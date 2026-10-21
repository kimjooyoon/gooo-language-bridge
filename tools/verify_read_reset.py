"""Bounded predicate proposal and Gooo comparison; not a Traefik integration run."""
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
PROPOSAL = ROOT / 'proposals/traefik-read-reset'
BRIDGE = ROOT / 'bridges/read-reset'
KEY = 'bridge/readreset:Classify'
ACTIVITY = 'urn:gooo:read-reset:classify'
CORRECTED = {'readfrom-read-reset', 'writeto-read-reset', 'readfrom-writeto-read-reset',
             'wrapped-readfrom-read-reset', 'loopback-reset'}
IDS = {'nil', 'plain-reset', 'plain-other', 'read-reset', 'fmt-read-reset', 'write-reset',
       'dial-reset', 'read-other', 'readfrom-read-other', 'readfrom-reset-without-read',
       'readfrom-write-reset'} | CORRECTED


def observations(raw, failures):
    rows, terminals = {}, {}
    for line in raw.splitlines():
        event = json.loads(line)
        output = event.get('Output', '')
        if 'WITNESS ' in output:
            row = json.loads(output.split('WITNESS ', 1)[1])
            if row['id'] in rows:
                raise ValueError('duplicate native case')
            rows[row['id']] = row
        name = event.get('Test', '')
        if name.startswith('TestReadResetClassification/') or name == 'TestReadFromReset':
            if event['Action'] in ('pass', 'fail', 'skip'):
                if name in terminals:
                    raise ValueError('duplicate native terminal event')
                terminals[name] = event['Action']
    if set(rows) != IDS:
        raise ValueError('native domain differs')
    for id, row in rows.items():
        name = 'TestReadFromReset' if id == 'loopback-reset' else 'TestReadResetClassification/' + id
        if terminals.get(name) != ('fail' if id in failures else 'pass'):
            raise ValueError('native test outcome differs: ' + id)
        if (row['actual'] != row['expected']) != (id in failures):
            raise ValueError('native mismatch set differs')
        obs = row['observation']
        if (set(obs) != {'outer_op', 'middle_op', 'inner_op', 'has_reset', 'has_error'}
                or any(type(obs[k]) is not str for k in ('outer_op', 'middle_op', 'inner_op'))
                or any(type(obs[k]) is not bool for k in ('has_reset', 'has_error'))
                or row['expected'] not in ('NO_LOG', 'DEBUG', 'ERROR')):
            raise ValueError('malformed native observation')
    loopback = rows['loopback-reset']['observation']
    if loopback != {'outer_op': 'readfrom', 'middle_op': 'read', 'inner_op': '',
                    'has_reset': True, 'has_error': True}:
        raise ValueError('real TCP reset did not reproduce the reported wrapper shape')
    return rows


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    out = ROOT / 'evidence/read-reset'
    out.mkdir(parents=True, exist_ok=True)
    for p in out.iterdir():
        if p.is_file():
            p.unlink()
    started = time.monotonic()
    summary = {'schema': 'gooo-language-bridge/read-reset/v1', 'decision': 'FAIL_CLOSED',
               'status': 'OWNED_PROPOSAL_NOT_SUBMITTED_UPSTREAM', 'steps': [],
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    try:
        provenance = json.loads((PROPOSAL / 'provenance.json').read_text())
        for name, metadata in provenance['files'].items():
            if name == 'pkg/tcp/proxy.go':
                path = PROPOSAL / 'caller-proxy.go.txt'
            elif name.startswith('pkg/'):
                path = PROPOSAL / 'original' / name
            else:
                path = PROPOSAL / ('LICENSE.traefik' if name == 'LICENSE.md' else 'upstream-AGENTS.txt')
            data = path.read_bytes()
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if hashlib.sha256(data).hexdigest() != metadata['sha256'] or blob != metadata['blob']:
                raise ValueError('pinned source differs: ' + name)
        summary['source'] = provenance['revision']
        with tempfile.TemporaryDirectory(prefix='read-reset-') as temporary:
            work = Path(temporary)
            target = work / 'pkg/tcp'
            target.mkdir(parents=True)
            (work / 'go.mod').write_text('module evidence.local/readreset\n\ngo 1.27.0\n')
            for p in (PROPOSAL / 'original/pkg/tcp').glob('*.go'):
                shutil.copyfile(p, target / p.name)
            for p in (PROPOSAL / 'fixtures').glob('*.go'):
                shutil.copyfile(p, target / p.name)

            def run(label, command, expected=0, cwd=work, environment=env):
                p = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, timeout=180)
                (out / (label + '.stdout')).write_bytes(p.stdout)
                (out / (label + '.stderr')).write_bytes(p.stderr)
                summary['steps'].append({'label': label, 'command': command, 'exit_code': p.returncode})
                if p.returncode != expected:
                    raise ValueError(label + ' exit code differs')
                return p.stdout

            command = ['go', 'test', '-json', './pkg/tcp', '-count=1', '-timeout=20s']
            before = observations(run('before', command, expected=1), CORRECTED)
            run('patch-check', ['git', 'apply', '--check', str(PROPOSAL / 'proposal.patch')])
            run('patch', ['git', 'apply', str(PROPOSAL / 'proposal.patch')])
            formatted = run('format', ['gofmt', '-l'] + [str(p) for p in sorted(target.glob('*.go'))])
            if formatted.strip():
                raise ValueError('proposed criterion or fixture needs formatting')
            after = observations(run('after', command), set())
            race = observations(run('race', command[:2] + ['-race'] + command[2:]), set())
            for id in IDS:
                if (before[id]['observation'] != after[id]['observation']
                        or before[id]['expected'] != after[id]['expected']
                        or race[id]['observation'] != after[id]['observation']):
                    raise ValueError('native input or expected label differs')
            windows = dict(env, GOOS='windows', GOARCH='amd64', CGO_ENABLED='0')
            run('windows-compile', ['go', 'test', '-c', '-o', str(work / 'tcp.test.exe'), './pkg/tcp'], environment=windows)
            summary.update(windows_compile=True, windows_runtime_tested=False)

            rows = [after[id] for id in sorted(IDS)]
            case_path = out / 'cases.json'
            case_path.write_text(json.dumps({'schema': 'gooo/body-composition-cases/v1', 'cases': [
                {'inputs': {KEY: r['observation']}, 'expected': {KEY: r['expected']}} for r in rows]}, indent=2) + '\n')
            binary = str(Path(args.gooo).resolve())
            version = json.loads(run('compiler', [binary, 'version', '--build', '--json']))
            if version.get('version') != '0.6.38-dev':
                raise ValueError('compiler version differs')
            receipt = json.loads(run('execution', [binary, 'package', 'execute', '--json', '--cases',
                                                  str(case_path), 'gooo.workspace.json'], cwd=BRIDGE))
            runtime = receipt.get('result', {}).get('runtime', {})
            if (receipt.get('decision') != 'PASS' or receipt.get('cases_digest') != digest(case_path)
                    or receipt.get('manifest_digest') != digest(BRIDGE / 'gooo.workspace.json')
                    or any(type(runtime.get(k)) is not int or runtime[k] != 16 for k in ('finite_passed', 'finite_total'))):
                raise ValueError('missing complete source-bound Gooo PASS')
            traces = runtime['traces']
            if (len(traces) != 16 or any(type(t['case_index']) is not int for t in traces)
                    or {t['case_index'] for t in traces} != set(range(16))):
                raise ValueError('Gooo case identity differs')
            for trace in traces:
                row = rows[trace['case_index']]
                if len(trace['deliveries']) != 1:
                    raise ValueError('ambiguous Gooo delivery')
                d = trace['deliveries'][0]
                if (d['activity_id'] != ACTIVITY or d['input'] != row['observation']
                        or d['actual'] != row['expected'] or d['expected'] != row['expected'] or d['passed'] is not True
                        or any(type(d['input'][k]) is not bool for k in ('has_reset', 'has_error'))):
                    raise ValueError('Gooo decision or native input differs')
                row.update(original=before[row['id']]['actual'], proposed=row['actual'], gooo=d['actual'])
            (out / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
            summary.update(decision='PASS', cases=16, original_mismatches=5, proposed_matches=16,
                           gooo_matches=16, real_loopback_cases=1, go=run('go-version', ['go', 'version']).decode().strip())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + list(PROPOSAL.rglob('*')) + list(BRIDGE.iterdir()) + [Path(__file__)]
        summary['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)
                             if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
