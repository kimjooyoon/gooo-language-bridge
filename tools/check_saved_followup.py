"""Compare local saved activity; never collect, execute, post, or update a baseline.

Each bundle has snapshot.json with schema gooo/saved-followup-snapshot/v1,
subject, and the eight COMPONENTS. Components declare coverage and relative
files; invocation instead declares coverage, argv, and selection. Coverage is
complete/partial/unknown/missing. Complete file components need captured files,
including an explicit empty collection when no feedback/checks were observed.

The previous bundle additionally has inspection.json and a separate result file: schema
gooo/saved-followup-inspection/v1, status=completed, exit_code=0,
snapshot_sha256, evaluation_sha256, and result={path, sha256}. These are local
unsigned declarations, not authenticated process evidence. Digests use sha256:.
The report exposes bindings for manually recording a completed inspection.
An unchanged result says nothing about remote freshness or B1/B2 decisions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

COMPONENTS = ('head', 'feedback', 'checks', 'implementation', 'policy', 'schemas', 'invocation', 'scope')
EVALUATION = ('implementation', 'policy', 'schemas', 'invocation', 'scope')
MAX_FILE = 128 * 1024
MAX_TOTAL = 1024 * 1024
MAX_FILES = 64
COVERAGE = ('complete', 'partial', 'unknown', 'missing')
LIMITS = ['Saved local bytes only; no remote freshness is established.',
          'Completion is unsigned local evidence; no process authentication is established.',
          'No approval, posting permission, or B1/B2 policy decision is established.']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def text(value, maximum, empty=False):
    require(type(value) is str and (empty or bool(value)) and len(value) <= maximum, 'invalid bounded text')


def object_fields(value, fields):
    require(type(value) is dict and set(value) == set(fields), 'missing or unknown object fields')


def path_parts(name):
    text(name, 256)
    parts = name.split('/')
    require('\\' not in name and '\x00' not in name and all(p not in ('', '.', '..') for p in parts),
            'expected relative path without traversal')
    return parts


def read_file(directory, name):
    """Open every in-bundle path component without following symlinks."""
    parts = path_parts(name)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    fd = os.open(directory, flags | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], flags | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(child, 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_FILE, 'expected bounded regular file')
            data = source.read(MAX_FILE + 1)
            require(len(data) <= MAX_FILE, 'file exceeds byte budget')
            return data
    finally:
        os.close(fd)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate JSON key')
        value[key] = item
    return value


def invalid_constant(value):
    raise ValueError('nonfinite JSON constant: ' + value)


def parsed(data):
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)


def snapshot(directory):
    raw = read_file(directory, 'snapshot.json')
    manifest = parsed(raw)
    object_fields(manifest, ('schema', 'subject', 'components'))
    require(manifest['schema'] == 'gooo/saved-followup-snapshot/v1', 'unsupported snapshot schema')
    text(manifest['subject'], 512)
    object_fields(manifest['components'], COMPONENTS)
    seen, components, incomplete = set(), {}, []
    total = len(raw)
    for role in COMPONENTS:
        component = manifest['components'][role]
        fields = ('coverage', 'argv', 'selection') if role == 'invocation' else ('coverage', 'files')
        object_fields(component, fields)
        require(type(component['coverage']) is str and component['coverage'] in COVERAGE, 'invalid coverage')
        if component['coverage'] != 'complete':
            incomplete.append(role)
        bound = dict(component)
        if role == 'invocation':
            argv = component['argv']
            require(type(argv) is list and 1 <= len(argv) <= 64, 'invalid argv')
            for arg in argv:
                text(arg, 1024, empty=True)
            text(component['selection'], 4096)
        else:
            files = component['files']
            require(type(files) is list and len(files) <= MAX_FILES, 'invalid file list')
            require(component['coverage'] != 'complete' or bool(files), 'complete coverage needs captured files')
            bound['files'] = []
            for name in files:
                path_parts(name)
                require(name not in seen and name not in ('snapshot.json', 'inspection.json'), 'duplicate or reserved file path')
                seen.add(name)
                require(len(seen) <= MAX_FILES, 'bundle exceeds file budget')
                data = read_file(directory, name)
                total += len(data)
                require(total <= MAX_TOTAL, 'bundle exceeds byte budget')
                bound['files'].append({'path': name, 'bytes': len(data), 'sha256': digest(data)})
        components[role] = digest(encoded(bound))
    return {'subject': manifest['subject'], 'component_sha256': components,
            'captured_files': sorted(seen), 'captured_bytes': total,
            'incomplete_components': incomplete,
            'snapshot_sha256': digest(encoded({'manifest_sha256': digest(raw), 'components': components})),
            'evaluation_sha256': digest(encoded({k: components[k] for k in EVALUATION}))}


def completion(directory, previous):
    raw = read_file(directory, 'inspection.json')
    receipt = parsed(raw)
    object_fields(receipt, ('schema', 'status', 'exit_code', 'snapshot_sha256', 'evaluation_sha256', 'result'))
    require(receipt['schema'] == 'gooo/saved-followup-inspection/v1', 'unsupported inspection schema')
    require(receipt['status'] == 'completed' and type(receipt['exit_code']) is int and receipt['exit_code'] == 0,
            'previous inspection did not declare successful completion')
    for key in ('snapshot_sha256', 'evaluation_sha256'):
        require(receipt[key] == previous[key], 'previous inspection binding differs: ' + key)
    result = receipt['result']
    object_fields(result, ('path', 'sha256'))
    require(result['path'] not in ('snapshot.json', 'inspection.json')
            and result['path'] not in previous['captured_files'], 'result is not a separate inspection output')
    require(type(result['sha256']) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', result['sha256']), 'invalid result digest')
    data = read_file(directory, result['path'])
    require(previous['captured_bytes'] + len(raw) + len(data) <= MAX_TOTAL, 'previous bundle exceeds byte budget')
    require(bool(data) and digest(data) == result['sha256'], 'missing or changed completed result')
    return {'receipt': str(Path(directory).absolute() / 'inspection.json'), 'receipt_sha256': digest(raw),
            'snapshot_sha256': previous['snapshot_sha256'], 'evaluation_sha256': previous['evaluation_sha256'],
            'result': result}


def check(current_directory, previous_directory=None):
    current = snapshot(current_directory)
    report = {'schema': 'gooo/saved-followup-report/v1', 'decision': 'INSPECT', 'reason': 'NO_PREVIOUS_INSPECTION',
              'changed_components': [], 'incomplete_components': ['current:' + k for k in current['incomplete_components']],
              'current_binding': current, 'prior_binding': None, 'effect': 'none', 'limits': list(LIMITS)}
    if previous_directory is None:
        return report
    try:
        previous = snapshot(previous_directory)
        changed = [k for k in COMPONENTS if current['component_sha256'][k] != previous['component_sha256'][k]]
        if current['subject'] != previous['subject']:
            changed.append('subject')
        if not changed and current['snapshot_sha256'] != previous['snapshot_sha256']:
            changed.append('manifest')
        report['changed_components'] = changed
        report['incomplete_components'] += ['previous:' + k for k in previous['incomplete_components']]
        report['prior_binding'] = completion(previous_directory, previous)
    except (OSError, ValueError, TypeError) as error:
        report.update(reason='PREVIOUS_INSPECTION_UNUSABLE', diagnostic=str(error))
        return report
    if report['incomplete_components']:
        report['reason'] = 'INCOMPLETE_SAVED_COVERAGE'
    elif report['changed_components']:
        report['reason'] = 'SAVED_COMPONENT_CHANGED'
    else:
        report.update(decision='RETAIN_UNCHANGED', reason='IDENTICAL_COMPLETE_SAVED_INPUT_AND_EVALUATION')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', required=True, type=Path)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    code = 0
    try:
        report = check(args.current, args.previous)
    except (OSError, ValueError, TypeError) as error:
        code = 2
        report = {'schema': 'gooo/saved-followup-report/v1', 'decision': 'INSPECT',
                  'reason': 'INVALID_CURRENT_BUNDLE', 'diagnostic': str(error), 'effect': 'none', 'limits': list(LIMITS)}
    if args.output is None:
        sys.stdout.write(encoded(report).decode())
    else:
        destination = args.output.resolve()
        for bundle in (args.current, args.previous):
            require(bundle is None or not destination.is_relative_to(bundle.resolve()), 'output must not replace bundle evidence')
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        with os.fdopen(fd, 'wb') as output:
            require(stat.S_ISREG(os.fstat(output.fileno()).st_mode), 'expected regular output file')
            output.write(encoded(report))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
