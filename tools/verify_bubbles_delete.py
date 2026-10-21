"""Compare eight native textarea deletions with a source-owned Gooo activity."""
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
BRIDGE = ROOT / 'bridges/forward-delete'
FIXTURE = ROOT / 'tests/fixtures/bubbles_delete_witness_test.go'
BASE = 'c3bde0d166c2ca607d9864493453fd77bdcae7e4'
PATCH = 'c328d151ef791e224ebff53d664fbfa7586796fe'
KEY = 'bridge/editing:Delete'
ACTIVITY = 'urn:gooo:editing:delete-forward-scalar'
CORRECTED = {'last-character', 'only-character', 'wide-character'}
IDS = CORRECTED | {'middle-character', 'line-end', 'empty-line', 'last-line-character', 'last-line-end'}


def observations(raw, failures):
    rows, terminals = {}, {}
    for line in raw.splitlines():
        event = json.loads(line)
        output = event.get('Output', '')
        if 'WITNESS ' in output:
            row = json.loads(output.split('WITNESS ', 1)[1])
            if row['id'] in rows:
                raise ValueError('duplicate native witness')
            rows[row['id']] = row
        name = event.get('Test', '')
        if name.startswith('TestBridgeForwardDelete/') and event['Action'] in ('pass', 'fail', 'skip'):
            id = name.split('/', 1)[1]
            if id in terminals:
                raise ValueError('duplicate native terminal event')
            terminals[id] = event['Action']
    if set(rows) != IDS or set(terminals) != IDS:
        raise ValueError('native case domain differs')
    for id, row in rows.items():
        if (terminals[id] != ('fail' if id in failures else 'pass')
                or (row['actual'] != row['expected']) != (id in failures)):
            raise ValueError('native failure set differs')
        value = row['input']
        if (set(value) != {'text', 'byte_column'} or type(value['text']) is not str
                or type(value['byte_column']) is not int or type(row['rune_column']) is not int
                or type(row['expected']) is not str or type(row['actual']) is not str):
            raise ValueError('native input/output types differ')
        text, column = value['text'].encode('utf-8'), value['byte_column']
        if not 0 <= column <= len(text) <= 1024:
            raise ValueError('native text or cursor outside bounded domain')
        prefix = text[:column].decode('utf-8')
        if '\n' in prefix or len(prefix) != row['rune_column']:
            raise ValueError('cursor is not a first-line scalar boundary')
    return rows


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    out = ROOT / 'evidence/forward-delete'
    out.mkdir(parents=True, exist_ok=True)
    for path in out.iterdir():
        if path.is_file():
            path.unlink()
    started = time.monotonic()
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    summary = {'schema': 'gooo-language-bridge/forward-delete/v1', 'decision': 'FAIL_CLOSED',
               'original': BASE, 'patch': PATCH, 'steps': [],
               'upstream_pr': 'https://github.com/charmbracelet/bubbles/pull/1072',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    try:
        provenance = json.loads((BRIDGE / 'provenance.json').read_text())
        if (provenance['original_revision'] != BASE or provenance['submitted_revision'] != PATCH
                or provenance['fixture_sha256'] != hashlib.sha256(FIXTURE.read_bytes()).hexdigest()):
            raise ValueError('provenance source or fixture differs')
        with tempfile.TemporaryDirectory(prefix='bubbles-delete-') as temporary:
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
            run('fetch-original', ['git', 'fetch', '--depth=1', 'https://github.com/charmbracelet/bubbles.git', BASE])
            run('fetch-patch', ['git', 'fetch', '--depth=1', 'https://github.com/kimjooyoon/bubbles.git', PATCH])
            rows_by_revision = []
            command = ['go', 'test', '-json', './textarea', '-run', '^TestBridgeForwardDelete$', '-count=1', '-timeout=45s']
            for label, rev, failures in [('before', BASE, CORRECTED), ('after', PATCH, set())]:
                run(label + '-checkout', ['git', 'checkout', '--detach', rev])
                if run(label + '-identity', ['git', 'rev-parse', 'HEAD']).decode().strip() != rev:
                    raise ValueError('native source revision differs')
                for name in ('textarea/textarea.go', 'go.mod', 'go.sum', 'LICENSE'):
                    shutil.copyfile(work / name, out / (label + '-' + name.replace('/', '-')))
                shutil.copyfile(FIXTURE, work / 'textarea/bridge_delete_witness_test.go')
                rows_by_revision.append(observations(run(label, command, 1 if failures else 0), failures))
            before, after = rows_by_revision
            race = observations(run('race', command[:2] + ['-race'] + command[2:]), set())
            for id in IDS:
                for key in ('input', 'rune_column', 'expected'):
                    if before[id][key] != after[id][key] or race[id][key] != after[id][key]:
                        raise ValueError('native input or expectation differs')
            rows = [after[id] for id in sorted(IDS)]
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
                    or any(type(runtime.get(k)) is not int or runtime[k] != 8 for k in ('finite_total', 'finite_passed'))):
                raise ValueError('missing complete source-bound Gooo PASS')
            traces = runtime['traces']
            if (len(traces) != 8 or any(type(t['case_index']) is not int for t in traces)
                    or {t['case_index'] for t in traces} != set(range(8))):
                raise ValueError('Gooo case domain differs')
            for trace in traces:
                row = rows[trace['case_index']]
                if len(trace['deliveries']) != 1:
                    raise ValueError('ambiguous Gooo delivery')
                d = trace['deliveries'][0]
                if (d['activity_id'] != ACTIVITY or d['input'] != row['input']
                        or type(d['input']['byte_column']) is not int or type(d['input']['text']) is not str
                        or d['actual'] != row['expected'] or d['expected'] != row['expected'] or d['passed'] is not True):
                    raise ValueError('Gooo input, identity or output differs')
                row.update(original=before[row['id']]['actual'], patched=row['actual'], gooo=d['actual'])
            (out / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
            summary.update(decision='PASS', cases=8, original_mismatches=3, patched_matches=8,
                           gooo_matches=8, compiler_sha256=digest(Path(binary)),
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
