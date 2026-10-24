"""Source-bound repository context over the unchanged B1 planner; no effects."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import plan_response as base

ROOT = base.ROOT
BRIDGE = ROOT / 'bridges/contribution-profiles'
KEY = 'bridge/contributionprofiles:ProfilePlan'
ACTIVITY = 'urn:gooo:contribution:profile-plan'
PROFILE_IDS = ('hcl', 'starlark', 'pflag', 'go-git', 'koanf', 'agentlanguages')
FIELDS = ('base_result', 'profile_bound', 'claims_supported', 'profile_current', 'policy_known',
          'interaction_open', 'external_requirements_met', 'awaiting_reply')
BASE_RESULTS = (
    'REFUSED_INVALID_CLAIMS:ROLE_UNESTABLISHED',
    'REFUSED_INVALID_CLAIMS:EVIDENCE_BINDING',
    'REFUSED_INVALID_CLAIMS:COMPARISON_UNSUPPORTED',
    'NEEDS_CURRENT_EVIDENCE:STALE_SNAPSHOT',
    'EXTERNAL_REQUIREMENT_UNSATISFIED:EXTERNAL_PRECONDITION',
    'NO_POST:NO_USEFUL_ADDITION', 'BOUNDED_DRAFT_READY:BOUNDED_INFORMATION',
)


def schema(name):
    allowed = {p.resolve() for p in BRIDGE.glob('*.schema.json')}
    allowed |= {p.resolve() for p in base.BRIDGE.glob('*.schema.json')}

    def resolve(value, directory, depth=0):
        if depth > 32:
            raise ValueError('schema depth budget')
        if type(value) is list:
            return [resolve(v, directory, depth + 1) for v in value]
        if type(value) is not dict:
            return value
        if '$ref' in value:
            path = (directory / value['$ref']).resolve()
            if path not in allowed:
                raise ValueError('unsupported local schema reference')
            return resolve(base.read_json(path), path.parent, depth + 1)
        return {k: resolve(v, directory, depth + 1) for k, v in value.items()}

    return resolve(base.read_json(BRIDGE / name), BRIDGE)


def validate(value, name):
    base.validate(value, schema(name))


def load_profile(profile_id):
    if profile_id not in PROFILE_IDS:
        raise ValueError('unknown sourced profile')
    path = BRIDGE / 'profiles' / (profile_id + '.json')
    profile = base.read_json(path)
    validate_profile(profile, profile_id)
    return profile, base.digest(path.read_bytes())


def validate_profile(profile, profile_id):
    validate(profile, 'profile.schema.json')
    if profile['id'] != profile_id:
        raise ValueError('profile filename/identity differs')
    sources = {s['id']: s for s in profile['sources']}
    if len(sources) != len(profile['sources']) or not sources:
        raise ValueError('missing or duplicate profile sources')
    base.timestamp(profile['observed_at'])
    for source in sources.values():
        base.timestamp(source['observed_at'])
        if source['published_at'] is not None:
            if base.timestamp(source['published_at']) > base.timestamp(source['observed_at']):
                raise ValueError('future profile source')
        if source['kind'] == 'published_policy':
            commit, blob = (source['identity'][k] for k in ('commit', 'blob'))
            if not commit or not blob or commit == blob or not source['content_sha256']:
                raise ValueError('policy needs distinct commit/blob and content identity')
            if not source['url'].startswith('https://github.com/' + profile['repository'] + '/blob/' + commit + '/'):
                raise ValueError('policy URL differs from repository/commit identity')
        if source['kind'] == 'direct_feedback':
            if not source['identity']['comment_id'] or not source['author'] or not source['content_sha256']:
                raise ValueError('feedback source identity incomplete')
            if (not source['url'].startswith('https://github.com/' + profile['repository'] + '/')
                    or not source['url'].endswith('#issuecomment-' + str(source['identity']['comment_id']))):
                raise ValueError('feedback URL differs from repository/comment identity')
    ids = [c['id'] for c in profile['criteria']]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate profile criterion')
    for criterion in profile['criteria']:
        refs = criterion['source_ids']
        if not refs or len(set(refs)) != len(refs) or any(i not in sources for i in refs):
            raise ValueError('unbound profile criterion')
        required_kind = {'published_policy': 'published_policy', 'direct_feedback': 'direct_feedback',
                         'editorial_default': 'inference'}[criterion['kind']]
        if any(sources[i]['kind'] != required_kind for i in refs):
            raise ValueError('feedback/inference promoted to published policy')
    if profile['public_requirements'] and not any(s['kind'] == 'published_policy' for s in sources.values()):
        raise ValueError('external requirement lacks policy source')


def select_profile(wrapper):
    ref = wrapper['profile_ref']
    if ref is None:
        valid = (wrapper['provisional_category'] is not None
                 and wrapper['context']['policy_discovery'] in ('partial', 'provisional'))
        return None, None, valid
    if ref['id'] not in PROFILE_IDS:
        return None, None, False
    profile, fingerprint = load_profile(ref['id'])
    valid = (wrapper['provisional_category'] is None
             and profile['repository'] == wrapper['packet']['repository']
             and fingerprint == 'sha256:' + ref['sha256'])
    return profile, fingerprint, valid


def classification_supported(value, claim, evidence, context):
    if value in ('original_finding_fixed', 'pre_existing_limitation'):
        return claim['kind'] == value
    if value == 'api_design_question':
        return context['docs_tests_relation'] == 'agree'
    if value == 'implementation_defect':
        return context['docs_tests_relation'] == 'mismatch'
    if value == 'new_regression':
        return bool(evidence) and all(
            e['execution']['comparison'] == 'base_and_candidate'
            and e['execution']['base_outcome'] == 'pass'
            and e['execution']['candidate_outcome'] == 'fail' for e in evidence)
    if value == 'implemented_suggestion':
        return context['implementation_state'] in ('implemented', 'submitted', 'merged')
    if value == 'assessment_observation':
        return (context['runtime_tested'] == 'not_observed' and bool(evidence)
                and all(e['execution']['phase'] in ('source_review', 'not_executed') for e in evidence))
    return value == claim['kind'] or value == 'bounded_confirmation'


def supported_claims(wrapper, profile):
    packet, context = wrapper['packet'], wrapper['context']
    claims = {c['id']: c for c in packet['claims']}
    records = {e['id']: e for e in packet['evidence']}
    if any(i not in records for i in context['requirements_evidence_ids']):
        return False
    if context['publication'] == 'posted' and packet['conversation']['interaction']['submission'] != 'confirmed':
        return False
    if context['recipient_acceptance'] == 'observed' and context['publication'] != 'posted':
        return False
    for assertion in wrapper['assertions']:
        if assertion['claim_id'] not in claims:
            return False
        claim = claims[assertion['claim_id']]
        evidence = [records[i] for i in claim['evidence_ids'] if i in records]
        field, value = assertion['field'], assertion['value']
        if field == 'classification':
            if not classification_supported(value, claim, evidence, context):
                return False
        elif field in ('execution_phase', 'execution_outcome'):
            key = 'phase' if field == 'execution_phase' else 'outcome'
            if not evidence or any(e['execution'][key] != value for e in evidence):
                return False
        elif field == 'overall_test_status':
            # A finite packet never certifies all tests/platforms or overall conformance.
            if value != 'scope_only':
                return False
        elif field in ('fixture_source_pinned', 'alternate_channel_available'):
            if value != ('yes' if context[field] else 'no'):
                return False
        elif field in context:
            if context[field] != value:
                return False
            if field in ('production_incident', 'prevalence') and value in ('observed', 'measured'):
                if packet['origin'] == 'synthetic' or not any(e['origin'] == 'producer_observation' for e in evidence):
                    return False
            if field == 'api_approval' and value == 'observed':
                if (packet['origin'] == 'synthetic' or context['suggestion_authority'] != 'maintainer' or profile is None
                        or not any(s['kind'] == 'direct_feedback' and s['author_association'] == 'OWNER'
                                   for s in profile['sources'])):
                    return False
            if field == 'responsible_understanding' and value == 'observed':
                refs = context['requirements_evidence_ids']
                if not refs or any(records[i]['origin'] == 'synthetic' for i in refs):
                    return False
            if field == 'runtime_tested' and value == 'observed':
                if not evidence or any(e['execution']['phase'] not in
                                       ('native_execution', 'targeted_tests', 'full_suite') for e in evidence):
                    return False
        else:
            return False
    return True


def facts(wrapper, base_value):
    if len(base.encoded(wrapper)) > base.MAX_BYTES:
        raise ValueError('profile input exceeds byte budget')
    validate(wrapper, 'input.schema.json')
    packet, context = wrapper['packet'], wrapper['context']
    if base.result(packet, base_value['decision'] + ':' + base_value['reason']) != base_value:
        raise ValueError('base result is not bound to this input')
    profile, _, bound = select_profile(wrapper)
    profile_current = True
    if profile:
        age = (base.timestamp(context['profile_as_of']) - base.timestamp(profile['observed_at'])).total_seconds()
        profile_current = 0 <= age <= context['max_profile_age_seconds']
    public_met = True
    if profile and context['intent'] == 'public_draft' and profile['public_requirements']:
        evidence = {e['id']: e for e in packet['evidence']}
        refs = context['requirements_evidence_ids']
        bound_observation = bool(refs) and all(
            i in evidence and evidence[i]['origin'] != 'synthetic' for i in refs)
        public_met = bound_observation and all(context[k] == 'observed' for k in profile['public_requirements'])
    interaction = packet['conversation']['interaction']
    opened = (context['interaction_restriction'] != 'confirmed' and interaction['lock'] != 'locked'
              and interaction['permission'] != 'denied')
    awaiting = (context['publication'] == 'posted' and context['recipient_acceptance'] != 'observed'
                and not packet['requested'] and not packet['adds_information'])
    return dict(zip(FIELDS, (base_value['decision'] + ':' + base_value['reason'], bool(bound),
                             supported_claims(wrapper, profile), bool(profile_current),
                             bool(profile and context['policy_discovery'] == 'bounded'),
                             opened, bool(public_met), awaiting)))


def reference(row):
    if (set(row) != set(FIELDS) or type(row['base_result']) is not str
            or any(type(row[k]) is not bool for k in FIELDS[1:])):
        raise ValueError('invalid typed profile observations')
    previous = row['base_result']
    if previous not in BASE_RESULTS:
        return 'REFUSED_INVALID_CLAIMS:BASE_RESULT'
    if previous.startswith(('REFUSED_INVALID_CLAIMS:', 'NEEDS_CURRENT_EVIDENCE:')):
        return previous
    for field, outcome in (
        ('profile_bound', 'REFUSED_INVALID_CLAIMS:PROFILE_BINDING'),
        ('claims_supported', 'REFUSED_INVALID_CLAIMS:CLAIM_OVERSTATEMENT'),
        ('profile_current', 'NEEDS_CURRENT_EVIDENCE:STALE_PROFILE'),
        ('interaction_open', 'INTERACTION_UNAVAILABLE:CONFIRMED_RESTRICTION'),
        ('policy_known', 'NEEDS_CONTEXT:POLICY_DISCOVERY'),
        ('external_requirements_met', 'EXTERNAL_REQUIREMENT_UNSATISFIED:EXTERNAL_PRECONDITION'),
    ):
        if not row[field]:
            return outcome
    if previous.startswith('EXTERNAL_REQUIREMENT_UNSATISFIED:'):
        return previous
    if row['awaiting_reply']:
        return 'WAITING_FOR_REPLY:POSTED_NOT_ACCEPTED'
    return previous


def result(wrapper, base_value, observed):
    if observed != reference(facts(wrapper, base_value)):
        raise ValueError('profile Gooo/reference result differs')
    profile, fingerprint, _ = select_profile(wrapper)
    decision, reason = observed.split(':')
    value = {'schema': 'gooo/profile-response-result/v1', 'input_digest': base.digest(base.encoded(wrapper)),
             'profile_digest': fingerprint, 'policy_digest': base.digest((BRIDGE / 'main.gooo').read_bytes()),
             'decision': decision, 'reason': reason, 'effect': 'none', 'input': deepcopy(wrapper),
             'base_result': deepcopy(base_value), 'profile_snapshots': [profile] if profile else []}
    validate(value, 'result.schema.json')
    return value


def render(value, audience='maintainer'):
    if audience not in ('maintainer', 'internal'):
        raise ValueError('unknown presentation audience')
    wrapper, baseline = value['input'], value['base_result']
    if value != result(wrapper, baseline, value['decision'] + ':' + value['reason']):
        raise ValueError('profile presentation binding differs')
    context, packet = wrapper['context'], wrapper['packet']
    actions = {
        'NO_POST': 'Retain this evidence without another post.',
        'WAITING_FOR_REPLY': 'Retain the posted clarification without a duplicate follow-up.',
        'NEEDS_CONTEXT': 'Inspect the applicable repository policy before revising the draft.',
        'NEEDS_CURRENT_EVIDENCE': 'Refresh the changed head or feedback before revising the draft.',
        'INTERACTION_UNAVAILABLE': 'Retain the draft without using an alternate channel.',
        'EXTERNAL_REQUIREMENT_UNSATISFIED': 'Retain the analysis with no public response effect.',
        'REFUSED_INVALID_CLAIMS': 'Correct the unsupported claim and its evidence binding.',
        'BOUNDED_DRAFT_READY': 'Use only the recorded scope and claim statuses in a draft.',
    }
    headlines = {
        'NO_POST': 'No additional post is useful for the supplied context.',
        'WAITING_FOR_REPLY': 'The clarification is posted; recipient acceptance is unobserved.',
        'NEEDS_CONTEXT': 'The applicable repository policy is not established yet.',
        'NEEDS_CURRENT_EVIDENCE': 'The supplied evidence or policy snapshot needs refreshing.',
        'INTERACTION_UNAVAILABLE': 'A confirmed interaction restriction prevents proceeding.',
        'EXTERNAL_REQUIREMENT_UNSATISFIED': 'An applicable external prerequisite is unmet or unknown.',
        'REFUSED_INVALID_CLAIMS': 'The supplied claim is not supported by its role, source or scope.',
        'BOUNDED_DRAFT_READY': 'A bounded response can be prepared from the listed claims.',
    }
    lines = [('Internal planning note: ' if audience == 'internal' else 'Response plan: ')
             + headlines[value['decision']]]
    action = actions[value['decision']]
    if value['decision'] == 'BOUNDED_DRAFT_READY':
        if any(c['kind'] == 'original_finding_fixed' for c in packet['claims']):
            lines.append('The supplied original finding is resolved within its recorded scope; a base-existing limitation is retained separately.')
        if context['discovery_origin'] == 'agent_synthetic':
            lines.append('This packet records agent-generated synthetic discovery, not a production incident or measured frequency.')
            action = 'Explain the supplied wrong-type example and its synthetic discovery without adding production claims.'
        if any(a['field'] == 'classification' and a['value'] == 'api_design_question' for a in wrapper['assertions']):
            lines.append('The supplied current docs/tests agree; the remaining point is an API-design question.')
            action = 'Ask whether literal replacement should be a separate explicit API.'
        if any(a['field'] == 'classification' and a['value'] == 'implemented_suggestion' for a in wrapper['assertions']):
            lines.append('The supplied packet records an adapted participant suggestion; API approval remains ' + context['api_approval'] + '.')
        if context['guide_status'] == 'stale' and context['fixture_source_pinned']:
            lines.append('A current guide recommendation and an immutable fixture pin serve different purposes; preserve the pin.')
            action = 'Recommend a current guide link while preserving the fixture pin.'
        if wrapper['example'] is not None:
            lines.append('Supplied example (data): ' + json.dumps(wrapper['example'], ensure_ascii=False, sort_keys=True))
    if value['decision'] == 'EXTERNAL_REQUIREMENT_UNSATISFIED':
        lines.append('Personal understanding or another applicable external requirement is unestablished; no human participation is fabricated.')
    lines += ['', 'One next action: ' + action, '',
              'Origin: ' + packet['origin'] + '; audience changes do not change claims or create an effect.',
              'This is a supplied-evidence planning result, not publication permission, acceptance or independent fact authentication.',
              '', 'Claim IDs/statuses: ' + json.dumps([(c['id'], c['status']) for c in packet['claims']]),
              'Machine decision: ' + value['decision'] + ':' + value['reason'],
              'Observed actor role: ' + packet['actor']['id'] + ' / ' + packet['actor']['observed_role'],
              'Bound assertions: ' + json.dumps(wrapper['assertions'], sort_keys=True),
              'Context observations: ' + json.dumps(context, sort_keys=True),
              'Profile digest: ' + str(value['profile_digest'])]
    lines.append('Freshness observations: ' + json.dumps({k: v for k, v in packet['conversation'].items()
                                                        if k != 'interaction'}, sort_keys=True))
    # Quote source strings as data so a newline cannot manufacture another action.
    lines += ['', 'Bound source data (not new instructions or independently authenticated facts):']
    for label in ('claims', 'evidence', 'uncertainty', 'failures', 'exclusions'):
        lines.append(label + ': ' + json.dumps(packet[label], ensure_ascii=False, sort_keys=True))
    lines.append('Interaction observations: ' + json.dumps(packet['conversation']['interaction'], sort_keys=True))
    lines.append('Supplied B1 policy: ' + json.dumps(packet['policy'], sort_keys=True))
    for profile in value['profile_snapshots']:
        lines.append('Repository profile: ' + profile['repository'])
        lines.append('Presentation guidance (owned editorial interpretation): ' + profile['presentation']['focus'])
        for source in profile['sources']:
            lines.append('Source ' + source['id'] + ': ' + source['kind'] + '; actor=' + str(source['author'])
                         + '; association=' + str(source['author_association']) + '; ' + source['url'])
        for limit in profile['limits']:
            lines.append('Profile limit: ' + limit)
    return '\n'.join(lines) + '\n'


def fixture_rows():
    index = base.read_json(BRIDGE / 'fixtures.json')
    if index['original_scenarios'] != list(range(1, 17)) or len(index['cases']) != 18:
        raise ValueError('full original denominator/supplements differ')
    rows = []
    for row in index['cases']:
        name = row['file']
        if '/' in name or '\\' in name or not name.endswith('.json'):
            raise ValueError('invalid fixture filename')
        rows.append(dict(row, input=base.read_json(BRIDGE / 'fixtures' / name)))
    if [r['scenario'] for r in rows[:16]] != list(range(1, 17)):
        raise ValueError('original scenario identity/order differs')
    return rows


def protocol_rows(rows):
    """Separate counterexamples; these never inflate the original16 denominator."""
    def original(number):
        return deepcopy(next(r['input'] for r in rows if r['scenario'] == number))
    result_rows = []
    for name, scenario, expected, mutate in (
        ('wrong-profile-digest', 5, 'REFUSED_INVALID_CLAIMS:PROFILE_BINDING',
         lambda w: w['profile_ref'].update(sha256='0' * 64)),
        ('production-overstatement', 5, 'REFUSED_INVALID_CLAIMS:CLAIM_OVERSTATEMENT',
         lambda w: next(a for a in w['assertions'] if a['field'] == 'production_incident').update(value='observed')),
        ('stale-profile', 5, 'NEEDS_CURRENT_EVIDENCE:STALE_PROFILE',
         lambda w: w['context'].update(profile_as_of='2026-11-01T00:00:00Z')),
        ('participant-api-approval', 7, 'REFUSED_INVALID_CLAIMS:CLAIM_OVERSTATEMENT',
         lambda w: next(a for a in w['assertions'] if a['field'] == 'api_approval').update(value='observed')),
        ('all-tests-overstatement', 16, 'REFUSED_INVALID_CLAIMS:CLAIM_OVERSTATEMENT',
         lambda w: next(a for a in w['assertions'] if a['field'] == 'overall_test_status').update(value='all_passed')),
        ('hosted-ci-overstatement', 16, 'REFUSED_INVALID_CLAIMS:CLAIM_OVERSTATEMENT',
         lambda w: next(a for a in w['assertions'] if a['field'] == 'ci_status').update(value='passed')),
    ):
        wrapper = original(scenario)
        wrapper['packet']['id'] = 'protocol-' + name
        mutate(wrapper)
        result_rows.append({'scenario': None, 'label': 'protocol-' + name, 'input': wrapper, 'expected': expected})
    return result_rows


def verify_receipt(receipt, rows, baseline, cases_path, code):
    runtime = receipt.get('result', {}).get('runtime', {})
    if (type(code) is not int or code != 0 or receipt.get('decision') != 'PASS'
            or receipt.get('cases_digest') != base.digest(cases_path.read_bytes())
            or receipt.get('manifest_digest') != base.digest((BRIDGE / 'gooo.workspace.json').read_bytes())
            or any(type(runtime.get(k)) is not int or runtime[k] != len(rows)
                   for k in ('finite_total', 'finite_passed'))):
        raise ValueError('incomplete or unbound profile execution')
    traces = runtime.get('traces', [])
    if (len(traces) != len(rows) or any(type(t.get('case_index')) is not int for t in traces)
            or {t['case_index'] for t in traces} != set(range(len(rows)))):
        raise ValueError('profile trace domain differs')
    outputs = {}
    for trace in traces:
        i = trace['case_index']
        deliveries = trace.get('deliveries', [])
        if len(deliveries) != 1:
            raise ValueError('ambiguous profile delivery')
        delivery = deliveries[0]
        observation = facts(rows[i]['input'], baseline[i])
        expected = reference(observation)
        if (delivery.get('activity_id') != ACTIVITY or delivery.get('input') != observation
                or type(delivery['input'].get('base_result')) is not str
                or any(type(delivery['input'].get(k)) is not bool for k in FIELDS[1:])
                or delivery.get('actual') != expected or delivery.get('expected') != expected
                or delivery.get('passed') is not True):
            raise ValueError('profile delivery identity/input/result differs')
        outputs[i] = result(rows[i]['input'], baseline[i], delivery['actual'])
    return [outputs[i] for i in range(len(rows))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gooo', required=True)
    args = parser.parse_args()
    out = ROOT / 'evidence/contribution-profiles'
    out.mkdir(parents=True, exist_ok=True)
    if len(list(out.glob('attempt-*'))) >= 8:
        raise ValueError('retained attempt budget reached')
    attempt = Path(tempfile.mkdtemp(prefix='attempt-', dir=out))
    summary = {'schema': 'gooo-language-bridge/contribution-profiles/v1', 'decision': 'FAIL_CLOSED',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
               'network_requests': 0, 'publication_effects': 0}
    binary = str(Path(args.gooo).resolve())
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')

    def execute(label, bridge, key, observations, expected):
        cases = attempt / (label + '-cases.json')
        cases.write_bytes(base.encoded({'schema': 'gooo/body-composition-cases/v1', 'cases': [
            {'inputs': {key: row}, 'expected': {key: value}} for row, value in zip(observations, expected)]}))
        run = subprocess.run([binary, 'package', 'execute', '--json', '--cases', str(cases),
                              'gooo.workspace.json'], cwd=bridge, env=env, capture_output=True, timeout=90)
        (attempt / (label + '-execution.json')).write_bytes(run.stdout)
        (attempt / (label + '-execution.stderr')).write_bytes(run.stderr)
        summary[label + '_exit_code'] = run.returncode
        return json.loads(run.stdout), cases, run.returncode

    try:
        fixtures = fixture_rows()
        rows = fixtures + protocol_rows(fixtures)
        for profile_id in PROFILE_IDS:
            load_profile(profile_id)
        version = subprocess.run([binary, 'version', '--build', '--json'], capture_output=True, timeout=10)
        (attempt / 'compiler.json').write_bytes(version.stdout)
        (attempt / 'compiler.stderr').write_bytes(version.stderr)
        if version.returncode or json.loads(version.stdout).get('version') != '0.6.38-dev':
            raise ValueError('unsupported compiler')
        baseline_rows = [{'packet': r['input']['packet'], 'expected': base.reference(base.facts(r['input']['packet']))}
                         for r in rows]
        receipt, cases, code = execute('base', base.BRIDGE, base.KEY,
                                       [base.facts(r['packet']) for r in baseline_rows],
                                       [r['expected'] for r in baseline_rows])
        baseline = base.verify_receipt(receipt, baseline_rows, cases, code)
        observations = [facts(r['input'], b) for r, b in zip(rows, baseline)]
        if any(reference(f) != r['expected'] for f, r in zip(observations, rows)):
            raise ValueError('fixture expectations differ')
        receipt, cases, code = execute('profile', BRIDGE, KEY, observations, [r['expected'] for r in rows])
        outputs = verify_receipt(receipt, rows, baseline, cases, code)
        (attempt / 'inputs.json').write_bytes(base.encoded([r['input'] for r in rows]))
        index = []
        for i, output in enumerate(outputs):
            filename = 'result-%02d.json' % i
            (attempt / filename).write_bytes(base.encoded(output))
            for audience in ('maintainer', 'internal'):
                (attempt / ('view-%02d-%s.txt' % (i, audience))).write_text(render(output, audience))
            index.append({'scenario': rows[i]['scenario'], 'label': rows[i]['label'], 'file': filename,
                          'decision': output['decision'], 'reason': output['reason']})
        (attempt / 'results-index.json').write_bytes(base.encoded(index))
        summary.update(decision='PASS', cases=len(rows), original_scenarios=list(range(1, 17)),
                       supplemental_cases=2, protocol_cases=6, profiles=list(PROFILE_IDS),
                       compiler_sha256=base.digest(Path(binary).read_bytes()))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    paths = (list(attempt.iterdir()) + list(BRIDGE.rglob('*')) + [Path(__file__), Path(base.__file__)]
             + list(base.BRIDGE.iterdir()))
    summary['sha256'] = {p.relative_to(ROOT).as_posix(): base.digest(p.read_bytes())
                         for p in sorted(paths) if p.is_file()}
    (attempt / 'attempt-manifest.json').write_bytes(base.encoded(summary))
    summary['sha256'].update({p.relative_to(ROOT).as_posix(): base.digest(p.read_bytes())
                              for p in sorted(out.rglob('*')) if p.is_file() and p != out / 'summary.json'})
    (out / 'summary.json').write_bytes(base.encoded(summary))
    print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
