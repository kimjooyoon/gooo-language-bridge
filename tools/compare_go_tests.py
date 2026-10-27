"""Compare complete recorded Go test outcomes; never execute or approve a patch."""
import argparse
from bisect import bisect_left
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

if __package__:
    from .compare_js import classify, reject_constant, unique_object
else:
    from compare_js import classify, reject_constant, unique_object

LIMIT = 8 * 1024 * 1024


def decode(raw):
    return json.loads(raw.decode('utf-8', errors='strict'),
                      object_pairs_hook=unique_object, parse_constant=reject_constant)


def identity(value, maximum=1024):
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or any(ord(c) < 32 for c in value)):
        raise ValueError('invalid case, package or test identity')
    value.encode('utf-8', errors='strict')
    return value


def domain(raw):
    if not 1 <= len(raw) <= LIMIT:
        raise ValueError('case domain must be 1 byte..8 MiB')
    rows = decode(raw)
    if type(rows) is not list or not 1 <= len(rows) <= 1000:
        raise ValueError('expected 1..1000 explicit leaf cases')
    result, pairs = {}, set()
    for row in rows:
        if type(row) is not dict or set(row) != {'id', 'package', 'test'}:
            raise ValueError('each case needs exactly id, package and test')
        name = identity(row['id'], 256)
        pair = (identity(row['package']), identity(row['test']))
        if name in result or pair in pairs:
            raise ValueError('duplicate case identity or package/test pair')
        result[name] = pair
        pairs.add(pair)
    return result


def observations(raw, cases):
    if not 1 <= len(raw) <= LIMIT:
        raise ValueError('capture must be 1 byte..8 MiB')
    packages, tests, package_tests = {}, {}, {}
    for line in raw.splitlines():
        if not line.strip():
            raise ValueError('blank record in capture')
        event = decode(line)
        if type(event) is not dict:
            raise ValueError('test event must be an object')
        action = event.get('Action')
        if event.get('FailedBuild') or action == 'build-fail':
            raise ValueError('build failure is not a test outcome')
        if action == 'build-output':
            identity(event.get('ImportPath'))
            if type(event.get('Output')) is not str:
                raise ValueError('invalid build output')
            continue
        package = identity(event.get('Package'))
        test = event.get('Test')
        if test is not None:
            test = identity(test)
        if action == 'start' and test is None:
            if package in packages:
                raise ValueError('duplicate package start; use a single capture with -count=1')
            packages[package] = 'running'
            package_tests[package] = []
            continue
        if packages.get(package) != 'running':
            raise ValueError('event outside an active package')
        if action == 'output':
            if type(event.get('Output')) is not str:
                raise ValueError('invalid test output')
            continue
        if test is None:
            if action not in ('pass', 'fail', 'skip'):
                raise ValueError('unsupported package action')
            states = [tests[k] for k in package_tests[package]]
            if any(v in ('running', 'paused') for v in states):
                raise ValueError('package ended with unfinished tests')
            if action == 'skip' and states:
                raise ValueError('package skipped after recording tests')
            if (action == 'fail') != ('fail' in states):
                raise ValueError('package failure and test failures disagree')
            packages[package] = action
            continue
        key = (package, test)
        state = tests.get(key)
        if action == 'run' and state is None:
            tests[key] = 'running'
            package_tests[package].append(key)
        elif action == 'pause' and state == 'running':
            tests[key] = 'paused'
        elif action == 'cont' and state == 'paused':
            tests[key] = 'running'
        elif action in ('pass', 'fail', 'skip') and state == 'running':
            tests[key] = action
        else:
            raise ValueError('duplicate, unsupported or out-of-order test event')
    if not packages or any(v == 'running' for v in packages.values()):
        raise ValueError('capture has no complete package termination')
    ordered = sorted(tests)

    def is_parent(package, test):
        prefix = test + '/'
        index = bisect_left(ordered, (package, prefix))
        return (index < len(ordered) and ordered[index][0] == package
                and ordered[index][1].startswith(prefix))

    result = {}
    for name, (package, test) in cases.items():
        if is_parent(package, test):
            raise ValueError('selected case is a parent, not a leaf test')
        if tests.get((package, test)) not in ('pass', 'fail'):
            raise ValueError('selected leaf case is missing, skipped or incomplete')
        result[name] = {'id': name, 'input': [package, test],
                        'result': tests[(package, test)]}
    selected = set(cases.values())
    return result, {'packages': packages, 'unselected_failures': [
        {'package': p, 'test': t} for (p, t), status in sorted(tests.items())
        if status == 'fail' and (p, t) not in selected and not is_parent(p, t)],
        'parent_failures': [{'package': p, 'test': t}
                            for (p, t), status in sorted(tests.items())
                            if status == 'fail' and is_parent(p, t)]}


def compare(raw_cases, raw_base, raw_head):
    cases = domain(raw_cases)
    base, base_context = observations(raw_base, cases)
    head, head_context = observations(raw_head, cases)
    expected = {k: dict(v, result='pass') for k, v in base.items()}
    groups = classify(expected, head, base)
    return {'decision': 'RECORDED_OUTCOMES_COMPARED', 'cases': len(cases),
            'introduced_failures': groups['introduced'],
            'resolved_failures': groups['corrected'],
            'failed_both': groups['unchanged_differences'],
            'passed_both': sorted(set(cases) - set(groups['head_differences'])
                                  - set(groups['corrected'])),
            'outcomes': [{'id': k, 'package': cases[k][0], 'test': cases[k][1],
                          'base': base[k]['result'], 'head': head[k]['result']}
                         for k in sorted(cases)],
            'context': {'base': base_context, 'head': head_context},
            'source_revision_authenticated': False, 'go_runtime_observed': False,
            'failure_causes_compared': False, 'patch_approved': False}


def capture(path, limit=LIMIT):
    # Opening a named pipe must not wait for a writer before checking its type.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('input must be a regular file')
        raw = stream.read(limit + 1)
    if not 1 <= len(raw) <= limit:
        raise ValueError('input must be 1 byte..' + str(limit) + ' bytes')
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cases', 'base', 'head', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    # Refuse an existing directory even if a previous comparison failed.
    try:
        out.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 2
    report = {'decision': 'INVALID_CAPTURE'}
    try:
        raw = {}
        for name in ('cases', 'base', 'head'):
            raw[name] = capture(getattr(args, name))
            (out / (name + '.original')).write_bytes(raw[name])
        for name in ('compare_go_tests.py', 'compare_js.py'):
            (out / name).write_bytes(Path(__file__).with_name(name).read_bytes())
        report = compare(raw['cases'], raw['base'], raw['head'])
    except (OSError, ValueError) as error:
        report['error'] = str(error)
    report['sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(out.iterdir()) if p.is_file()}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=True))
    if report['decision'] != 'RECORDED_OUTCOMES_COMPARED':
        return 2
    return 1 if 'fail' in report['context']['head']['packages'].values() else 0


if __name__ == '__main__':
    raise SystemExit(main())
