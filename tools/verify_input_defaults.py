"""Compare typed input presence with a pinned Tengo runtime's map overrides."""
import argparse
import hashlib
import itertools
import json
import os
import shutil
from pathlib import Path
import tempfile
import time

try:
    from .compare_js import run_step
except ImportError:
    from compare_js import run_step

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'bridges/input-defaults'
NATIVE = ROOT / 'examples/tengo-defaults-reference'
KEY = 'bridge/defaults:Resolve'
ACTIVITY = 'urn:gooo:bridge:defaults:resolve'
INPUTS = {k: 'urn:gooo:bridge:defaults:' + k.replace('_', '-') for k in (
    'a_present', 'a_value', 'b_present', 'b_value', 'enabled_present', 'enabled_value')}
OUTPUTS = {k: 'urn:gooo:bridge:defaults:resolved-' + k for k in ('a', 'b', 'enabled')}
INPUT_TYPES = {k: (int if k in ('a_value', 'b_value') else bool) for k in INPUTS}
OUTPUT_TYPES = {'a': int, 'b': int, 'enabled': bool}


def corpus():
    rows = []
    # Missing fields follow non-default values, exercising reuse on the same Compiled.
    for a, b, enabled in itertools.product((-1, None, 0, 2), (-1, None, 0, 2), (False, None, True)):
        values = {'a': a, 'b': b, 'enabled': enabled}
        overrides = {k: v for k, v in values.items() if v is not None}
        semantic = {}
        for k, v in values.items():
            semantic[k + '_present'] = v is not None
            semantic[k + '_value'] = v if v is not None else (False if k == 'enabled' else 0)
        expected = dict(a=0, b=1, enabled=True)
        expected.update(overrides)
        id = '/'.join(k + ':' + ('missing' if v is None else str(v).lower()) for k, v in values.items())
        rows.append(dict(id=id, overrides=overrides, input=semantic, expected=expected))
    return rows


def typed(value, expected, types):
    return (type(value) is dict and set(value) == set(types)
            and all(type(value[k]) is kind and value[k] == expected[k] for k, kind in types.items()))


def native_rows(rows, native):
    if (type(native) is not list or len(native) != len(rows)
            or any(type(r) is not dict or set(r) != {'id', 'overrides', 'actual'} for r in native)
            or [r['id'] for r in native] != [r['id'] for r in rows]):
        raise ValueError('native case order/domain differs')
    for row, observed in zip(rows, native):
        kinds = {k: OUTPUT_TYPES[k] for k in row['overrides']}
        if (not typed(observed['overrides'], row['overrides'], kinds)
                or not typed(observed['actual'], row['expected'], OUTPUT_TYPES)):
            raise ValueError('native typed input/output differs')
    return native


def field_rows(fields, expected, ids, types):
    if (type(fields) is not list or len(fields) != len(ids)
            or any(type(f) is not dict or set(f) != {'id', 'name', 'value'} for f in fields)
            or {(f['name'], f['id']) for f in fields} != set(ids.items())):
        raise ValueError('semantic field identity differs')
    if any(type(f['value']) is not types[f['name']] or f['value'] != expected[f['name']] for f in fields):
        raise ValueError('semantic field type/value differs')


