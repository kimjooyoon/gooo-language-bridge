"""Verify the immutable Chroma submission independently of upstream approval."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'f2224b4a0bd96f64da4cd9a92b293d81aaaf71cd'


def main():
    out = ROOT / 'evidence/chroma-gooo'
    out.mkdir(parents=True, exist_ok=True)
    for path in out.glob('*'):
        if path.is_file():
            path.unlink()
    summary = {'schema': 'gooo-language-bridge/upstream-checks/v1',
               'source': SOURCE, 'decision': 'FAIL_CLOSED',
               'upstream_pr': 'https://github.com/alecthomas/chroma/pull/1410',
               'steps': []}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='chroma-gooo-') as temporary:
            work = Path(temporary)
            commands = [
                ('init', ['git', 'init', '-q']),
                ('fetch', ['git', 'fetch', '--depth=1', 'https://github.com/kimjooyoon/chroma.git', SOURCE]),
                ('checkout', ['git', 'checkout', '--detach', SOURCE]),
                ('tests', ['go', 'test', './...', '-timeout=120s']),
                ('race', ['go', 'test', '-race', './lexers', '-run', '^TestLexers/Gooo/', '-count=1', '-timeout=60s']),
                ('generate', ['go', 'generate', './lexers']),
                ('generated-diff', ['git', 'diff', '--exit-code', '--', 'lexers/lexers_gen.go']),
            ]
            for name, command in commands:
                result = subprocess.run(command, cwd=work, capture_output=True, timeout=180)
                (out / (name + '.stdout')).write_bytes(result.stdout)
                (out / (name + '.stderr')).write_bytes(result.stderr)
                summary['steps'].append({'name': name, 'command': command, 'exit_code': result.returncode})
                if result.returncode:
                    raise ValueError(name + ' failed')
                if name == 'checkout':
                    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=work, timeout=10).decode().strip()
                    if actual != SOURCE:
                        raise ValueError('source identity mismatch')
                    summary['go'] = subprocess.check_output(['go', 'version'], cwd=work, timeout=10).decode().strip()
            bundled = ROOT / 'examples/highlight-gooo/gooo.xml'
            if bundled.read_bytes() != (work / 'lexers/embedded/gooo.xml').read_bytes():
                raise ValueError('consumer lexer differs from the submitted source')
            summary['consumer_lexer_sha256'] = hashlib.sha256(bundled.read_bytes()).hexdigest()
            fixtures = work / 'lexers/testdata/gooo'
            summary['fixtures'] = []
            for actual in sorted(fixtures.glob('*.actual')):
                expected = actual.with_suffix('.expected')
                tokens = json.loads(expected.read_text())
                if any(token['type'] == 'Error' for token in tokens):
                    raise ValueError('Error token in ' + actual.name)
                if ''.join(token['value'] for token in tokens) != actual.read_text():
                    raise ValueError('source reconstruction mismatch')
                summary['fixtures'].append({'name': actual.name, 'tokens': len(tokens),
                    'source_sha256': hashlib.sha256(actual.read_bytes()).hexdigest(),
                    'expected_sha256': hashlib.sha256(expected.read_bytes()).hexdigest()})
            if len(summary['fixtures']) != 2:
                raise ValueError('expected exactly two source fixtures')
            summary['decision'] = 'PASS'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        summary['sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(out.glob('*')) if p.is_file()}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
