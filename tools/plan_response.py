"""Bounded offline response planning; no acquisition or publication effects."""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'bridges/contribution-response'
KEY = 'bridge/contributionresponse:Plan'
ACTIVITY = 'urn:gooo:contribution:response-plan'
FIELDS = ('roles_match', 'bindings_match', 'comparison_supported',
          'evidence_current', 'external_satisfied', 'useful_addition')
MAX_BYTES = 128 * 1024


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def digest(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('nonfinite JSON constant: ' + value)


def read_json(path):
    data = Path(path).read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError('packet exceeds byte budget')
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)


def validate(value, schema, location='$'):
    """Validate the bounded JSON Schema subset used by these three fixed schemas."""
    if '$ref' in schema:
        if schema['$ref'] not in ('input.schema.json', 'evidence.schema.json'):
            raise ValueError('unsupported schema reference')
        return validate(value, read_json(BRIDGE / schema['$ref']), location)
    types = {'object': dict, 'array': list, 'string': str, 'boolean': bool,
             'integer': int, 'null': type(None)}
    declared = schema.get('type')
    if declared:
        allowed = declared if type(declared) is list else [declared]
        if type(value) not in [types[t] for t in allowed]:
            raise ValueError(location + ': wrong JSON type')
    if 'const' in schema and value != schema['const']:
        raise ValueError(location + ': schema/version mismatch')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(location + ': unknown enum')
    if type(value) is dict:
        properties = schema['properties']
        if set(value) != set(schema['required']) or set(value) - set(properties):
            raise ValueError(location + ': missing or unknown fields')
        for key, item in value.items():
            validate(item, properties[key], location + '.' + key)
    elif type(value) is list:
        if not schema.get('minItems', 0) <= len(value) <= schema['maxItems']:
            raise ValueError(location + ': array budget')
        for i, item in enumerate(value):
            validate(item, schema['items'], location + '[' + str(i) + ']')
    elif type(value) is str:
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', MAX_BYTES):
            raise ValueError(location + ': string budget')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
            raise ValueError(location + ': identity format')
    elif type(value) is int:
        if not schema.get('minimum', value) <= value <= schema.get('maximum', value):
            raise ValueError(location + ': numeric budget')


def timestamp(text):
    stamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('timestamps must include timezone')
    return stamp


