"""Compare Go, Python, pinned GoLua and fresh Gooo on one bounded domain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

try:
    from .verify import BRIDGE, ROOT, accepted, cases
    from .compare_js import run_step
except ImportError:
    from verify import BRIDGE, ROOT, accepted, cases
    from compare_js import run_step

ACTIVITY = 'urn:gooo:bridge:python:floor-divide'
LUA = ROOT / 'examples/lua-division-reference'
EDGE_PAIRS = [{'a': -(1 << 63), 'b': -1}, {'a': (1 << 63) - 1, 'b': 1}, {'a': 1, 'b': 0}]


def lua_index(native):
    if type(native) is not list:
        raise ValueError('Lua observations must be an array')
    indexed = {}
    for row in native:
        if (type(row) is not dict or any(type(row.get(k)) is not int for k in ('a', 'b'))
                or (row['a'], row['b']) in indexed):
            raise ValueError('invalid or duplicate Lua input pair')
        indexed[row['a'], row['b']] = row
    return indexed


def include_lua(rows, native):
    indexed = lua_index(native)
    if len(indexed) != len(rows) or set(indexed) != {(r['a'], r['b']) for r in rows}:
        raise ValueError('Lua input domain differs')
    result = []
    for row in rows:
        observed = indexed[row['a'], row['b']]
        if (set(observed) != {'a', 'b', 'quotient'} or type(observed['quotient']) is not int
                or observed['quotient'] != row['python_floor']):
            raise ValueError('Lua floor observation differs on the bounded domain')
        result.append(dict(row, lua_floor=observed['quotient']))
    return result


def lua_edges(native):
    indexed = lua_index(native)
    if set(indexed) != {(p['a'], p['b']) for p in EDGE_PAIRS}:
        raise ValueError('Lua boundary domain differs')
    result = []
    for pair in EDGE_PAIRS:
        a, b = pair['a'], pair['b']
        row = indexed[a, b]
        output = {'a_decimal': str(a), 'b_decimal': str(b), 'in_gooo_domain': False}
        if not b:
            if (set(row) != {'a', 'b', 'error'} or type(row['error']) is not str
                    or 'divide by zero' not in row['error']):
                raise ValueError('Lua zero-divisor boundary differs')
            try:
                a // b
            except ZeroDivisionError as error:
                output.update(lua_error=row['error'], python_error=type(error).__name__)
        else:
            expected = -(1 << 63) if b == -1 else (1 << 63) - 1
            if set(row) != {'a', 'b', 'quotient'} or type(row['quotient']) is not int or row['quotient'] != expected:
                raise ValueError('Lua integer boundary differs')
            output.update(lua_floor_decimal=str(row['quotient']), python_floor_decimal=str(a // b),
                          same_integer_result=row['quotient'] == a // b)
        result.append(output)
    return result


def observe_lua(pairs, env, out, summary):
    provenance = json.loads((LUA / 'provenance.json').read_text())
    steps = summary['lua_steps'] = []
    for source, name in [('main.go', 'lua-observer.go'), ('go.mod', 'lua-observer.mod'),
                         ('go.sum', 'lua-observer.sum'), ('provenance.json', 'lua-provenance.json')]:
        (out / name).write_bytes((LUA / source).read_bytes())
    for name, inputs in [('lua-input.json', pairs), ('lua-edge-input.json', EDGE_PAIRS)]:
        (out / name).write_text(json.dumps(inputs) + '\n')
    with tempfile.TemporaryDirectory(prefix='gooo-lua-division-') as temporary:
        binary = str(Path(temporary) / 'observer')
        def run(label, command, timeout=120):
            return run_step(label, command, LUA, env, out, steps, timeout)
        module = json.loads(run('lua-module', ['go', 'mod', 'download', '-json',
                                               provenance['module'] + '@' + provenance['version']]))
        if (module.get('Origin', {}).get('Hash') != provenance['revision']
                or module.get('Version') != provenance['version'] or module.get('Sum') != provenance['sum']):
            raise ValueError('Lua module source binding differs')
        run('lua-build', ['go', 'build', '-mod=readonly', '-trimpath', '-o', binary, '.'])
        identity = json.loads(run('lua-identity', [binary, '--identity'], 10))
        if (any(identity.get(k) != provenance[k] for k in ('module', 'version', 'sum', 'lua_source'))
                or identity.get('go') != 'go1.27.3'
                or any(type(identity.get(k)) is not str or not identity[k] for k in ('os', 'arch'))):
            raise ValueError('Lua built observer identity differs')
        summary['lua_runtime'] = identity
        summary['lua_binary_sha256'] = 'sha256:' + hashlib.sha256(Path(binary).read_bytes()).hexdigest()
        native = json.loads(run('lua', [binary, '--input', str(out / 'lua-input.json')], 30))
        edges = lua_edges(json.loads(run('lua-edge', [binary, '--input', str(out / 'lua-edge-input.json')], 30)))
        rejected = [
            ('missing', b'[{"a":1}]', 'a and b must be int64 values'),
            ('overflow', b'[{"a":9223372036854775808,"b":1}]', 'cannot unmarshal number'),
            ('trailing', b'[{"a":1,"b":1}] null', 'expected one JSON array'),
        ]
        for name, raw, diagnostic in rejected:
            label = 'lua-invalid-' + name
            path = out / (label + '.json')
            path.write_bytes(raw)
            try:
                run(label, [binary, '--input', str(path)], 10)
            except ValueError:
                error = (out / (label + '.stderr')).read_text()
                if (steps[-1]['exit_code'] != 2 or (out / (label + '.stdout')).read_bytes()
                        or len(error.splitlines()) != 1 or diagnostic not in error):
                    raise ValueError('Lua malformed-input rejection differs: ' + name)
            else:
                raise ValueError('Lua observer accepted malformed input: ' + name)
        summary['lua_protocol_rejections'] = len(rejected)
    (out / 'lua-edge-rows.json').write_text(json.dumps(edges, indent=2) + '\n')
    return native, edges


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
    summary = {'schema': 'gooo-language-bridge/division-comparison/v1', 'decision': 'FAIL_CLOSED',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
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
        lua, edges = observe_lua(pairs, env, out, summary)
        rows = include_lua(rows, lua)
        (out / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
        summary.update(decision='PASS', cases=len(rows),
                       go_python_differences=sum(r['go_quotient'] != r['python_floor'] for r in rows),
                       gooo_python_matches=sum(r['gooo_actual'] == r['python_floor'] for r in rows),
                       lua_python_matches=sum(r['lua_floor'] == r['python_floor'] for r in rows),
                       excluded_lua_boundaries=len(edges),
                       excluded_integer_differences=sum(r.get('same_integer_result') is False for r in edges),
                       activity_id=ACTIVITY, receipt_cases_digest=receipt['cases_digest'],
                       go=subprocess.check_output(['go', 'version'], env=env, timeout=10).decode().strip())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = sorted(out.glob('*')) + [ROOT / 'evidence/execution.json',
                ROOT / 'examples/division-reference/main.go', BRIDGE / 'main.gooo', Path(__file__)] + list(LUA.glob('*'))
        summary['sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in paths if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
