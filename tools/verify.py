"""Bounded independent observations; no network or model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'bridges/python-floor'


def cases():
    return {'schema': 'gooo/body-composition-cases/v1', 'cases': [
        {'inputs': {'bridge/python:FloorDivide.input0': a,
                    'bridge/python:FloorDivide.input1': b},
         'expected': {'bridge/python:FloorDivide': a // b}}
        for a in range(-7, 8) for b in range(-4, 5) if b]}


def accepted(receipt, code):
    runtime = receipt.get('result', {}).get('runtime', {})
    return (type(code) is int and code == 0 and receipt.get('decision') == 'PASS'
            and type(runtime.get('finite_total')) is int
            and type(runtime.get('finite_passed')) is int
            and runtime['finite_total'] == 120 and runtime['finite_passed'] == 120)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    out = ROOT / 'evidence'
    out.mkdir(exist_ok=True)
    # Remove prior results so interrupted runs cannot expose an old success.
    for name in ('summary.json', 'execution.json', 'stderr.txt', 'compiler.json'):
        (out / name).unlink(missing_ok=True)
    binary = str(Path(args.gooo).resolve())
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    started = time.monotonic()
    summary = {'schema': 'gooo-language-bridge/run/v1', 'decision': 'FAIL_CLOSED',
               'python': platform.python_version(), 'implementation': platform.python_implementation(),
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    try:
        version = subprocess.run([binary, 'version', '--build', '--json'],
                                 capture_output=True, timeout=30, env=env)
        (out / 'compiler.json').write_bytes(version.stdout)
        identity = json.loads(version.stdout)
        if version.returncode or identity.get('version') != '0.6.38-dev':
            raise ValueError('compiler version mismatch')
        (out / 'cases.json').write_text(json.dumps(cases(), indent=2) + '\n')
        command = [binary, 'package', 'execute', '--json', '--cases',
                   str(out / 'cases.json'), 'gooo.workspace.json']
        result = subprocess.run(command, cwd=BRIDGE, capture_output=True, timeout=480, env=env)
        (out / 'execution.json').write_bytes(result.stdout)
        (out / 'stderr.txt').write_bytes(result.stderr)
        summary['exit_code'] = result.returncode
        if not accepted(json.loads(result.stdout), result.returncode):
            raise ValueError('receipt does not establish all 120 finite comparisons')
        summary['decision'] = 'PASS'
        summary['finite_passed'] = summary['finite_total'] = 120
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = sorted(BRIDGE.glob('*')) + sorted(out.glob('*')) + [Path(__file__)]
        summary['sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in paths if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