def facts(packet):
    if len(encoded(packet)) > MAX_BYTES:
        raise ValueError('packet exceeds byte budget')
    validate(packet, read_json(BRIDGE / 'input.schema.json'))
    actor = packet['actor']
    context = packet['conversation']
    claims, evidence = packet['claims'], packet['evidence']
    if (len({c['id'] for c in claims}) != len(claims)
            or len({e['id'] for e in evidence}) != len(evidence)):
        raise ValueError('duplicate claim/evidence identity')
    by_id = {e['id']: e for e in evidence}
    roles = actor['observed_role'] != 'unknown' and all(
        c['actor_id'] == actor['id'] and c['asserted_role'] == actor['observed_role'] for c in claims)
    bindings, comparison = True, True
    for claim in claims:
        ids = claim['evidence_ids']
        if not ids or len(set(ids)) != len(ids) or any(i not in by_id for i in ids):
            bindings = False
            continue
        for i in ids:
            e = by_id[i]
            identity, run = e['identities'], e['execution']
            if claim['tested_revision'] is not None:
                bindings &= claim['tested_revision'] == (identity['candidate_commit'] or identity['source_commit'])
                bindings &= claim['tested_revision'] == context['tested_head']
            if run['phase'] in ('parse', 'compile', 'targeted_tests', 'full_suite'):
                bindings &= bool(identity['source_commit'] and run['tested_scope'])
                if identity['candidate_commit'] is not None:
                    bindings &= identity['source_commit'] == identity['candidate_commit']
                comparison &= run['outcome'] in ('pass', 'fail')
            elif run['phase'] == 'not_executed':
                comparison &= run['outcome'] == 'not_executed'
            elif run['phase'] == 'unknown':
                comparison &= run['outcome'] == 'unknown'
            if claim['kind'] in ('original_finding_fixed', 'pre_existing_limitation'):
                comparison &= bool(identity['base_commit'] and identity['candidate_commit'])
                comparison &= run['comparison'] == 'base_and_candidate'
                comparison &= run['phase'] in ('targeted_tests', 'full_suite')
                comparison &= run['base_outcome'] == 'fail'
                comparison &= run['candidate_outcome'] == (
                    'pass' if claim['kind'] == 'original_finding_fixed' else 'fail')
                comparison &= run['outcome'] == run['candidate_outcome']
                comparison &= claim['status'] == (
                    'resolved' if claim['kind'] == 'original_finding_fixed' else 'observed')
    age = (timestamp(context['as_of']) - timestamp(context['observed_at'])).total_seconds()
    current = (0 <= age <= context['max_age_seconds']
               and context['snapshot_id'] == context['current_snapshot_id']
               and context['tested_head'] == context['current_head'])
    # A visible composer or minimized review never establishes posting permission.
    requirement = packet['policy']['external_requirement']
    external = (requirement == 'satisfied' and
                ((packet['policy']['basis'] == 'synthetic' and packet['origin'] == 'synthetic')
                 or (packet['policy']['basis'] != 'synthetic'
                     and packet['policy']['source_identity'] is not None)))
    return dict(zip(FIELDS, (bool(roles), bool(bindings), bool(comparison), bool(current),
                             external, packet['requested'] or packet['adds_information'])))


def reference(row):
    if set(row) != set(FIELDS) or any(type(v) is not bool for v in row.values()):
        raise ValueError('planner requires exactly six Boolean observations')
    for field, reason in (
        ('roles_match', 'REFUSED_INVALID_CLAIMS:ROLE_UNESTABLISHED'),
        ('bindings_match', 'REFUSED_INVALID_CLAIMS:EVIDENCE_BINDING'),
        ('comparison_supported', 'REFUSED_INVALID_CLAIMS:COMPARISON_UNSUPPORTED'),
        ('evidence_current', 'NEEDS_CURRENT_EVIDENCE:STALE_SNAPSHOT'),
        ('external_satisfied', 'EXTERNAL_REQUIREMENT_UNSATISFIED:EXTERNAL_PRECONDITION'),
        ('useful_addition', 'NO_POST:NO_USEFUL_ADDITION'),
    ):
        if not row[field]:
            return reason
    return 'BOUNDED_DRAFT_READY:BOUNDED_INFORMATION'


def result(packet, observed):
    expected = reference(facts(packet))
    if observed != expected:
        raise ValueError('Gooo/reference decision differs')
    decision, reason = observed.split(':')
    value = {'schema': 'gooo/contribution-response-result/v1',
             'input_digest': digest(encoded(packet)),
             'policy_digest': digest((BRIDGE / 'main.gooo').read_bytes()),
             'decision': decision, 'reason': reason, 'effect': 'none', 'packet': deepcopy(packet)}
    validate(value, read_json(BRIDGE / 'result.schema.json'))
    return value


