"""Compare explicit missing/null/default intent with released HCL public APIs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

try:
    from .compare_js import run_step
    from .verify_input_defaults import typed, field_rows
except ImportError:
    from compare_js import run_step
    from verify_input_defaults import typed, field_rows

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'bridges/hcl-null-defaults'
NATIVE = ROOT / 'examples/hcl-defaults-reference'
KEY = 'bridge/hcl-defaults:Resolve'
ACTIVITY = 'urn:gooo:bridge:hcl-defaults:resolve'
INPUTS = {k: 'urn:gooo:bridge:hcl-defaults:' + k.replace('_', '-') for k in
          ('is_optional', 'default_present', 'default_value', 'provided', 'input_null', 'input_value')}
OUTPUTS = {k: 'urn:gooo:bridge:hcl-defaults:' + k.replace('_', '-') for k in ('accepted', 'is_null', 'value')}
INPUT_TYPES = {k: int if k in ('default_value', 'input_value') else bool for k in INPUTS}
OUTPUT_TYPES = {'accepted': bool, 'is_null': bool, 'value': int}
DECLARATIONS = {'required': (False, False, 0), 'optional': (True, False, 0),
                'default-zero': (True, True, 0), 'default-42': (True, True, 42)}


def corpus():
    rows = []
    for declaration, (optional, has_default, default) in DECLARATIONS.items():
        for state, value in [('missing', 0), ('null', 0), ('number', -1), ('number', 0), ('number', 2)]:
            accepted = optional or state != 'missing'
            use_default = optional and has_default and state in ('missing', 'null')
            is_null = accepted and state in ('missing', 'null') and not use_default
            result = default if use_default else (value if accepted and not is_null else 0)
            rows.append(dict(id=declaration + '/' + state + '/' + str(value),
                             declaration=declaration, state=state, value=value,
                             input=dict(is_optional=optional, default_present=has_default, default_value=default,
                                        provided=state != 'missing', input_null=state == 'null', input_value=value),
                             expected=dict(accepted=accepted, is_null=is_null, value=result)))
    return rows


def native_inputs(rows):
    return [{k: r[k] for k in ('id', 'declaration', 'state', 'value')} for r in rows]


def native_rows(rows, native, constraints):
    keys = {'id', 'declaration', 'state', 'value', 'constraint', 'input', 'after_defaults', 'result', 'diagnostic', 'actual'}
    if (type(native) is not list or len(native) != len(rows)
            or any(type(n) is not dict or set(n) != keys for n in native)
            or [n['id'] for n in native] != [r['id'] for r in rows]):
        raise ValueError('native case order/domain differs')
    for r, n in zip(rows, native):
        physical = {k: r[k] for k in ('id', 'declaration', 'state', 'value')}
        if (not typed({k: n[k] for k in physical}, physical, {k: type(v) for k, v in physical.items()})
                or n['constraint'] != constraints[r['declaration']]
                or not typed(n['actual'], r['expected'], OUTPUT_TYPES)):
            raise ValueError('native input/type/policy differs')
        before = {} if r['state'] == 'missing' else {'v': None if r['state'] == 'null' else r['value']}
        applied = dict(before)
        if r['input']['is_optional'] and r['input']['default_present'] and r['state'] in ('missing', 'null'):
            applied = {'v': r['input']['default_value']}
        for field, expected in [('input', before), ('after_defaults', applied)]:
            if not typed(n[field], expected, {k: type(v) for k, v in expected.items()}):
                raise ValueError('native missing/null/default observation differs')
        if r['expected']['accepted']:
            expected = {'v': None if r['expected']['is_null'] else r['expected']['value']}
            if (n['diagnostic'] != '' or not typed(n['result'], expected, {k: type(v) for k, v in expected.items()})):
                raise ValueError('native accepted result differs')
        elif n['result'] is not None or n['diagnostic'] != 'attribute "v" is required':
            raise ValueError('native required-attribute diagnostic differs')
    return native


def compare(rows, native, receipt, cases_digest, manifest_digest, constraints):
    native_rows(rows, native, constraints)
    runtime = receipt.get('result', {}).get('runtime', {})
    if (receipt.get('decision') != 'PASS' or receipt.get('cases_digest') != cases_digest
            or receipt.get('manifest_digest') != manifest_digest
            or any(type(runtime.get(k)) is not int or runtime[k] != len(rows) for k in ('finite_total', 'finite_passed'))):
        raise ValueError('missing complete source-bound Gooo PASS')
    traces = runtime.get('traces', [])
    if (len(traces) != len(rows) or any(type(t.get('case_index')) is not int for t in traces)
            or {t['case_index'] for t in traces} != set(range(len(rows)))):
        raise ValueError('Gooo case domain differs')
    actual = {}
    for trace in traces:
        i = trace['case_index']; r = rows[i]; deliveries = trace.get('deliveries', [])
        if len(deliveries) != 1:
            raise ValueError('ambiguous Gooo delivery')
        d = deliveries[0]
        if (d.get('activity_id') != ACTIVITY or d.get('passed') is not True
                or not typed(d.get('input'), r['input'], INPUT_TYPES)
                or not typed(d.get('actual'), r['expected'], OUTPUT_TYPES)
                or not typed(d.get('expected'), r['expected'], OUTPUT_TYPES)):
            raise ValueError('Gooo activity/type/value differs')
        field_rows(d.get('input_fields'), r['input'], INPUTS, INPUT_TYPES)
        field_rows(d.get('actual_fields'), r['expected'], OUTPUTS, OUTPUT_TYPES)
        actual[i] = d['actual']
    return [dict(r, native=n['actual'], gooo=actual[i]) for i, (r, n) in enumerate(zip(rows, native))]


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--gooo', required=True)
    args = parser.parse_args(); out = ROOT / 'evidence/hcl-null-defaults'; out.mkdir(parents=True, exist_ok=True)
    for p in out.iterdir():
        if p.is_file(): p.unlink()
    summary = dict(schema='gooo-language-bridge/hcl-null-defaults/v1', decision='FAIL_CLOSED',
                   commit=os.environ.get('GITHUB_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'), steps=[])
    started = time.monotonic(); env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off', GOFLAGS='')
    def run(label, command, cwd=NATIVE, timeout=120):
        return run_step(label, command, cwd, env, out, summary['steps'], timeout)
    try:
        rows = corpus(); provenance = json.loads((BRIDGE / 'provenance.json').read_text())
        if len(rows) != 20 or len({r['id'] for r in rows}) != 20:
            raise ValueError('expected twenty distinct inputs')
        (out / 'inputs.json').write_text(json.dumps(native_inputs(rows), indent=2) + '\n')
        for name, target in [('main.go', 'native-source.go'), ('go.mod', 'native.mod'), ('go.sum', 'native.sum')]:
            (out / target).write_bytes((NATIVE / name).read_bytes())
        module = json.loads(run('module', ['go', 'mod', 'download', '-json', provenance['module'] + '@' + provenance['version']]))
        if (module.get('Origin', {}).get('Hash') != provenance['revision']
                or module.get('Version') != provenance['version'] or module.get('Sum') != provenance['sum']):
            raise ValueError('native module source binding differs')
        run('module-verify', ['go', 'mod', 'verify'])
        for name in ('LICENSE', 'go.mod'):
            shutil.copyfile(Path(module['Dir']) / name, out / ('upstream-' + name))
        with tempfile.TemporaryDirectory(prefix='gooo-hcl-defaults-') as temp:
            binary = str(Path(temp) / 'observer')
            run('build', ['go', 'build', '-mod=readonly', '-trimpath', '-o', binary, '.'])
            identity = json.loads(run('identity', [binary, '--identity'], timeout=10))
            if (any(identity.get(k) != provenance[k] for k in ('module', 'version', 'sum', 'constraints'))
                    or identity.get('go') != 'go1.27.3'
                    or any(type(identity.get(k)) is not str or not identity[k] for k in ('os', 'arch'))):
                raise ValueError('native runtime/source identity differs')
            summary.update(native_runtime=identity, native_binary_sha256=digest(Path(binary)))
            native = json.loads(run('native', [binary, '--input', str(out / 'inputs.json')], timeout=30))
            native_rows(rows, native, provenance['constraints'])
            controls = [
                ('declaration', [dict(id='bad', declaration='unknown', state='missing', value=0)], 'unknown declaration'),
                ('state', [dict(id='bad', declaration='optional', state='unknown', value=0)], 'unknown input state'),
                ('bool-value', [dict(id='bad', declaration='optional', state='number', value=True)], 'cannot unmarshal bool'),
                ('null-value', [dict(id='bad', declaration='optional', state='number', value=None)], 'missing numeric payload'),
                ('duplicate', [native_inputs(rows)[0]] * 2, 'duplicate/invalid case identity'),
                ('noncanonical', [dict(id='bad', declaration='optional', state='missing', value=1)], 'noncanonical unused value'),
            ]
            for name, value, diagnostic in controls:
                label = 'native-invalid-' + name; path = out / (label + '.json'); path.write_text(json.dumps(value) + '\n')
                try: run(label, [binary, '--input', str(path)], timeout=10)
                except ValueError:
                    error = (out / (label + '.stderr')).read_text()
                    if (summary['steps'][-1]['exit_code'] != 2 or (out / (label + '.stdout')).read_bytes()
                            or len(error.splitlines()) != 1 or diagnostic not in error):
                        raise ValueError('native protocol rejection differs: ' + name)
                else: raise ValueError('native adapter accepted invalid input: ' + name)
        cases = out / 'cases.json'; cases.write_text(json.dumps(dict(schema='gooo/body-composition-cases/v1', cases=[
            dict(inputs={KEY: r['input']}, expected={KEY: n['actual']}) for r, n in zip(rows, native)]), indent=2) + '\n')
        compiler = str(Path(args.gooo).resolve())
        version = json.loads(run('compiler', [compiler, 'version', '--build', '--json'], cwd=BRIDGE, timeout=10))
        if version.get('version') != '0.6.38-dev': raise ValueError('compiler version differs')
        receipt = json.loads(run('execution', [compiler, 'package', 'execute', '--json', '--cases', str(cases), 'gooo.workspace.json'], cwd=BRIDGE))
        combined = compare(rows, native, receipt, digest(cases), digest(BRIDGE / 'gooo.workspace.json'), provenance['constraints'])
        for name, field, value in [('bool-number', 'input_value', True), ('number-null', 'input_null', 0), ('missing-presence', 'provided', None)]:
            label = 'gooo-invalid-' + name; bad = dict(rows[0]['input'])
            if name == 'missing-presence': del bad[field]
            else: bad[field] = value
            path = out / (label + '.json'); path.write_text(json.dumps(dict(schema='gooo/body-composition-cases/v1', cases=[dict(inputs={KEY: bad}, expected={KEY: rows[0]['expected']})])) + '\n')
            try: run(label, [compiler, 'package', 'execute', '--json', '--cases', str(path), 'gooo.workspace.json'], cwd=BRIDGE, timeout=60)
            except ValueError:
                rejected = json.loads((out / (label + '.stdout')).read_text()); d = rejected.get('input_diagnostic', {})
                if (summary['steps'][-1]['exit_code'] != 1 or rejected.get('decision') != 'FAIL_CLOSED'
                        or rejected.get('cases_digest') != digest(path) or rejected.get('manifest_digest') != digest(BRIDGE / 'gooo.workspace.json')
                        or d.get('stage') != 'INPUT_VALIDATION' or d.get('code') != 'INVALID_INPUT_VALUE'
                        or type(d.get('case_index')) is not int or d['case_index'] != 0 or d.get('key') != KEY):
                    raise ValueError('Gooo type/presence rejection differs: ' + name)
            else: raise ValueError('Gooo accepted invalid input: ' + name)
        (out / 'rows.json').write_text(json.dumps(combined, indent=2) + '\n')
        counts = dict(accepted=sum(n['actual']['accepted'] for n in native),
                      required_missing_rejections=sum(not n['actual']['accepted'] for n in native),
                      null_results=sum(n['actual']['is_null'] for n in native),
                      defaults_applied=sum(n['input'] != n['after_defaults'] for n in native))
        if counts != dict(accepted=19, required_missing_rejections=1, null_results=3, defaults_applied=4):
            raise ValueError('native boundary coverage differs')
        summary.update(decision='PASS', cases=len(rows), native_matches=len(rows), gooo_matches=len(rows), **counts, native_protocol_rejections=6,
                       gooo_type_rejections=2, gooo_presence_rejections=1, activity_id=ACTIVITY, compiler_sha256=digest(Path(compiler)))
    except (OSError, ValueError, KeyError, TypeError) as error: summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + list(BRIDGE.iterdir()) + list(NATIVE.iterdir()) + [Path(__file__), ROOT / 'tools/verify_input_defaults.py', ROOT / 'tools/compare_js.py']
        summary['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(paths)) if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n'); print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
