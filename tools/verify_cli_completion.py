"""Compare CLI execution/completion intent with independent native observations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'bridges/completion-intent'
FIXTURE = ROOT / 'tests/fixtures/cli_completion_witness_test.go'
BASE = '10f69fd3c38de86a3bc17810dcb7f818b494f027'
PATCH = '5dbdb1037281c390c4f98c144ab82150262bdff9'
KEY = 'bridge/completion:Resolve'
ACTIVITY = 'urn:gooo:cli:resolve-input-intent'
CORRECTED = {scope + '/' + name for scope in ('root', 'child', 'nested')
             for name in ('unknown', 'missing-ascii', 'missing-unicode')}


def case_domain():
    rows = {}
    for scope in ('root', 'child', 'nested'):
        for name, token in [('unknown', '-az'), ('missing-ascii', '-ab'),
                            ('missing-unicode', '-a한'), ('single-missing', '-b')]:
            rows[scope + '/' + name] = (token, True, True, [token])
    for name, args, completion, incomplete in [
            ('reject-unknown', ['-az'], False, True),
            ('reject-missing', ['-ab'], False, True),
            ('reject-unicode', ['-a한'], False, True),
            ('equals-value', ['-ab=given'], False, False),
            ('separate-value', ['-ab', 'given'], False, False),
            ('equals-empty', ['-ab='], False, False),
            ('complete-value', ['-ab=given'], True, False),
            ('complete-empty', ['-ab='], True, False)]:
        rows['control/' + name] = (args[0], completion, incomplete, args)
    return rows


def observations(raw, failures):
    domain = case_domain()
    rows, terminals = {}, {}
    prefix = 'TestBridgeCompletionIntent/'
    for line in raw.splitlines():
        event = json.loads(line)
        output = event.get('Output', '')
        if 'WITNESS ' in output:
            row = json.loads(output.split('WITNESS ', 1)[1])
            if row['id'] in rows or event.get('Test') != prefix + row['id']:
                raise ValueError('duplicate or mislabeled native witness')
            rows[row['id']] = row
        name = event.get('Test', '')
        if name.startswith(prefix) and event['Action'] in ('pass', 'fail', 'skip'):
            id = name[len(prefix):]
            if id in terminals:
                raise ValueError('duplicate native terminal event')
            terminals[id] = event['Action']
    if set(rows) != set(domain) or set(terminals) != set(domain):
        raise ValueError('native case domain differs')
    for id, row in rows.items():
        token, completion, incomplete, args = domain[id]
        value = row['input']
        if (set(value) != {'token', 'completion', 'incomplete'}
                or type(value['token']) is not str
                or type(value['completion']) is not bool or type(value['incomplete']) is not bool
                or value != dict(token=token, completion=completion, incomplete=incomplete)):
            raise ValueError('native input identity differs')
        path = ['sub'] if id.startswith('child/') else ['sub', 'nested'] if id.startswith('nested/') else []
        argv = ['app'] + path + ['value'] + args + (['--generate-shell-completion'] if completion else [])
        if (row['argv'] != argv or any(type(row[k]) is not bool for k in ('action', 'completed', 'error'))
                or (row['completion_args'] is not None and
                    (type(row['completion_args']) is not list or any(type(v) is not str for v in row['completion_args'])))):
            raise ValueError('native argv or callback types differ')
        if row['error']:
            actual = 'REJECT' if not row['action'] and not row['completed'] else 'INVALID_CALLBACK'
        elif completion:
            if not row['completed'] or row['action']:
                actual = 'INVALID_CALLBACK'
            elif row['completion_args'] == ['value', token]:
                actual = 'PENDING:' + token
            else:
                actual = 'CONSUMED' if row['completion_args'] == ['value'] else 'INVALID_TAIL'
        else:
            actual = 'CONSUMED' if row['action'] and not row['completed'] else 'INVALID_CALLBACK'
        expected = ('PENDING:' + token if completion else 'REJECT') if incomplete else 'CONSUMED'
        if row['actual'] != actual or row['expected'] != expected:
            raise ValueError('native result is not supported by its observations')
        if (terminals[id] != ('fail' if id in failures else 'pass')
                or (actual != expected) != (id in failures)):
            raise ValueError('native failure set differs')
    return rows


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    out = ROOT / 'evidence/completion-intent'
    out.mkdir(parents=True, exist_ok=True)
    for path in out.iterdir():
        if path.is_file():
            path.unlink()
    started = time.monotonic()
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    summary = {'schema': 'gooo-language-bridge/completion-intent/v1', 'decision': 'FAIL_CLOSED',
               'original': BASE, 'patch': PATCH, 'steps': [],
               'upstream_pr': 'https://github.com/urfave/cli/pull/2485',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    try:
        provenance = json.loads((BRIDGE / 'provenance.json').read_text())
        if (provenance['original_revision'] != BASE or provenance['submitted_revision'] != PATCH
                or provenance['fixture_sha256'] != hashlib.sha256(FIXTURE.read_bytes()).hexdigest()):
            raise ValueError('provenance source or fixture differs')
        with tempfile.TemporaryDirectory(prefix='cli-completion-') as temporary:
            work = Path(temporary)

            def run(label, command, expected=0, cwd=work):
                p = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=180)
                (out / (label + '.stdout')).write_bytes(p.stdout)
                (out / (label + '.stderr')).write_bytes(p.stderr)
                summary['steps'].append({'label': label, 'command': command, 'exit_code': p.returncode})
                if p.returncode != expected:
                    raise ValueError(label + ' exit code differs')
                return p.stdout

            run('init', ['git', 'init', '-q'])
            run('fetch-original', ['git', 'fetch', '--depth=1', 'https://github.com/urfave/cli.git', BASE])
            run('fetch-patch', ['git', 'fetch', '--depth=1', 'https://github.com/kimjooyoon/cli.git', PATCH])
            rows_by_revision = []
            command = ['go', 'test', '-json', '.', '-run', '^TestBridgeCompletionIntent$', '-count=1', '-timeout=45s']
            for label, rev, failures in [('before', BASE, CORRECTED), ('after', PATCH, set())]:
                run(label + '-checkout', ['git', 'checkout', '--detach', rev])
                if run(label + '-identity', ['git', 'rev-parse', 'HEAD']).decode().strip() != rev:
                    raise ValueError('native source revision differs')
                for name in ('command_parse.go', 'go.mod', 'go.sum', 'LICENSE'):
                    shutil.copyfile(work / name, out / (label + '-' + name.replace('/', '-')))
                shutil.copyfile(FIXTURE, work / 'bridge_completion_witness_test.go')
                rows_by_revision.append(observations(run(label, command, 1 if failures else 0), failures))
            before, after = rows_by_revision
            race = observations(run('race', command[:2] + ['-race'] + command[2:]), set())
            for id in case_domain():
                for key in ('input', 'argv', 'expected'):
                    if before[id][key] != after[id][key] or race[id][key] != after[id][key]:
                        raise ValueError('native input or expectation differs')
            rows = [after[id] for id in sorted(case_domain())]
            cases = out / 'cases.json'
            cases.write_text(json.dumps({'schema': 'gooo/body-composition-cases/v1', 'cases': [
                {'inputs': {KEY: row['input']}, 'expected': {KEY: row['expected']}} for row in rows]}, indent=2) + '\n')
            binary = str(Path(args.gooo).resolve())
            version = json.loads(run('compiler', [binary, 'version', '--build', '--json']))
            if version.get('version') != '0.6.38-dev':
                raise ValueError('compiler version differs')
            receipt = json.loads(run('execution', [binary, 'package', 'execute', '--json', '--cases',
                                                  str(cases), 'gooo.workspace.json'], cwd=BRIDGE))
            runtime = receipt.get('result', {}).get('runtime', {})
            if (receipt.get('decision') != 'PASS' or receipt.get('cases_digest') != digest(cases)
                    or receipt.get('manifest_digest') != digest(BRIDGE / 'gooo.workspace.json')
                    or any(type(runtime.get(k)) is not int or runtime[k] != 20 for k in ('finite_total', 'finite_passed'))):
                raise ValueError('missing complete source-bound Gooo PASS')
            traces = runtime['traces']
            if (len(traces) != 20 or any(type(t['case_index']) is not int for t in traces)
                    or {t['case_index'] for t in traces} != set(range(20))):
                raise ValueError('Gooo case domain differs')
            for trace in traces:
                row = rows[trace['case_index']]
                if len(trace['deliveries']) != 1:
                    raise ValueError('ambiguous Gooo delivery')
                d = trace['deliveries'][0]
                if (d['activity_id'] != ACTIVITY or d['input'] != row['input']
                        or type(d['input']['token']) is not str or type(d['input']['completion']) is not bool
                        or type(d['input']['incomplete']) is not bool
                        or d['actual'] != row['expected'] or d['expected'] != row['expected'] or d['passed'] is not True):
                    raise ValueError('Gooo input, identity or output differs')
                row.update(original=before[row['id']]['actual'], patched=row['actual'], gooo=d['actual'])
            (out / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
            summary.update(decision='PASS', cases=20,
                           distinct_policy_inputs=len({json.dumps(row['input'], sort_keys=True) for row in rows}),
                           original_mismatches=9, patched_matches=20,
                           gooo_matches=20, compiler_sha256=digest(Path(binary)),
                           go=run('go-version', ['go', 'version']).decode().strip())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + list(BRIDGE.iterdir()) + [Path(__file__), FIXTURE]
        summary['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)
                             if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