def render(value):
    validate(value, read_json(BRIDGE / 'result.schema.json'))
    packet = value['packet']
    if result(packet, value['decision'] + ':' + value['reason']) != value:
        raise ValueError('presentation input binding differs')
    statements = {
        'NO_POST': 'No additional post is useful on these supplied observations.',
        'NEEDS_CURRENT_EVIDENCE': 'The evidence is stale for the supplied current conversation.',
        'EXTERNAL_REQUIREMENT_UNSATISFIED': 'An external requirement is unmet or unknown.',
        'REFUSED_INVALID_CLAIMS': 'The supplied roles, evidence bindings or comparison do not support this claim.',
        'BOUNDED_DRAFT_READY': 'A bounded response draft can be prepared from these supplied claims.',
    }
    actions = {
        'NO_POST': 'Retain the evidence without another post.',
        'NEEDS_CURRENT_EVIDENCE': 'Refresh the changed head or feedback before revising the draft.',
        'EXTERNAL_REQUIREMENT_UNSATISFIED': 'Retain the analysis with no publication effect.',
        'REFUSED_INVALID_CLAIMS': 'Correct the unsupported claim and its source binding.',
        'BOUNDED_DRAFT_READY': 'Use only the listed scope and claim statuses in a draft.',
    }
    lines = [statements[value['decision']]]
    if (value['decision'] not in ('REFUSED_INVALID_CLAIMS', 'NEEDS_CURRENT_EVIDENCE')
            and any(c['kind'] == 'original_finding_fixed' and c['status'] == 'resolved'
                    for c in packet['claims'])):
        lines.append('The supplied packet reports the original finding resolved within its listed scope; '
                     'a separate base-existing limitation is retained below.')
    elif packet['conversation']['interaction']['minimization'] == 'low-quality':
        lines.append('The supplied review is minimized as low-quality. '
                     'That does not establish dismissal, a moderation cause or a posting restriction.')
    lines += ['', 'One next action: ' + actions[value['decision']],
             '', 'Origin: ' + packet['origin'] + '; no live execution is implied by a fixture.',
             'No publication effect or recipient acceptance is established.',
             'Packet: ' + packet['id'] + '; input binding: ' + value['input_digest'],
             'Observed actor role: ' + packet['actor']['id'] + ' / ' + packet['actor']['observed_role'],
             '', 'Supplied claims (not independent proof):']
    for claim in packet['claims']:
        lines.append('- ' + claim['id'] + ': ' + claim['kind'] + ' / ' + claim['status']
                     + '; actor=' + claim['actor_id'] + ' (' + claim['asserted_role'] + ')')
    interaction = packet['conversation']['interaction']
    lines += ['', 'Interaction observations: ' + json.dumps(interaction, sort_keys=True), '', 'Evidence appendix:']
    lines.append('Policy: ' + json.dumps(packet['policy'], sort_keys=True))
    lines.append('Phase: ' + packet['phase'] + '; planner source: ' + value['policy_digest'])
    for evidence in packet['evidence']:
        run = evidence['execution']
        lines.append('- ' + evidence['id'] + ': ' + run['phase'] + ' / ' + run['outcome']
                     + '; comparison=' + run['comparison'] + '; scope=' + json.dumps(run['tested_scope']))
        lines.append('  identities=' + json.dumps(evidence['identities'], sort_keys=True))
        for ref in evidence['references']:
            lines.append('  ' + ref['id'] + ': ' + ref['url'] + '; sha256=' + (ref['sha256'] or 'unknown'))
    # Material limitations remain visible even on a no-post/refused result.
    for record in [packet] + packet['claims'] + packet['evidence']:
        for label in ('uncertainty', 'failures', 'exclusions'):
            for text in record[label]:
                lines.append(label + ': ' + text)
    return '\n'.join(lines) + '\n'


