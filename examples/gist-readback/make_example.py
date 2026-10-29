"""Create synthetic saved Gist evidence; no Git, network or account is used."""
import argparse
import hashlib
import json
from pathlib import Path


def make(out):
    out.mkdir(parents=True, exist_ok=False)
    payload = b'const value = "\\u0080";\n'
    inner = json.dumps({'artifact.txt': {'bytes': len(payload),
                        'sha256': hashlib.sha256(payload).hexdigest()}}, indent=2).encode() + b'\n'
    files = {'artifact.txt': payload, 'manifest.json': inner}
    objects = {}

    def add(kind, content):
        oid = hashlib.sha1(kind.encode() + b' ' + str(len(content)).encode()
                           + b'\0' + content, usedforsecurity=False).hexdigest()
        objects[oid] = (kind, content)
        return oid

    blobs = {name: add('blob', raw) for name, raw in files.items()}
    tree = add('tree', b''.join(b'100644 ' + name.encode() + b'\0' + bytes.fromhex(blobs[name])
                               for name in sorted(files)))
    commit = add('commit', ('tree ' + tree + '\nauthor Example <example@example.invalid> 0 +0000\n'
                           'committer Example <example@example.invalid> 0 +0000\n\nSynthetic example\n').encode())
    target = 'https://gist.github.com/example/' + '1' * 32
    api = {'id': '1' * 32, 'html_url': target, 'owner': {'login': 'example'},
           'history': [{'version': commit}], 'files': {name: {
               'filename': name, 'size': len(raw), 'truncated': False, 'encoding': 'utf-8',
               'content': raw.decode(),
               'raw_url': 'https://gist.githubusercontent.com/example/' + '1' * 32
                          + '/raw/' + blobs[name] + '/' + name}
               for name, raw in files.items()}}
    api['files']['artifact.txt']['content'] = 'const value = "\\^@";\n'
    expected = {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                for name, raw in files.items()}
    (out / 'expected.json').write_text(json.dumps(expected, indent=2) + '\n')
    (out / 'api.json').write_text(json.dumps(api, indent=2) + '\n')
    (out / 'revision.txt').write_text(commit + '\n')
    (out / 'objects.batch').write_bytes(b''.join(
        (oid + ' ' + kind + ' ' + str(len(content)) + '\n').encode() + content + b'\n'
        for oid, (kind, content) in objects.items()))
    return commit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(make(Path(args.out)))
