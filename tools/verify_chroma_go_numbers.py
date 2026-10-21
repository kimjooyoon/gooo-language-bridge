"""Reproduce the Go imaginary-literal fix against pinned original/patch sources."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = 'ef614fb8afe8ccf3f2b2cb45117c543a3ce8832b'
PATCH = '9eeba90bf714797853d60a5e815f8db33c00ae35'
FIXTURE = 'lexers/testdata/go/prefixed_imaginary'
TEST = 'TestLexers/Go/testdata/go/prefixed_imaginary.actual'
PROBE = ROOT / 'tests/fixtures/chroma_go_numbers.go'


def check_rows(before, after):
    if len(before) != 18 or len(after) != 18 or len({r['literal'] for r in after}) != 18:
        raise ValueError('unexpected literal domain')
    corrected, controls, imaginary = [], [], 0
    for b, a in zip(before, after):
        literal = a['literal']
        if b['literal'] != literal or b['native'] != a['native'] or len(a['native']) != 1:
            raise ValueError('native input or scanner result differs')
        if a['native'][0]['value'] != literal or a['native'][0]['type'] not in ('IMAG', 'INT', 'FLOAT'):
            raise ValueError('native scanner did not recognize one complete numeric literal')
        if len(a['chroma']) != 1 or a['chroma'][0]['value'] != literal:
            raise ValueError('patched lexer splits a numeric literal')
        if a['native'][0]['type'] == 'IMAG':
            imaginary += 1
            if a['chroma'][0]['type'] != 'LiteralNumber':
                raise ValueError('imaginary literal classification differs')
        if b['chroma'] != a['chroma']:
            if (a['native'][0]['type'] != 'IMAG' or len(b['chroma']) != 2
                    or b['chroma'][0]['value'] != literal[:-1]
                    or not b['chroma'][0]['type'].startswith('LiteralNumber')
                    or b['chroma'][1] != {'type': 'NameOther', 'value': 'i'}):
                raise ValueError('unexpected baseline difference')
            corrected.append(literal)
        else:
            controls.append(literal)
    if len(corrected) != 11 or len(controls) != 7 or imaginary != 14:
        raise ValueError('corrected/control/scanner counts differ')
    return {'corrected': corrected, 'unchanged_controls': controls, 'native_imaginary': imaginary}


def check_test_events(raw, outcome):
    events = [json.loads(line) for line in raw.splitlines()]
    terminal = [e['Action'] for e in events if e.get('Test') == TEST and e['Action'] in ('pass', 'fail', 'skip')]
    if terminal != [outcome]:
        raise ValueError('missing or unexpected regression test outcome')


def main():
    out = ROOT / 'evidence/chroma-go-numbers'
    out.mkdir(parents=True, exist_ok=True)
    for path in out.iterdir():
        if path.is_file():
            path.unlink()
    started = time.monotonic()
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    summary = {'schema': 'gooo-language-bridge/chroma-go-numbers/v1', 'decision': 'FAIL_CLOSED',
               'original': BASE, 'patch': PATCH, 'steps': [],
               'upstream_pr': 'https://github.com/alecthomas/chroma/pull/1411',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    try:
        with tempfile.TemporaryDirectory(prefix='chroma-go-numbers-') as temporary:
            work = Path(temporary)

            def run(label, command, expected=0):
                result = subprocess.run(command, cwd=work, env=env, capture_output=True, timeout=180)
                (out / (label + '.stdout')).write_bytes(result.stdout)
                (out / (label + '.stderr')).write_bytes(result.stderr)
                summary['steps'].append({'label': label, 'command': command, 'exit_code': result.returncode})
                if result.returncode != expected:
                    raise ValueError(label + ' exit code differs')
                return result.stdout

            run('init', ['git', 'init', '-q'])
            run('fetch-original', ['git', 'fetch', '--depth=1', 'https://github.com/alecthomas/chroma.git', BASE])
            run('fetch-patch', ['git', 'fetch', '--depth=1', 'https://github.com/kimjooyoon/chroma.git', PATCH])
            run('checkout-patch', ['git', 'checkout', '--detach', PATCH])
            actual, expected = (work / (FIXTURE + suffix) for suffix in ('.actual', '.expected'))
            source, golden = actual.read_bytes(), expected.read_bytes()
            (out / 'fixture.actual').write_bytes(source)
            (out / 'fixture.expected').write_bytes(golden)
            tokens = json.loads(golden)
            if (len(tokens) != 36 or any(t['type'] == 'Error' for t in tokens)
                    or ''.join(t['value'] for t in tokens).encode() != source):
                raise ValueError('golden tokens do not preserve the exact fixture')
            literals = source.decode().splitlines()
            if len(literals) != 18:
                raise ValueError('expected 18 literal lines')
            compile_source = out / 'native_literals.go'
            compile_source.write_text('package numbers\nconst (\n' + ''.join(
                ' n%d = %s\n' % (i, value) for i, value in enumerate(literals)) + ')\n')
            run('native-compile', ['go', 'test', str(compile_source)])
            run('checkout-original', ['git', 'checkout', '--detach', BASE])
            actual.write_bytes(source)
            expected.write_bytes(golden)
            before = json.loads(run('before-tokens', ['go', 'run', str(PROBE), str(actual)]))
            regex = '^TestLexers$/^Go$/^testdata/go/prefixed_imaginary.actual$'
            check_test_events(run('before-regression', ['go', 'test', '-json', './lexers', '-run', regex,
                                                       '-count=1', '-timeout=60s'], expected=1), 'fail')
            actual.unlink()
            expected.unlink()
            run('restore-patch', ['git', 'checkout', '--detach', PATCH])
            if run('source-identity', ['git', 'rev-parse', 'HEAD']).decode().strip() != PATCH:
                raise ValueError('patch identity differs')
            after = json.loads(run('after-tokens', ['go', 'run', str(PROBE), str(actual)]))
            summary.update(check_rows(before, after))
            check_test_events(run('after-regression', ['go', 'test', '-json', './lexers', '-run', regex,
                                                      '-count=1', '-timeout=60s']), 'pass')
            check_test_events(run('race', ['go', 'test', '-race', '-json', './lexers', '-run', '^TestLexers$/^Go$',
                                          '-count=1', '-timeout=90s']), 'pass')
            run('full-tests', ['go', 'test', './...', '-timeout=120s'])
            summary['go'] = run('go-version', ['go', 'version']).decode().strip()
            summary.update(decision='PASS', literals=18, fixture_tokens=36,
                           fixture_sha256=hashlib.sha256(source).hexdigest(),
                           golden_sha256=hashlib.sha256(golden).hexdigest())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + [Path(__file__), PROBE]
        summary['sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(paths) if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