def verify_receipt(receipt, rows, cases_path, code):
    runtime = receipt.get('result', {}).get('runtime', {})
    if (type(code) is not int or code != 0 or receipt.get('decision') != 'PASS'
            or receipt.get('cases_digest') != digest(cases_path.read_bytes())
            or receipt.get('manifest_digest') != digest((BRIDGE / 'gooo.workspace.json').read_bytes())
            or any(type(runtime.get(k)) is not int or runtime[k] != len(rows)
                   for k in ('finite_total', 'finite_passed'))):
        raise ValueError('missing complete bound Gooo planner PASS')
    traces = runtime.get('traces', [])
    if (len(traces) != len(rows) or any(type(t.get('case_index')) is not int for t in traces)
            or {t['case_index'] for t in traces} != set(range(len(rows)))):
        raise ValueError('planner case domain differs')
    outputs = {}
    for trace in traces:
        i = trace['case_index']
        deliveries = trace.get('deliveries', [])
        if len(deliveries) != 1:
            raise ValueError('ambiguous planner delivery')
        delivery = deliveries[0]
        row = facts(rows[i]['packet'])
        expected = reference(row)
        if (delivery.get('activity_id') != ACTIVITY or delivery.get('input') != row
                or any(type(v) is not bool for v in delivery.get('input', {}).values())
                or delivery.get('actual') != expected or delivery.get('expected') != expected
                or delivery.get('passed') is not True):
            raise ValueError('planner identity/input/result differs')
        outputs[i] = result(rows[i]['packet'], delivery['actual'])
    return [outputs[i] for i in range(len(rows))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    out = ROOT / 'evidence/response-planning'
    out.mkdir(parents=True, exist_ok=True)
    if len(list(out.glob('attempt-*'))) >= 8:
        raise ValueError('eight retained attempts reached; select a fresh evidence checkout')
    # Each invocation has a new directory; failed work cannot overwrite a prior receipt.
    attempt = Path(tempfile.mkdtemp(prefix='attempt-', dir=out))
    summary = {'schema': 'gooo-language-bridge/response-planning/v1', 'decision': 'FAIL_CLOSED',
               'network_requests': 0, 'publication_effects': 0, 'original_scenarios': [1, 2, 3, 4, 6, 15],
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID')}
    binary = str(Path(args.gooo).resolve())
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')
    try:
        rows = read_json(BRIDGE / 'fixtures.json')['cases']
        observations = [facts(row['packet']) for row in rows]
        for row, observed in zip(rows, observations):
            if reference(observed) != row['expected']:
                raise ValueError('fixture expectation differs')
        version = subprocess.run([binary, 'version', '--build', '--json'],
                                 capture_output=True, timeout=10)
        (attempt / 'compiler.json').write_bytes(version.stdout)
        (attempt / 'compiler.stderr').write_bytes(version.stderr)
        if version.returncode or json.loads(version.stdout).get('version') != '0.6.38-dev':
            raise ValueError('unsupported compiler identity')
        cases_path = attempt / 'cases.json'
        cases_path.write_bytes(encoded({'schema': 'gooo/body-composition-cases/v1', 'cases': [
            {'inputs': {KEY: f}, 'expected': {KEY: reference(f)}} for f in observations]}))
        executed = subprocess.run([binary, 'package', 'execute', '--json', '--cases', str(cases_path),
                                   'gooo.workspace.json'], cwd=BRIDGE, env=env,
                                  capture_output=True, timeout=90)
        (attempt / 'execution.json').write_bytes(executed.stdout)
        (attempt / 'execution.stderr').write_bytes(executed.stderr)
        outputs = verify_receipt(json.loads(executed.stdout), rows, cases_path, executed.returncode)
        (attempt / 'results.json').write_bytes(encoded(outputs))
        for i, output in enumerate(outputs):
            (attempt / ('view-%02d.txt' % i)).write_text(render(output))
        summary.update(decision='PASS', cases=len(rows), compiler_sha256=digest(Path(binary).read_bytes()))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    paths = list(attempt.iterdir()) + list(BRIDGE.iterdir()) + [Path(__file__)]
    summary['sha256'] = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes())
                         for p in sorted(paths) if p.is_file()}
    (attempt / 'summary.json').write_bytes(encoded(summary))
    # Retain and cover earlier attempt diagnostics without replacing their manifests.
    summary['sha256'].update({p.relative_to(ROOT).as_posix(): digest(p.read_bytes())
                              for p in sorted(out.rglob('*')) if p.is_file() and p != out / 'summary.json'})
    (out / 'summary.json').write_bytes(encoded(summary))
    print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
