"""Compare first-error work and valid output with the published v0.1.0 source."""
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / 'examples/highlight-gooo'
BASE = 'c1a7933408d9f33c5fd53ca88ae713a0838c2ecd'


def measurements(raw):
    pattern = (r'^BenchmarkRejectInvalidSource-\d+\s+1\s+([0-9.]+) ns/op\s+'
               r'(\d+) B/op\s+(\d+) allocs/op\s*$')
    rows = [{'ns_per_op': float(ns), 'bytes_per_op': int(size), 'allocs_per_op': int(count)}
            for ns, size, count in re.findall(pattern, raw.decode(), re.MULTILINE)]
    if len(rows) != 3:
        raise ValueError('expected three single-iteration benchmark observations')
    return rows


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = ROOT / 'evidence/highlighter-first-error'
    out.mkdir(parents=True, exist_ok=True)
    for path in out.iterdir():
        if path.is_file():
            path.unlink()
    started = time.monotonic()
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    summary = {'schema': 'gooo-language-bridge/highlighter-first-error/v1', 'decision': 'FAIL_CLOSED',
               'original': BASE, 'steps': [], 'commit': os.environ.get('GITHUB_SHA'),
               'run_id': os.environ.get('GITHUB_RUN_ID')}
    try:
        with tempfile.TemporaryDirectory(prefix='highlight-gooo-') as temporary:
            work = Path(temporary)

            def run(label, command, cwd, expected=0, input=None, environment=env):
                result = subprocess.run(command, cwd=cwd, env=environment, input=input,
                                        capture_output=True, timeout=180)
                (out / (label + '.stdout')).write_bytes(result.stdout)
                (out / (label + '.stderr')).write_bytes(result.stderr)
                summary['steps'].append({'label': label, 'command': command, 'exit_code': result.returncode})
                if result.returncode != expected:
                    raise ValueError(label + ' exit code differs')
                return result

            run('init', ['git', 'init', '-q'], work)
            run('fetch-original', ['git', 'fetch', '--depth=1',
                'https://github.com/kimjooyoon/gooo-language-bridge.git', BASE], work)
            run('checkout-original', ['git', 'checkout', '--detach', BASE], work)
            original = work / 'examples/highlight-gooo'
            benchmark = CONSUMER / 'benchmark_test.go'
            (original / 'benchmark_test.go').write_bytes(benchmark.read_bytes())
            (out / 'original-main.go').write_bytes((original / 'main.go').read_bytes())
            command = ['go', 'test', '-run', '^$', '-bench', '^BenchmarkRejectInvalidSource$',
                       '-benchtime=1x', '-count=3']
            before = measurements(run('before-benchmark', command, original).stdout)
            after = measurements(run('after-benchmark', command, CONSUMER).stdout)
            baseline_bytes = statistics.median(r['bytes_per_op'] for r in before)
            current_bytes = statistics.median(r['bytes_per_op'] for r in after)
            if not 0 < current_bytes < baseline_bytes / 2:
                raise ValueError('first-error allocation reduction was not reproduced')
            summary.update(before=before, after=after,
                           median_allocation_reduction=round(1 - current_bytes / baseline_bytes, 6))

            binaries = []
            for label, cwd in [('before', original), ('after', CONSUMER)]:
                binary = work / ('highlight-' + label)
                run(label + '-build', ['go', 'build', '-o', str(binary), '.'], cwd)
                binaries.append(str(binary))
            samples = {'floor': (ROOT / 'bridges/python-floor/main.gooo').read_bytes(), 'empty': b'',
                       'html-escape': b'entity Text id "<script>alert(1)</script>"\n'}
            for name, newline in [('LF', '\n'), ('CRLF', '\r\n'), ('CR', '\r')]:
                samples[name] = ('activity 인사(Text) -> Text computes `// # /* raw' + newline
                                 + 'return input`' + newline).encode()
            summary['valid_outputs'] = []
            for name, source in samples.items():
                (out / (name + '.gooo')).write_bytes(source)
                for format in ('html', 'json'):
                    outputs = [run(label + '-' + name + '-' + format,
                                   [binary, '-format', format, '-'], work, input=source).stdout
                               for label, binary in zip(('before', 'after'), binaries)]
                    if outputs[0] != outputs[1]:
                        raise ValueError('valid output changed: ' + name + '/' + format)
                    if format == 'json':
                        tokens = json.loads(outputs[1]) or []
                        if ''.join(t['value'] for t in tokens).encode() != source:
                            raise ValueError('JSON source reconstruction differs')
                    summary['valid_outputs'].append(name + '/' + format)
            bad = b'?' * (128 << 10)
            (out / 'invalid.gooo').write_bytes(bad)
            for label, binary in zip(('before', 'after'), binaries):
                failed = run(label + '-invalid', [binary, '-format', 'json', '-'], work, expected=1, input=bad)
                if failed.stdout or not failed.stderr.startswith(b'unrecognised source character '):
                    raise ValueError('invalid input no longer fails before output')
                if label == 'after' and failed.stderr != b'unrecognised source character "?"\n':
                    raise ValueError('first raw Error diagnostic differs')

            minimum = dict(env, GOTOOLCHAIN='go1.25.0')
            version = run('minimum-version', ['go', 'version'], CONSUMER, environment=minimum)
            if 'go1.25.0 ' not in version.stdout.decode():
                raise ValueError('minimum toolchain identity differs')
            run('minimum-tests', ['go', 'test', '-count=1', './...'], CONSUMER, environment=minimum)
            summary['minimum_go'] = version.stdout.decode().strip()
            summary['benchmark_go'] = run('go-version', ['go', 'version'], CONSUMER).stdout.decode().strip()
            summary.update(decision='PASS', invalid_input_bytes=len(bad),
                           valid_output_comparisons=len(summary['valid_outputs']),
                           timing_scope='Three single iterations per version on one malformed input; ns/op is observational, not a CI gate. B/op is total allocation, not peak RSS.')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + list(CONSUMER.glob('*.go')) + [Path(__file__),
                CONSUMER / 'go.mod', CONSUMER / 'go.sum', CONSUMER / 'gooo.xml', CONSUMER / 'provenance.json']
        summary['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)
                             if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
