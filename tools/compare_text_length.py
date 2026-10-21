"""Compare named string units; retain original native output and Gooo receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'bridges/text-length'
ACTIVITY = 'urn:gooo:bridge:text:measure'
KEY = 'bridge/text:Measure'
FIELDS = {'utf8_bytes': 'urn:gooo:bridge:text:utf8-bytes',
          'code_points': 'urn:gooo:bridge:text:code-points',
          'utf16_units': 'urn:gooo:bridge:text:utf16-units'}


def corpus():
    rows = [
        ('empty', ''), ('ascii', 'gooo'), ('nul', '\0'), ('crlf', 'a\r\nb'),
        ('latin-precomposed', 'é'), ('latin-decomposed', 'e\u0301'),
        ('hangul-precomposed', '가'), ('hangul-decomposed', '\u1100\u1161'),
        ('emoji', '🙂'), ('zwj', '👩\u200d💻'), ('flag', '🇰🇷'),
        ('variation-selector', '✈\ufe0f'), ('mixed', 'Go 한글 🙂\0'),
        ('replacement-scalar', '\ufffd'),
    ]
    rows += [('scalar-%06x' % n, chr(n)) for n in
             (0x7f, 0x80, 0x7ff, 0x800, 0xd7ff, 0xe000, 0xffff, 0x10000, 0x10ffff)]
    rows += [('ascii-limit', 'a' * 1024), ('astral-limit', '🙂' * 256),
             ('mixed-limit', '한' * 340 + '🙂'), ('below-limit', '한' * 341)]
    return [{'id': name, 'text': text} for name, text in rows]


def python_lengths(text):
    encoded = text.encode('utf-8', errors='strict')
    if len(encoded) > 1024:
        raise ValueError('input exceeds 1024 UTF-8 bytes')
    return {'utf8_bytes': len(encoded), 'code_points': len(text),
            'utf16_units': len(text.encode('utf-16-le', errors='strict')) // 2}


def suite(rows):
    return {'schema': 'gooo/body-composition-cases/v1', 'cases': [
        {'inputs': {KEY: r['text']}, 'expected': {KEY: python_lengths(r['text'])}}
        for r in rows]}


def compare(rows, native, receipt, code):
    runtime = receipt.get('result', {}).get('runtime', {})
    if (type(code) is not int or code != 0 or receipt.get('decision') != 'PASS'
            or any(type(runtime.get(k)) is not int or runtime[k] != len(rows)
                   for k in ('finite_total', 'finite_passed'))):
        raise ValueError('missing complete finite Gooo PASS')
    expected_ids = [r['id'] for r in rows]
    if len(set(expected_ids)) != len(rows) or not 1 <= len(rows) <= 128:
        raise ValueError('invalid corpus identity')
    observations = {}
    for row in native:
        if row['id'] in observations:
            raise ValueError('duplicate native input identity')
        observations[row['id']] = row
    if set(observations) != set(expected_ids):
        raise ValueError('native input domain differs')
    traces = {}
    for trace in runtime['traces']:
        index = trace['case_index']
        if type(index) is not int or index in traces:
            raise ValueError('duplicate or invalid Gooo case index')
        traces[index] = trace
    if set(traces) != set(range(len(rows))):
        raise ValueError('Gooo input domain differs')
    result = []
    for index, row in enumerate(rows):
        expected = python_lengths(row['text'])
        observed = observations[row['id']]
        if observed['text'] != row['text'] or not valid_lengths(observed['lengths'], expected):
            raise ValueError('native Go/Python disagreement')
        deliveries = traces[index]['deliveries']
        if len(deliveries) != 1:
            raise ValueError('ambiguous Gooo delivery')
        d = deliveries[0]
        if (d['activity_id'] != ACTIVITY or d['input'] != row['text']
                or d['passed'] is not True or not valid_lengths(d['actual'], expected)
                or not valid_lengths(d['expected'], expected)):
            raise ValueError('Gooo observation or input identity differs')
        fields = d['actual_fields']
        if len(fields) != len(FIELDS) or sorted(
                (f['name'], f['id']) for f in fields) != sorted(FIELDS.items()):
            raise ValueError('Gooo field identity differs')
        if any(type(f['value']) is not int or f['value'] != expected[f['name']] for f in fields):
            raise ValueError('Gooo typed field value differs')
        result.append(dict(row, python=expected, go=observed['lengths'], gooo=d['actual']))
    return result


def compare_javascript(rows, observed):
    if not isinstance(observed, dict):
        raise ValueError('JavaScript output must be an object')
    runtime = observed['runtime']
    if (not isinstance(runtime, dict) or set(runtime) != {'node', 'v8', 'unicode'}
            or any(type(v) is not str or not v for v in runtime.values())):
        raise ValueError('missing JavaScript runtime identity')
    native = observed['rows']
    if not isinstance(native, list):
        raise ValueError('JavaScript observations must be a list')
    expected_ids = {r['id'] for r in rows}
    if len(expected_ids) != len(rows) or not 1 <= len(rows) <= 128:
        raise ValueError('invalid JavaScript corpus identity')
    by_id = {}
    for row in native:
        if row['id'] in by_id:
            raise ValueError('duplicate JavaScript input identity')
        by_id[row['id']] = row
    if set(by_id) != expected_ids:
        raise ValueError('JavaScript input domain differs')
    for row in rows:
        actual = by_id[row['id']]
        if actual['text'] != row['text'] or not valid_lengths(actual['lengths'], python_lengths(row['text'])):
            raise ValueError('native JavaScript/Python disagreement')
    return by_id


def valid_lengths(actual, expected):
    return (isinstance(actual, dict) and set(actual) == set(FIELDS)
            and all(type(actual[k]) is int and actual[k] == expected[k] for k in FIELDS))


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gooo', required=True)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    out = ROOT / 'evidence/text-length'
    out.mkdir(parents=True, exist_ok=True)
    for path in out.iterdir():
        if path.is_file():
            path.unlink()
    started = time.monotonic()
    summary = {'schema': 'gooo-language-bridge/text-length/v1', 'decision': 'FAIL_CLOSED',
               'python': platform.python_version(), 'implementation': platform.python_implementation(),
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    binary = str(Path(args.gooo).resolve())

    def run(label, command, **kwargs):
        p = subprocess.run(command, capture_output=True, timeout=90, env=env, **kwargs)
        (out / (label + '.stdout')).write_bytes(p.stdout)
        (out / (label + '.stderr')).write_bytes(p.stderr)
        summary[label + '_exit_code'] = p.returncode
        return p

    try:
        version = run('compiler', [binary, 'version', '--build', '--json'])
        identity = json.loads(version.stdout)
        if version.returncode or identity.get('version') != '0.6.38-dev':
            raise ValueError('compiler version mismatch')
        summary['compiler_sha256'] = digest(Path(binary))
        rows = corpus()
        (out / 'inputs.json').write_text(json.dumps(rows, ensure_ascii=True, indent=2) + '\n')
        cases_path = out / 'cases.json'
        cases_path.write_text(json.dumps(suite(rows), ensure_ascii=True, indent=2) + '\n')
        native = run('go', ['go', 'run', str(ROOT / 'examples/text-length-reference/main.go')],
                     input=(out / 'inputs.json').read_bytes(), cwd=ROOT)
        if native.returncode:
            raise ValueError('native Go reference failed')
        javascript = run('javascript', [args.node, str(ROOT / 'examples/text-length-reference/main.mjs')],
                         input=(out / 'inputs.json').read_bytes(), cwd=ROOT)
        if javascript.returncode:
            raise ValueError('native JavaScript reference failed')
        javascript_output = json.loads(javascript.stdout)
        javascript_rows = compare_javascript(rows, javascript_output)
        command = [binary, 'package', 'execute', '--json', '--cases', str(cases_path),
                   'gooo.workspace.json']
        executed = run('execution', command, cwd=BRIDGE)
        receipt = json.loads(executed.stdout)
        if (receipt['cases_digest'] != digest(cases_path)
                or receipt['manifest_digest'] != digest(BRIDGE / 'gooo.workspace.json')):
            raise ValueError('receipt input digest differs')
        compared = compare(rows, json.loads(native.stdout), receipt, executed.returncode)
        for row in compared:
            row['javascript'] = javascript_rows[row['id']]['lengths']
        (out / 'rows.json').write_text(json.dumps(compared, ensure_ascii=True, indent=2) + '\n')
        # A full-length prefix is not a valid result for a string above the contract.
        too_long = out / 'over-limit.json'
        too_long.write_text(json.dumps({'schema': 'gooo/body-composition-cases/v1', 'cases': [
            {'inputs': {KEY: 'a' * 1025}, 'expected': {KEY: {
                'utf8_bytes': 1025, 'code_points': 1025, 'utf16_units': 1025}}}]}))
        rejected = run('over-limit', command[:5] + [str(too_long), 'gooo.workspace.json'], cwd=BRIDGE)
        rejection = json.loads(rejected.stdout)
        diagnostic = rejection.get('input_diagnostic', {})
        if (rejected.returncode != 1 or rejection.get('decision') != 'FAIL_CLOSED'
                or rejection.get('cases_digest') != digest(too_long)
                or rejection.get('manifest_digest') != digest(BRIDGE / 'gooo.workspace.json')
                or diagnostic.get('stage') != 'INPUT_VALIDATION'
                or diagnostic.get('code') != 'INVALID_INPUT_VALUE'
                or type(diagnostic.get('case_index')) is not int or diagnostic['case_index'] != 0
                or diagnostic.get('key') != KEY or '1024 UTF-8 bytes' not in rejection.get('error', '')):
            raise ValueError('over-limit input was not explicitly rejected')
        javascript_rejections = []
        for label, text, reason in [('lone-high', '\ud800', 'INVALID_UNICODE_SCALAR'),
                                    ('lone-low', '\udfff', 'INVALID_UNICODE_SCALAR'),
                                    ('over-limit', 'a' * 1025, 'BYTE_LIMIT')]:
            path = out / ('javascript-' + label + '-input.json')
            path.write_text(json.dumps([{'id': label, 'text': text}], ensure_ascii=True) + '\n')
            rejected_js = run('javascript-' + label,
                              [args.node, str(ROOT / 'examples/text-length-reference/main.mjs')],
                              input=path.read_bytes(), cwd=ROOT)
            if (rejected_js.returncode != 1 or rejected_js.stdout
                    or json.loads(rejected_js.stderr) != {'decision': 'FAIL_CLOSED', 'code': reason}):
                raise ValueError('JavaScript domain rejection differs: ' + label)
            javascript_rejections.append(label)
        summary.update(decision='PASS', cases=len(compared), activity_id=ACTIVITY,
                       byte_codepoint_differences=sum(r['python']['utf8_bytes'] != r['python']['code_points'] for r in compared),
                       codepoint_utf16_differences=sum(r['python']['code_points'] != r['python']['utf16_units'] for r in compared),
                       over_limit_rejected=True, javascript_matches=len(javascript_rows),
                       javascript_runtime=javascript_output['runtime'], javascript_rejections=javascript_rejections,
                       go=subprocess.check_output(['go', 'version'], env=env, timeout=10).decode().strip())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        paths = list(out.iterdir()) + list(BRIDGE.iterdir()) + [Path(__file__),
                ROOT / 'examples/text-length-reference/main.go',
                ROOT / 'examples/text-length-reference/main.mjs']
        summary['sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)
                             if p.is_file() and p.name != 'summary.json'}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
