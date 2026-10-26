"""Retain bounded, source-pinned JavaScript snapshots; a difference is not a verdict."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ROOT / 'examples/js-differential'
ENGINES = {
    'goja': ('https://github.com/dop251/goja.git', 'github.com/dop251/goja'),
    'sobek': ('https://github.com/grafana/sobek.git', 'github.com/grafana/sobek'),
}
LIMIT = 8 * 1024 * 1024


def observer_source(engine, template):
    if engine not in ENGINES:
        raise ValueError('unsupported engine')
    repository, module = ENGINES[engine]
    marker = 'engine "github.com/dop251/goja"'
    if template.count(marker) != 1:
        raise ValueError('observer import marker must occur exactly once')
    return repository, module, template.replace(marker, 'engine "' + module + '"')


def verify_source_module(raw, module):
    declarations = re.findall(r'^module\s+([^\s]+)\s*$', raw, re.MULTILINE)
    if declarations != [module]:
        raise ValueError('source module differs from selected engine')


def sha(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON object key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('non-JSON numeric constant: ' + value)


def snapshots(raw):
    if len(raw) > LIMIT:
        raise ValueError('snapshot exceeds 8 MiB')
    rows = json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=unique_object,
                      parse_int=Decimal, parse_float=Decimal, parse_constant=reject_constant)
    if type(rows) is not list or not 1 <= len(rows) <= 10000:
        raise ValueError('expected 1..10000 snapshot rows')
    by_id = {}
    for row in rows:
        if (type(row) is not dict or not {'id', 'result'} <= set(row)
                or not set(row) <= {'id', 'input', 'result'}
                or type(row['id']) is not str or not 1 <= len(row['id']) <= 256
                or row['id'] in by_id):
            raise ValueError('invalid or duplicate snapshot identity')
        by_id[row['id']] = row
    return by_id


def typed(value):
    # bool and numeric 0/1 must not compare equal. JSON has one number category.
    if value is None:
        return ('null',)
    if type(value) is bool:
        return ('boolean', value)
    if type(value) is Decimal:
        return ('number', value)
    if type(value) is str:
        return ('string', value)
    if type(value) is list:
        return ('array', tuple(typed(v) for v in value))
    if type(value) is dict:
        return ('object', tuple((k, typed(v)) for k, v in sorted(value.items())))
    raise ValueError('unsupported snapshot value')


def classify(reference, head, base=None):
    if set(reference) != set(head) or (base is not None and set(reference) != set(base)):
        raise ValueError('provider case domains differ')
    groups = {k: [] for k in ('head_differences', 'corrected', 'introduced',
                              'unchanged_differences', 'changed_but_still_differs')}
    for id in sorted(reference):
        for provider in (head, base) if base is not None else (head,):
            if ('input' in provider[id]) != ('input' in reference[id]):
                raise ValueError('provider input identity presence differs')
            if 'input' in reference[id] and typed(provider[id]['input']) != typed(reference[id]['input']):
                raise ValueError('provider input identity differs')
        n, h = typed(reference[id]), typed(head[id])
        if h != n:
            groups['head_differences'].append(id)
        if base is None:
            continue
        b = typed(base[id])
        if b != n and h == n:
            groups['corrected'].append(id)
        elif b == n and h != n:
            groups['introduced'].append(id)
        elif h != n:
            groups['unchanged_differences' if h == b else 'changed_but_still_differs'].append(id)
    return groups


def kill_tree(process):
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    process.wait(timeout=10)


def isolated_environment(env):
    blocked = {'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
               'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
               'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT', 'GIT_PREFIX'}
    return {k: v for k, v in env.items() if k not in blocked
            and not k.startswith(('GIT_CONFIG_KEY_', 'GIT_CONFIG_VALUE_'))}


def run_step(label, command, cwd, env, out, steps, timeout=120):
    record = {'label': label, 'exit_code': None}
    steps.append(record)
    kwargs = {'start_new_session': True} if os.name == 'posix' else {}
    with (out / (label + '.stdout')).open('wb') as stdout, (out / (label + '.stderr')).open('wb') as stderr:
        process = subprocess.Popen(command, cwd=cwd, env=isolated_environment(env), stdout=stdout, stderr=stderr, **kwargs)
        started = time.monotonic()
        error = None
        try:
            while True:
                try:
                    process.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass
                if os.fstat(stdout.fileno()).st_size > LIMIT or os.fstat(stderr.fileno()).st_size > LIMIT:
                    error = label + ' output exceeds 8 MiB'
                if time.monotonic() - started > timeout:
                    error = label + ' timed out'
                if error or process.poll() is not None:
                    break
        finally:
            # The leader can exit while descendants still hold the output files.
            if os.name == 'posix' or process.poll() is None:
                kill_tree(process)
        record.update(exit_code=process.returncode, elapsed_seconds=round(time.monotonic() - started, 3))
        if error:
            record['error'] = error
            raise ValueError(error)
    if process.returncode:
        raise ValueError(label + ' exited ' + str(process.returncode))
    return (out / (label + '.stdout')).read_bytes()


def commit(value):
    if not re.fullmatch('[0-9a-f]{40}', value):
        raise argparse.ArgumentTypeError('a full lowercase Git commit SHA is required')
    return value


def compare(args):
    out = Path(args.out).resolve()
    # Never delete user files or mix fresh output with an old successful report.
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'schema': 'gooo-language-bridge/js-differential/v1', 'decision': 'FAIL_CLOSED',
              'engine': getattr(args, 'engine', 'goja'),
              'base_revision': args.base, 'head_revision': args.head,
              'head_ref': args.head_ref, 'steps': [], 'providers': {},
              'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    try:
        template = (PROVIDERS / 'observer.go').read_text()
        repository, module, observer = observer_source(report['engine'], template)
        report.update(repository=repository, module=module)
        script = Path(args.script)
        if not script.is_file():
            raise ValueError('script must be a regular file')
        with script.open('rb') as stream:
            source = stream.read(1024 * 1024 + 1)
        if not 1 <= len(source) <= 1024 * 1024:
            raise ValueError('script must be 1 byte..1 MiB')
        source.decode('utf-8', errors='strict')
        (out / 'snapshot-source.js').write_bytes(source)
        for original, name in [(Path(__file__), 'driver-source.py'),
                               (PROVIDERS / 'observer.go', 'observer-template.go'),
                               (PROVIDERS / 'observer.mjs', 'observer-source.mjs')]:
            shutil.copyfile(original, out / name)
        (out / 'observer-source.go').write_text(observer)
        with tempfile.TemporaryDirectory(prefix='gooo-js-') as temporary:
            work = Path(temporary)

            def run(label, command, cwd=work, timeout=120):
                return run_step(label, command, cwd, env, out, report['steps'], timeout)

            run('git-init', ['git', 'init', '--object-format=sha1', '-q', 'source'])
            checkout = work / 'source'
            go_version = run('go-version', ['go', 'version']).decode().strip()
            report['go'] = go_version
            (work / 'main.go').write_text(observer)
            (work / 'go.mod').write_text('module gooo-js-observer\n\ngo 1.27.3\n\n'
                                       'require ' + module + ' v0.0.0\n'
                                       'replace ' + module + ' => ./source\n')
            node_identity = json.loads(run('node-identity', [args.node, str(PROVIDERS / 'observer.mjs'), '--identity']))
            report['providers']['node'] = node_identity
            node_raw = run('node', [args.node, str(PROVIDERS / 'observer.mjs'),
                                   str(out / 'snapshot-source.js'), str(args.seconds * 1000)], timeout=args.seconds + 2)
            reference = snapshots(node_raw)
            native = {}
            for label, revision in [('head', args.head), ('base', args.base)]:
                if revision is None:
                    continue
                if label == 'base' and revision == args.head:
                    native[label] = native['head']
                    for suffix in ('stdout', 'stderr'):
                        shutil.copyfile(out / ('head.' + suffix), out / ('base.' + suffix))
                    report['providers'][label] = dict(report['providers']['head'], reused_head=True)
                    continue
                ref = args.head_ref if label == 'head' and args.head_ref else revision
                run(label + '-fetch', ['git', 'fetch', '--depth=1', repository, ref], cwd=checkout)
                fetched = run(label + '-fetched', ['git', 'rev-parse', 'FETCH_HEAD'], cwd=checkout).decode().strip()
                if fetched != revision:
                    raise ValueError(label + ' fetched revision differs from requested SHA')
                run(label + '-checkout', ['git', 'checkout', '--detach', revision], cwd=checkout)
                tree = run(label + '-tree', ['git', 'rev-parse', 'HEAD^{tree}'], cwd=checkout).decode().strip()
                verify_source_module((checkout / 'go.mod').read_text(), module)
                for name in ('go.mod', 'go.sum', 'LICENSE'):
                    shutil.copyfile(checkout / name, out / (label + '-source-' + name))
                run(label + '-tidy', ['go', 'mod', 'tidy'])
                binary = work / ('observer-' + label)
                run(label + '-build', ['go', 'build', '-trimpath', '-o', str(binary), '.'])
                shutil.copyfile(work / 'go.mod', out / (label + '-observer.mod'))
                shutil.copyfile(work / 'go.sum', out / (label + '-observer.sum'))
                identity = json.loads(run(label + '-identity', [str(binary), '--identity']))
                report['providers'][label] = dict(identity, engine=report['engine'], module=module,
                                                  source_tree=tree, binary_sha256=sha(binary))
                native[label] = snapshots(run(label, [str(binary), str(out / 'snapshot-source.js'),
                                                      str(args.seconds * 1000)], timeout=args.seconds + 2))
            groups = classify(reference, native['head'], native.get('base'))
            report.update(decision='DIFFERENCES' if groups['head_differences'] else 'MATCH',
                          cases=len(reference), counts={k: len(v) for k, v in groups.items()}, ids=groups)
    except (OSError, ValueError, KeyError, TypeError, RecursionError, ArithmeticError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        report['sha256'] = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != 'report.json'}
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=sorted(ENGINES), default='goja')
    parser.add_argument('--script', required=True, help='trusted JavaScript returning JSON.stringify of snapshot rows')
    parser.add_argument('--head', required=True, type=commit)
    parser.add_argument('--base', type=commit)
    parser.add_argument('--head-ref', help='optional refs/pull/N/head; resolved SHA must equal --head')
    parser.add_argument('--node', default='node')
    parser.add_argument('--seconds', type=int, default=30, choices=range(1, 61), metavar='1..60')
    parser.add_argument('--out', required=True, help='new output directory; existing directories are refused')
    args = parser.parse_args()
    if args.head_ref and not re.fullmatch(r'refs/pull/[1-9][0-9]*/head', args.head_ref):
        parser.error('--head-ref must be refs/pull/N/head')
    try:
        report = compare(args)
    except FileExistsError:
        parser.error('--out already exists; choose a fresh directory')
    print(json.dumps({k: report[k] for k in ('decision', 'elapsed_seconds')} |
                     {k: report[k] for k in ('cases', 'counts', 'error') if k in report}))
    return {'MATCH': 0, 'DIFFERENCES': 1, 'FAIL_CLOSED': 2}[report['decision']]


if __name__ == '__main__':
    raise SystemExit(main())