def compare(rows, native, receipt, cases_digest, manifest_digest):
    native_rows(rows, native)
    runtime = receipt.get('result', {}).get('runtime', {})
    if (receipt.get('decision') != 'PASS' or receipt.get('cases_digest') != cases_digest
            or receipt.get('manifest_digest') != manifest_digest
            or any(type(runtime.get(k)) is not int or runtime[k] != len(rows) for k in ('finite_total', 'finite_passed'))):
        raise ValueError('missing complete source-bound Gooo PASS')
    traces = runtime.get('traces', [])
    if (len(traces) != len(rows) or any(type(t.get('case_index')) is not int for t in traces)
            or {t['case_index'] for t in traces} != set(range(len(rows)))):
        raise ValueError('Gooo case domain differs')
    actual_values = {}
    for trace in traces:
        row = rows[trace['case_index']]
        deliveries = trace.get('deliveries', [])
        if len(deliveries) != 1:
            raise ValueError('ambiguous Gooo delivery')
        d = deliveries[0]
        if (d.get('activity_id') != ACTIVITY or d.get('passed') is not True
                or not typed(d.get('input'), row['input'], INPUT_TYPES)
                or not typed(d.get('actual'), row['expected'], OUTPUT_TYPES)
                or not typed(d.get('expected'), row['expected'], OUTPUT_TYPES)):
            raise ValueError('Gooo input/activity/value differs')
        field_rows(d.get('input_fields'), row['input'], INPUTS, INPUT_TYPES)
        field_rows(d.get('actual_fields'), row['expected'], OUTPUTS, OUTPUT_TYPES)
        actual_values[trace['case_index']] = d['actual']
    return [dict(row, native=observed['actual'], gooo=actual_values[i])
            for i, (row, observed) in enumerate(zip(rows, native))]


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def reset_counts(rows):
    counts = dict(a=0, b=0, enabled=0)
    defaults = dict(a=0, b=1, enabled=True)
    for previous, current in zip(rows, rows[1:]):
        for k, default in defaults.items():
            if (k not in current['overrides'] and previous['native'][k] != default
                    and current['native'][k] == default):
                counts[k] += 1
    if not all(counts.values()):
        raise ValueError('corpus does not exercise every field resetting after an override')
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    out = ROOT / 'evidence/input-defaults'
    out.mkdir(parents=True, exist_ok=True)
    for path in out.iterdir():
        if path.is_file():
            path.unlink()
    summary = dict(schema='gooo-language-bridge/input-defaults/v1', decision='FAIL_CLOSED',
                   commit=os.environ.get('GITHUB_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'), steps=[])
    started = time.monotonic()
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off', GOFLAGS='')
    def run(label, command, cwd=NATIVE, timeout=120):
        return run_step(label, command, cwd, env, out, summary['steps'], timeout)
    try:
        rows = corpus()
        if (len(rows) != 48 or len({r['id'] for r in rows}) != 48
                or len({json.dumps(r['overrides'], sort_keys=True) for r in rows}) != 48):
            raise ValueError('corpus does not establish 48 distinct input maps')
        inputs = [dict(id=r['id'], overrides=r['overrides']) for r in rows]
        (out / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        for source, name in [('main.go', 'native-source.go'), ('go.mod', 'native.mod'), ('go.sum', 'native.sum')]:
            (out / name).write_bytes((NATIVE / source).read_bytes())
        provenance = json.loads((BRIDGE / 'provenance.json').read_text())
        module = json.loads(run('module', ['go', 'mod', 'download', '-json', provenance['module'] + '@' + provenance['version']]))
        if (module.get('Origin', {}).get('Hash') != provenance['revision']
                or module.get('Version') != provenance['version'] or module.get('Sum') != provenance['sum']):
            raise ValueError('native module source binding differs')
        run('module-verify', ['go', 'mod', 'verify'])
        for name in ('LICENSE', 'go.mod'):
            shutil.copyfile(Path(module['Dir']) / name, out / ('upstream-' + name))
        with tempfile.TemporaryDirectory(prefix='gooo-tengo-defaults-') as temporary:
            binary = str(Path(temporary) / 'observer')
            run('build', ['go', 'build', '-mod=readonly', '-trimpath', '-o', binary, '.'])
            identity = json.loads(run('identity', [binary, '--identity'], timeout=10))
            if (any(identity.get(k) != provenance[k] for k in ('module', 'version', 'sum', 'tengo_source'))
                    or identity.get('go') != 'go1.27.3' or not identity.get('tengo_source')
                    or any(type(identity.get(k)) is not str or not identity[k] for k in ('os', 'arch'))):
                raise ValueError('native runtime identity differs')
            summary.update(native_runtime=identity, native_binary_sha256=digest(Path(binary)))
            native = json.loads(run('native', [binary, '--input', str(out / 'inputs.json')], timeout=30))
            native_rows(rows, native)
            controls = [
                ('null', [{'id': 'invalid', 'overrides': {'a': None}}], 'null override'),
                ('bool-integer', [{'id': 'invalid', 'overrides': {'a': True}}], 'cannot unmarshal bool'),
                ('integer-bool', [{'id': 'invalid', 'overrides': {'enabled': 0}}], 'cannot unmarshal number'),
                ('unknown', [{'id': 'invalid', 'overrides': {'extra': 1}}], 'unknown override field'),
                ('duplicate', [{'id': 'same', 'overrides': {}}] * 2, 'duplicate case identity'),
            ]
            for name, value, diagnostic in controls:
                label = 'native-invalid-' + name
                path = out / (label + '.json')
                path.write_text(json.dumps(value) + '\n')
                try:
                    run(label, [binary, '--input', str(path)], timeout=10)
                except ValueError:
                    error = (out / (label + '.stderr')).read_text()
                    if (summary['steps'][-1]['exit_code'] != 2 or (out / (label + '.stdout')).read_bytes()
                            or len(error.splitlines()) != 1 or diagnostic not in error):
                        raise ValueError('native protocol rejection differs: ' + name)
                else:
                    raise ValueError('native observer accepted out-of-domain input: ' + name)
        cases = out / 'cases.json'
        cases.write_text(json.dumps({'schema': 'gooo/body-composition-cases/v1', 'cases': [
            {'inputs': {KEY: row['input']}, 'expected': {KEY: n['actual']}}
            for row, n in zip(rows, native)
        ]}, indent=2) + '\n')
        compiler = str(Path(args.gooo).resolve())
        version = json.loads(run('compiler', [compiler, 'version', '--build', '--json'], cwd=BRIDGE, timeout=10))
        if version.get('version') != '0.6.38-dev':
            raise ValueError('compiler version differs')
        receipt = json.loads(run('execution', [compiler, 'package', 'execute', '--json', '--cases', str(cases),
                                               'gooo.workspace.json'], cwd=BRIDGE, timeout=120))
        combined = compare(rows, native, receipt, digest(cases), digest(BRIDGE / 'gooo.workspace.json'))
        resets = reset_counts(combined)
        for name, field, value in [('bool-integer', 'a_value', True), ('integer-bool', 'enabled_value', 0),
                                    ('integer-presence', 'a_present', 0), ('missing-presence', 'a_present', None)]:
            label = 'gooo-invalid-' + name
            value_row = dict(rows[0]['input'])
            if name == 'missing-presence':
                del value_row[field]
            else:
                value_row[field] = value
            path = out / (label + '.json')
            path.write_text(json.dumps({'schema': 'gooo/body-composition-cases/v1', 'cases': [
                {'inputs': {KEY: value_row}, 'expected': {KEY: rows[0]['expected']}}]}) + '\n')
            try:
                run(label, [compiler, 'package', 'execute', '--json', '--cases', str(path), 'gooo.workspace.json'], cwd=BRIDGE, timeout=60)
            except ValueError:
                rejected = json.loads((out / (label + '.stdout')).read_text())
                d = rejected.get('input_diagnostic', {})
                if (summary['steps'][-1]['exit_code'] != 1 or rejected.get('decision') != 'FAIL_CLOSED'
                        or rejected.get('cases_digest') != digest(path)
                        or rejected.get('manifest_digest') != digest(BRIDGE / 'gooo.workspace.json')
                        or d.get('stage') != 'INPUT_VALIDATION' or d.get('code') != 'INVALID_INPUT_VALUE'
                        or type(d.get('case_index')) is not int or d['case_index'] != 0 or d.get('key') != KEY):
                    raise ValueError('Gooo input type rejection differs: ' + name)
            else:
                raise ValueError('Gooo accepted wrong input field type: ' + name)
        (out / 'rows.json').write_text(json.dumps(combined, indent=2) + '\n')
        summary.update(decision='PASS', cases=len(rows), native_matches=len(rows), gooo_matches=len(rows),
                       unique_native_inputs=len({json.dumps(r['overrides'], sort_keys=True) for r in rows}),
                       native_protocol_rejections=5, gooo_type_rejections=3, gooo_presence_rejections=1, reset_transitions=resets,
                       activity_id=ACTIVITY, compiler_sha256=digest(Path(compiler)))
    except (OSError, ValueError, KeyError, TypeError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + list(BRIDGE.iterdir()) + list(NATIVE.iterdir()) + [Path(__file__)]
        summary['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)
                             if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
