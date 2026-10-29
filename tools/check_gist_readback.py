"""Check saved flat Gist objects and API text; never fetch, execute or publish."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

if __package__:
    from .compare_go_tests import capture, decode
else:
    from compare_go_tests import capture, decode

LIMIT = 8 * 1024 * 1024
MAX_FILES = 100
MAX_OBJECTS = 1024
SHA1 = re.compile(r'[0-9a-f]{40}')
SHA256 = re.compile(r'[0-9a-f]{64}')
MATCHES = {'GIT_BLOBS_MATCH_MANIFEST', 'GIT_BLOBS_MATCH_API_TEXT_DIFFERS',
           'GIT_BLOBS_MATCH_API_TEXT_INCOMPLETE'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def filename(value):
    require(type(value) is str and value not in ('', '.', '..')
            and not any(c in value for c in '/\\')
            and not any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value),
            'expected a flat filename without control characters')
    require(len(value.encode('utf-8')) <= 255, 'filename exceeds 255 UTF-8 bytes')
    return value


def manifest_files(value):
    require(type(value) is dict and 1 <= len(value) <= MAX_FILES,
            'expected 1..100 manifest files, including the manifest if published')
    for name, entry in value.items():
        filename(name)
        require(type(entry) is dict and set(entry) == {'bytes', 'sha256'},
                'manifest entries need exactly bytes and sha256')
        require(type(entry['bytes']) is int and 0 <= entry['bytes'] <= LIMIT,
                'invalid manifest byte count')
        require(type(entry['sha256']) is str and SHA256.fullmatch(entry['sha256']),
                'expected lowercase SHA-256')
    return value


def batch_objects(raw):
    require(type(raw) is bytes and 1 <= len(raw) <= LIMIT, 'object capture byte budget')
    objects, pos = {}, 0
    while pos < len(raw):
        require(len(objects) < MAX_OBJECTS, 'object count budget')
        end = raw.find(b'\n', pos, pos + 129)
        require(end >= 0, 'missing or oversized batch header')
        fields = raw[pos:end].split(b' ')
        require(len(fields) == 3, 'expected default cat-file batch header')
        oid, kind, size = fields
        require(re.fullmatch(b'[0-9a-f]{40}', oid) is not None
                and kind in (b'commit', b'tree', b'blob', b'tag')
                and re.fullmatch(b'0|[1-9][0-9]{0,6}', size) is not None,
                'invalid SHA-1 object header')
        size = int(size)
        require(size <= LIMIT, 'object byte budget')
        start, finish = end + 1, end + 1 + size
        require(finish < len(raw) and raw[finish:finish + 1] == b'\n',
                'truncated object or missing batch terminator')
        content = raw[start:finish]
        digest = hashlib.sha1(kind + b' ' + str(size).encode() + b'\0' + content,
                              usedforsecurity=False).hexdigest()
        require(digest == oid.decode(), 'Git object hash differs from content')
        require(digest not in objects, 'duplicate captured object ID')
        objects[digest] = (kind.decode(), content)
        pos = finish + 1
    return objects


class ObjectsNeeded(Exception):
    def __init__(self, oid):
        self.oid = oid


def object_content(objects, oid, kind):
    if oid not in objects:
        raise ObjectsNeeded(oid)
    actual, content = objects[oid]
    require(actual == kind, 'referenced object has the wrong type')
    return content


def flat_tree(raw):
    result, pos, previous = {}, 0, None
    while pos < len(raw):
        require(len(result) < MAX_FILES, 'tree file count budget')
        space, nul = raw.find(b' ', pos), raw.find(b'\0', pos)
        require(pos < space < nul and nul + 21 <= len(raw), 'invalid flat tree entry')
        require(raw[pos:space] in (b'100644', b'100755'),
                'only regular flat blob entries are supported')
        name_bytes = raw[space + 1:nul]
        name = filename(name_bytes.decode('utf-8', errors='strict'))
        require(name not in result, 'duplicate tree filename')
        require(previous is None or previous < name_bytes, 'tree names are not in Git order')
        result[name] = raw[nul + 1:nul + 21].hex()
        previous, pos = name_bytes, nul + 21
    return result


def base_report():
    return {'schema': 'gooo/gist-readback/v1', 'decision': 'INVALID_CAPTURE',
            'next_action': 'INSPECT_CAPTURE', 'git_blob_bytes_match': False,
            'api_metadata_matches': False, 'source_authenticated': False,
            'remote_freshness_established': False, 'patch_approval_verified': False,
            'captured_source_executed': False, 'network_requests': 0,
            'publication_effects': 0, 'repost_recommended': False}


def check(manifest, api, raw_objects, target, revision):
    expected = manifest_files(manifest)
    require(type(revision) is str and SHA1.fullmatch(revision),
            'expected an independent full lowercase commit pin')
    require(type(target) is str and len(target) <= 500, 'expected bounded Gist URL text')
    parsed = urlsplit(target)
    require(parsed.scheme == 'https' and parsed.netloc == 'gist.github.com'
            and not parsed.query and not parsed.fragment
            and re.fullmatch(r'/[A-Za-z0-9][A-Za-z0-9-]{0,38}/[0-9a-f]{32}', parsed.path)
            and parsed.geturl() == target, 'expected canonical HTTPS Gist URL')
    owner, gist_id = parsed.path.strip('/').split('/')
    require(type(api) is dict and type(api.get('files')) is dict
            and len(api['files']) <= MAX_FILES, 'expected bounded Gist API files')
    objects = batch_objects(raw_objects)
    report = base_report()
    report.update(gist=target, requested_revision=revision, expected_files=len(expected),
                  captured_objects=len(objects), issues=[], file_bindings=[],
                  api_text_differences=[], api_text_incomplete=[])

    def mismatch(condition, code):
        if not condition:
            report['issues'].append(code)

    def api_mismatch(condition, code):
        if not condition:
            report['issues'].append(code)
            report['api_metadata_matches'] = False

    report['api_metadata_matches'] = True
    history = api.get('history')
    captured_revision = (history[0].get('version') if type(history) is list
                         and history and type(history[0]) is dict else None)
    api_mismatch(api.get('id') == gist_id, 'API_GIST_ID_DIFFERS')
    api_mismatch(api.get('html_url') == target, 'API_GIST_URL_DIFFERS')
    api_mismatch(type(api.get('owner')) is dict and api['owner'].get('login') == owner,
                 'API_OWNER_DIFFERS')
    api_mismatch(captured_revision == revision, 'API_REVISION_DIFFERS_OR_MISSING')
    api_mismatch(set(api['files']) == set(expected), 'API_FILE_NAMES_DIFFER')
    try:
        commit = object_content(objects, revision, 'commit')
        headers, separator, _ = commit.partition(b'\n\n')
        lines = headers.split(b'\n')
        roots = [line for line in lines if line.startswith(b'tree ')]
        require(separator and roots and roots == [lines[0]]
                and re.fullmatch(b'tree [0-9a-f]{40}', roots[0]),
                'expected exactly one leading commit tree header')
        root = roots[0][5:].decode()
        entries = flat_tree(object_content(objects, root, 'tree'))
        report['root_tree'] = root
        mismatch(set(entries) == set(expected), 'MANIFEST_TREE_FILE_NAMES_DIFFER')
        git_issues = len(report['issues'])
        for name in sorted(set(expected) & set(entries)):
            content = object_content(objects, entries[name], 'blob')
            digest = hashlib.sha256(content).hexdigest()
            matches = len(content) == expected[name]['bytes'] and digest == expected[name]['sha256']
            mismatch(matches, name + ':GIT_BYTES_DIFFER')
            binding = {'filename': name, 'blob': entries[name], 'bytes': len(content),
                       'sha256': digest, 'matches_manifest': matches}
            report['file_bindings'].append(binding)
        report['git_blob_bytes_match'] = (set(entries) == set(expected)
                                          and len(report['issues']) == git_issues)
    except ObjectsNeeded as missing:
        report.update(decision='GIT_OBJECTS_NEEDED', next_action='READ_EXISTING_GIT_OBJECTS',
                      missing_object_ids=[missing.oid], api_metadata_matches=False)
        return report

    for name in sorted(set(expected) & set(api['files'])):
        item = api['files'][name]
        require(type(item) is dict and type(item.get('truncated')) is bool,
                'expected file metadata with a Boolean truncated flag')
        api_mismatch(item.get('filename') == name, name + ':API_FILENAME_DIFFERS')
        if 'size' in item:
            api_mismatch(type(item['size']) is int and item['size'] == expected[name]['bytes'],
                         name + ':API_SIZE_DIFFERS')
        if 'content' in item:
            require(type(item['content']) is str, 'API content must be text')
        if 'encoding' in item:
            require(type(item['encoding']) is str, 'API encoding must be text')
        if item['truncated'] or 'content' not in item or item.get('encoding', 'utf-8') != 'utf-8':
            report['api_text_incomplete'].append(name)
            continue
        content = item['content'].encode('utf-8', errors='strict')
        digest = hashlib.sha256(content).hexdigest()
        if len(content) != expected[name]['bytes'] or digest != expected[name]['sha256']:
            report['api_text_differences'].append({'filename': name, 'bytes': len(content),
                                                   'sha256': digest})
    report['issues'] = sorted(set(report['issues']))
    if report['issues']:
        report.update(decision='CAPTURE_MISMATCH', next_action='INSPECT_CAPTURE')
    elif report['api_text_incomplete']:
        report.update(decision='GIT_BLOBS_MATCH_API_TEXT_INCOMPLETE',
                      next_action='RETAIN_CAPTURED_GIT_BYTES')
    elif report['api_text_differences']:
        report.update(decision='GIT_BLOBS_MATCH_API_TEXT_DIFFERS',
                      next_action='RETAIN_CAPTURED_GIT_BYTES')
    else:
        report.update(decision='GIT_BLOBS_MATCH_MANIFEST', next_action='RETAIN_CAPTURED_GIT_BYTES')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('gist', 'revision', 'manifest', 'api', 'objects', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    try:
        out.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 2
    report = base_report()
    try:
        raw = {}
        for name in ('manifest', 'api', 'objects'):
            raw[name] = capture(getattr(args, name), limit=LIMIT)
            (out / (name + '.original')).write_bytes(raw[name])
        report = check(decode(raw['manifest']), decode(raw['api']), raw['objects'],
                       args.gist, args.revision)
    except (OSError, ValueError, TypeError, RecursionError) as error:
        report['error'] = str(error)
    for name in ('check_gist_readback.py', 'compare_go_tests.py', 'compare_js.py'):
        (out / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    report['sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(out.iterdir()) if p.is_file()}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['decision'] in MATCHES else 2 if report['decision'] == 'INVALID_CAPTURE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
