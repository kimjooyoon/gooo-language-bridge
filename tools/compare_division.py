"""Compare native Go, native Python and fresh Gooo observations on one domain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

try:
    from .verify import BRIDGE, ROOT, accepted, cases
except ImportError:
    from verify import BRIDGE, ROOT, accepted, cases

ACTIVITY = 'urn:gooo:bridge:python:floor-divide'


def comparison_rows(case_rows, native, receipt):
    if not accepted(receipt, 0):
        raise ValueError('missing finite Gooo PASS')
    observations = {}
    for row in native:
        if any(type(row.get(key)) is not int for key in ('a', 'b', 'quotient', 'remainder')):
            raise ValueError('non-integer native observation')
        a, b, q, r = (row[key] for key in ('a', 'b', 'quotient', 'remainder'))
        if not b or a != b * q + r or abs(r) >= abs(b) or (r and (r < 0) != (a < 0)):
            raise ValueError('native result violates truncating-division invariants')
        if (a, b) in observations:
            raise ValueError('duplicate native input pair')
        observations[a, b] = q
    traces = receipt['result']['runtime']['traces']
    by_index = {}
    for trace in traces:
        index = trace['case_index']
        if type(index) is not int or index in by_index:
            raise ValueError('invalid or duplicate Gooo case index')
        by_index[index] = trace
    if len(observations) != len(case_rows) or set(by_index) != set(range(len(case_rows))):
        raise ValueError('missing or extra observations')
    result = []
    for index, case in enumerate(case_rows):
        a = case['inputs']['bridge/python:FloorDivide.input0']
        b = case['inputs']['bridge/python:FloorDivide.input1']
        expected = a // b
        deliveries = by_index[index]['deliveries']
        if len(deliveries) != 1:
            raise ValueError('ambiguous Gooo delivery')
        delivery = deliveries[0]
        inputs = delivery['inputs']
        if (delivery['activity_id'] != ACTIVITY or len(inputs) != 2
                or any(type(p['value']) is not int for p in inputs)
                or [(p['port'], p['value'], p['entity_id']) for p in inputs] != [
                    ('input0', a, 'urn:gooo:type:integer'), ('input1', b, 'urn:gooo:type:integer')]):
            raise ValueError('Gooo delivery identity or inputs differ')
        actual = delivery['actual']
        if (type(actual) is not int or actual != expected or delivery['passed'] is not True
                or type(delivery['expected']) is not int or delivery['expected'] != expected):
            raise ValueError('Gooo output differs from independent Python floor division')
        if (a, b) not in observations:
            raise ValueError('native input domain differs')
        result.append({'a': a, 'b': b, 'go_quotient': observations[a, b],
                       'python_floor': expected, 'gooo_actual': actual})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    out = ROOT / 'evidence/division-comparison'
    out.mkdir(parents=True, exist_ok=True)
    for path in out.glob('*'):
        if path.is_file():
            path.unlink()
    summary = {'schema': 'gooo-language-bridge/division-comparison/v1', 'decision': 'FAIL_CLOSED'}
    started = time.monotonic()
    try:
        bridge = subprocess.run([sys.executable, str(ROOT / 'tools/verify.py'), '--gooo', args.gooo],
                                cwd=ROOT, capture_output=True, timeout=600)
        (out / 'bridge.stdout').write_bytes(bridge.stdout)
        (out / 'bridge.stderr').write_bytes(bridge.stderr)
        if bridge.returncode:
            raise ValueError('fresh Gooo verification failed')
        case_rows = cases()['cases']
        pairs = [{'a': row['inputs']['bridge/python:FloorDivide.input0'],
                  'b': row['inputs']['bridge/python:FloorDivide.input1']} for row in case_rows]
        env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
        native = subprocess.run(['go', 'run', str(ROOT / 'examples/division-reference/main.go')],
                                cwd=ROOT, input=json.dumps(pairs).encode(), capture_output=True,
                                timeout=60, env=env)
        (out / 'go.stdout').write_bytes(native.stdout)
        (out / 'go.stderr').write_bytes(native.stderr)
        summary['native_exit_code'] = native.returncode
        if native.returncode:
            raise ValueError('native Go reference failed')
        receipt = json.loads((ROOT / 'evidence/execution.json').read_text())
        for field, path in [('cases_digest', ROOT / 'evidence/cases.json'),
                            ('manifest_digest', BRIDGE / 'gooo.workspace.json')]:
            if receipt[field] != 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('receipt digest mismatch')
        rows = comparison_rows(case_rows, json.loads(native.stdout), receipt)
        (out / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
        summary.update(decision='PASS', cases=len(rows),
                       go_python_differences=sum(r['go_quotient'] != r['python_floor'] for r in rows),
                       gooo_python_matches=sum(r['gooo_actual'] == r['python_floor'] for r in rows),
                       activity_id=ACTIVITY, receipt_cases_digest=receipt['cases_digest'],
                       go=subprocess.check_output(['go', 'version'], env=env, timeout=10).decode().strip())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = sorted(out.glob('*')) + [ROOT / 'evidence/execution.json',
                ROOT / 'examples/division-reference/main.go', BRIDGE / 'main.gooo', Path(__file__)]
        summary['sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in paths if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
