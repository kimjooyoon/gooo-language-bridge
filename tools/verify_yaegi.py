"""Reproduce the submitted Yaegi regression before and after the pinned fix."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = 'fcb76d1ece0c3edc2548c39aa5b170475d2261bb'
FIX = 'cb44dbddff3d6b32bc08aa43e0aab0e51c1fbf68'
TEST = 'interp/interp_issue_1736_test.go'
NAME = 'TestOperatorAssignmentToBinaryInterfaceSlice'


def run(command, cwd, timeout=120):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def check_events(result, expected_action, count):
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    leaves = [e for e in events if e.get('Action') in ('pass', 'fail', 'skip')
              and e.get('Test', '').count('/') == 2]
    return (len(leaves) == count and all(e['Action'] == expected_action for e in leaves)
            and result.returncode == (1 if expected_action == 'fail' else 0))


def main():
    out = ROOT / 'evidence/yaegi-1736'
    out.mkdir(parents=True, exist_ok=True)
    for previous in out.glob('*'):
        if previous.is_file():
            previous.unlink()
    summary = {'schema': 'gooo-language-bridge/upstream-regression/v1',
               'decision': 'FAIL_CLOSED', 'base': BASE, 'fix': FIX,
               'upstream_pr': 'https://github.com/traefik/yaegi/pull/1738'}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='yaegi-regression-') as temporary:
            work = Path(temporary)
            for command in (['git', 'init', '-q'],
                            ['git', 'fetch', '--depth=2', 'https://github.com/kimjooyoon/yaegi.git', FIX],
                            ['git', 'checkout', '--detach', FIX]):
                result = run(command, work)
                if result.returncode:
                    raise ValueError(result.stderr)
            identity = run(['git', 'rev-parse', 'HEAD'], work)
            if identity.stdout.strip() != FIX:
                raise ValueError('fixed revision mismatch')
            test_source = (work / TEST).read_bytes()
            summary['test_sha256'] = hashlib.sha256(test_source).hexdigest()
            summary['go'] = run(['go', 'version'], work).stdout.strip()
            for label, revision, pattern, action, count, race in (
                ('before', BASE, NAME + '/(string_addition|integer_addition|integer_negation|integer_complement)$', 'fail', 8, False),
                ('after', FIX, '^' + NAME + '$', 'pass', 10, False),
                ('race', FIX, '^' + NAME + '$', 'pass', 10, True),
            ):
                (work / TEST).unlink(missing_ok=True)
                checkout = run(['git', 'checkout', '--detach', revision], work)
                if checkout.returncode:
                    raise ValueError(checkout.stderr)
                (work / TEST).write_bytes(test_source)
                command = ['go', 'test', '-json', './interp', '-run', pattern, '-count=1', '-timeout=60s']
                if race:
                    command.append('-race')
                result = run(command, work)
                (out / (label + '.jsonl')).write_text(result.stdout)
                (out / (label + '.stderr')).write_text(result.stderr)
                summary[label] = {'exit_code': result.returncode, 'leaf_cases': count,
                                  'expected_action': action, 'command': command}
                if not check_events(result, action, count):
                    raise ValueError(label + ' did not match the required finite test events')
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
