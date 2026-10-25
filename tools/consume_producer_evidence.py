"""Read a fixed reference-only P1 export and run the existing B1/B2 plans."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import plan_profile_response as profile
from tools.check_candidates import captured_run

base = profile.base
ROOT = base.ROOT
BRIDGE = ROOT / 'bridges/producer-response'
PHASES = ('native_execution', 'oracle_comparison', 'saved_replay')
ENTRY = 'app/diagnostic-header-addition:AssessAddition'
PAYLOADS = ('appendix.json', 'technical-preview.txt') + tuple(p + '.evidence.json' for p in PHASES)
FILES = ('manifest.json',) + PAYLOADS
EVIDENCE_SCHEMA_SHA256 = '1b9c4d455554976ff8e1c3ccf3c533bea1de6bf5567e92d979c3f372b2ab9e12'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def published_source(provenance):
    require(provenance['status'] == 'PUBLISHED_P1_SOURCE_AND_FROZEN_BYTES_VERIFIED',
            'P1 publication/acceptance evidence is not ready')
    source = provenance['exporter_source']
    ci = provenance['exporter_ci']
    require(re.fullmatch('[0-9a-f]{40}', source['accepted_commit']) is not None
            and re.fullmatch('[0-9a-f]{40}', source['tested_head']) is not None
            and re.fullmatch('[0-9a-f]{40}', source['accepted_tree']) is not None
            and source['accepted_tree'] == source['tested_tree']
            and re.fullmatch('[0-9a-f]{64}', source['exporter_sha256']) is not None,
            'P1 source identities incomplete')
    require(ci['head'] == source['tested_head'] and ci['conclusion'] == 'success'
            and type(ci['run_id']) is int and ci['run_id'] > 0, 'P1 source CI binding differs')
    asset = provenance['frozen_asset']
    require(asset['url'].startswith('https://github.com/kimjooyoon/gooo-go-ports/releases/download/')
            and re.fullmatch('[0-9a-f]{64}', asset['sha256']) is not None
            and type(asset['bytes']) is int and asset['bytes'] > 0
            and asset['manifest_sha256'] == provenance['manifest_sha256'], 'P1 published byte binding differs')


def snapshot(directory):
    directory = Path(directory)
    require(not directory.is_symlink() and directory.is_dir(), 'expected regular bundle directory')
    require({p.name for p in directory.iterdir()} == set(FILES), 'producer file inventory differs')
    raw = {}
    for name in FILES:
        path = directory / name
        require(not path.is_symlink() and path.is_file(), 'nonregular producer file')
        require(path.stat().st_size <= base.MAX_BYTES, 'producer file exceeds byte budget')
        raw[name] = path.read_bytes()
    require(sum(map(len, raw.values())) <= 256 * 1024, 'producer bundle exceeds byte budget')
    return raw


def parsed(data):
    require(len(data) <= base.MAX_BYTES, 'JSON exceeds byte budget')
    return json.loads(data, object_pairs_hook=base.unique, parse_constant=base.invalid_constant)


def load_bundle(directory, expected_manifest):
    require(re.fullmatch('[0-9a-f]{64}', expected_manifest) is not None, 'expected full manifest SHA-256')
    raw = snapshot(directory)
    require(sha(raw['manifest.json']) == expected_manifest, 'producer manifest digest differs')
    manifest = parsed(raw['manifest.json'])
    require(set(manifest) == {'schema', 'state', 'contract_schema_sha256', 'files',
                              'native_acceptance', 'producer_authenticated'}, 'producer manifest fields differ')
    require(manifest['schema'] == 'gooo/header-addition-contribution-export/v1'
            and manifest['state'] == 'EXPORTED_REFERENCE_OBSERVATIONS', 'unsupported producer envelope')
    require(manifest['native_acceptance'] is False and manifest['producer_authenticated'] is False,
            'unsupported producer authority claim')
    require(manifest['contract_schema_sha256'] == EVIDENCE_SCHEMA_SHA256
            == sha((base.BRIDGE / 'evidence.schema.json').read_bytes()), 'producer/B1 schema binding differs')
    require(type(manifest['files']) is dict and set(manifest['files']) == set(PAYLOADS), 'payload inventory differs')
    for name, metadata in manifest['files'].items():
        require(type(metadata) is dict and set(metadata) == {'bytes', 'sha256'}
                and type(metadata['bytes']) is int and metadata['bytes'] == len(raw[name])
                and metadata['sha256'] == sha(raw[name]), 'payload size/digest differs: ' + name)
    appendix = parsed(raw['appendix.json'])
    require(appendix['schema'] == 'gooo/header-addition-contribution-appendix/v1'
            and appendix['entry'] == ENTRY and appendix['origin'] == 'frozen_observation', 'appendix identity differs')
    state = appendix['reader_state']
    require(state['native_acceptance'] is False and state['producer_authenticated'] is False
            and state['raw_receipts_inspected'] is True, 'appendix reader state differs')
    require(type(appendix['rows']) is list and type(appendix['case_names']) is list
            and all(type(name) is str and name for name in appendix['case_names']), 'selected domain types differ')
    require(type(appendix['selected_cases']) is int and appendix['selected_cases'] == 50
            and len(appendix['rows']) == len(appendix['case_names']) == 50
            and len(set(appendix['case_names'])) == 50, 'fixed selected case domain differs')
    require(type(appendix['selected_batches']) is int and appendix['selected_batches'] == 7
            and type(appendix['complete_reader_suite_count']) is int
            and appendix['complete_reader_suite_count'] > 0, 'reported population types differ')
    receipts = appendix['receipts']
    require(type(receipts) is list and all(type(r) is dict for r in receipts), 'receipt reference types differ')
    require(len(receipts) == 14, 'receipt reference count differs')
    pairs = {(r['batch'], r['operation']): r for r in receipts}
    require(all(type(r['batch']) is int for r in receipts)
            and set(pairs) == {(i, op) for i in range(7) for op in ('execute', 'replay')}, 'receipt reference domain differs')
    for batch in range(7):
        executed, replayed = pairs[batch, 'execute'], pairs[batch, 'replay']
        require(executed['cases_digest'] == replayed['cases_digest']
                and replayed['original_receipt_sha256'] == 'sha256:' + executed['receipt_sha256'],
                'saved replay parent differs')
    failure = appendix['producer_first_failure']
    require(failure['native_acceptance'] is False and failure['phase'] == 'join'
            and failure['context'] == appendix['reported_run'] and type(failure['error']) is str
            and bool(failure['error']), 'original join failure missing or misbound')
    records = []
    for phase in PHASES:
        record = parsed(raw[phase + '.evidence.json'])
        base.validate(record, base.read_json(base.BRIDGE / 'evidence.schema.json'))
        require(record['origin'] == 'frozen_observation' and record['execution']['phase'] == phase,
                'producer phase/origin differs')
        run = record['execution']
        require(all(run[k] == 'not_compared' for k in ('comparison', 'base_outcome', 'candidate_outcome')),
                'producer record invents base/candidate comparison')
        identity = record['identities']
        require(all(identity[k] is None for k in ('source_commit', 'source_blob', 'base_commit',
                                                  'candidate_commit', 'reference_commit')),
                'reported Git identity promoted to authenticated evidence')
        appendix_sha = sha(raw['appendix.json'])
        require(record['references'] == [{'id': 'selected-typed-appendix', 'url': 'urn:sha256:' + appendix_sha,
                                          'sha256': appendix_sha}], 'record appendix reference differs')
        require(record['id'] == 'urn:gooo:ports:header-addition:' + appendix_sha + ':' + phase,
                'record ID differs from phase/appendix')
        require(bool(record['failures']) and bool(record['uncertainty']) and bool(record['exclusions']),
                'producer material limits missing')
        records.append(record)
    require(len({r['id'] for r in records}) == 3, 'duplicate producer identity')
    return {'raw': raw, 'manifest': manifest, 'manifest_sha256': expected_manifest,
            'appendix': appendix, 'records': records}


def make_wrapper(bundle, template):
    wrapper = deepcopy(template)
    packet, appendix = wrapper['packet'], bundle['appendix']
    require(not packet['claims'] and not packet['evidence'] and not wrapper['assertions'], 'context must not supply producer claims')
    require(packet['origin'] == 'frozen_observation' and packet['repository'] == appendix['reported_run']['repository'],
            'review context repository/origin differs')
    require(packet['conversation']['snapshot_id'] == 'producer-manifest:' + bundle['manifest_sha256'],
            'review context is bound to another producer snapshot')
    packet['evidence'] = deepcopy(bundle['records'])
    for record in bundle['records']:
        claim_id = 'P1-' + record['execution']['phase']
        packet['claims'].append({'id': claim_id, 'actor_id': packet['actor']['id'],
                                 'asserted_role': packet['actor']['observed_role'], 'kind': 'bounded_confirmation',
                                 'status': 'observed', 'tested_revision': None, 'evidence_ids': [record['id']],
                                 **{k: deepcopy(record[k]) for k in ('uncertainty', 'failures', 'exclusions')}})
        wrapper['assertions'] += [{'claim_id': claim_id, 'field': 'execution_phase', 'value': record['execution']['phase']},
                                  {'claim_id': claim_id, 'field': 'execution_outcome', 'value': record['execution']['outcome']},
                                  {'claim_id': claim_id, 'field': 'overall_test_status', 'value': 'scope_only'}]
    packet['failures'].append('Reported producer join failure: ' + appendix['producer_first_failure']['error'])
    expected = appendix['rows'][0]['expected'][ENTRY]
    wrapper['example'] = {'input': 'Saved case: ' + appendix['case_names'][0],
                          'observed': '; '.join(r['execution']['phase'] + '/' + r['execution']['outcome'] for r in bundle['records']),
                          'expected': 'Supplied expectation: ' + json.dumps({k: expected[k] for k in ('status', 'reason')}, sort_keys=True)}
    profile.validate(wrapper, 'input.schema.json')
    return wrapper


def response_result(bundle, planned):
    wrapper = planned['input']
    require(wrapper['packet']['evidence'] == bundle['records'], 'planned producer records differ')
    require(planned == profile.result(wrapper, planned['base_result'], planned['decision'] + ':' + planned['reason']),
            'profile result binding differs')
    appendix = bundle['appendix']
    return {'schema': 'gooo/producer-response/v1', 'effect': 'none',
            'producer_manifest_sha256': bundle['manifest_sha256'],
            'producer_files': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in bundle['raw'].items()},
            'producer_observations': {'origin': appendix['origin'], 'entry': appendix['entry'],
                                      'native_acceptance': False, 'producer_authenticated': False,
                                      'selected_cases': appendix['selected_cases'], 'selected_batches': appendix['selected_batches'],
                                      'reported_complete_reader_suites': appendix['complete_reader_suite_count'],
                                      'receipt_references': len(appendix['receipts']),
                                      'reported_run': deepcopy(appendix['reported_run']),
                                      'producer_first_failure': deepcopy(appendix['producer_first_failure'])},
            'planning': deepcopy(planned)}


def render(bundle, value):
    require(value == response_result(bundle, value['planning']), 'producer presentation binding differs')
    source = value['producer_observations']
    detail = profile.render(value['planning'])
    actions = [line for line in detail.splitlines() if line.startswith('One next action: ')]
    require(len(actions) == 1, 'ambiguous next action in supplied context')
    packet = value['planning']['input']['packet']
    lines = ['# Saved producer evidence response plan', '',
             'Selected: 50 recorded HeaderAddition cases, 7 batches, 14 execute/replay references.',
             'P1 reports checking ' + str(source['reported_complete_reader_suites'])
             + ' suites before selection; this consumer does not rerun that full reader.',
             'Producer authentication and native acceptance remain false. Reported Git identities remain metadata.',
             'Original producer join failure (source data): ' + json.dumps(source['producer_first_failure']['error']),
             '', 'Recorded phases: ' + json.dumps({r['execution']['phase']: r['execution']['outcome'] for r in bundle['records']}),
             'Supplied example (data): ' + json.dumps(value['planning']['input']['example'], sort_keys=True),
             'Plan: ' + value['planning']['decision'] + ':' + value['planning']['reason'],
             'Claim IDs/statuses: ' + json.dumps([(c['id'], c['status']) for c in packet['claims']]),
             '', actions[0], '', 'Material limits (source data):']
    for field in ('uncertainty', 'failures', 'exclusions'):
        items = list(dict.fromkeys(packet[field] + [text for r in bundle['records'] for text in r[field]]))
        lines.append(field + ': ' + json.dumps(items, ensure_ascii=False))
    lines += ['', '[Full bound plan](plan-detail.txt) · [Machine result](result.json)',
              '[Complete source appendix](source/appendix.json) · [Original technical preview](source/technical-preview.txt)']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gooo', required=True)
    parser.add_argument('--bundle', type=Path, default=BRIDGE / 'fixtures/p1-40138087345')
    parser.add_argument('--context', type=Path, default=BRIDGE / 'review-context.json')
    parser.add_argument('--manifest-sha256', default=base.read_json(BRIDGE / 'provenance.json')['manifest_sha256'])
    parser.add_argument('--require-published-source', action='store_true')
    args = parser.parse_args()
    root = ROOT / 'evidence/producer-response'
    root.mkdir(parents=True, exist_ok=True)
    require(len(list(root.glob('attempt-*'))) < 8, 'retained attempt budget reached')
    out = Path(tempfile.mkdtemp(prefix='attempt-', dir=root))
    summary = {'schema': 'gooo-language-bridge/producer-response/v1', 'decision': 'FAIL_CLOSED',
               'commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
               'network_requests': 0, 'producer_native_executions': 0, 'publication_effects': 0}
    binary = str(Path(args.gooo).resolve())
    env = dict(os.environ, GOTOOLCHAIN='go1.27.3', GOWORK='off')

    def execute(label, bridge, key, observations, expected):
        cases = out / (label + '-cases.json')
        cases.write_bytes(base.encoded({'schema': 'gooo/body-composition-cases/v1',
                                      'cases': [{'inputs': {key: observations}, 'expected': {key: expected}}]}))
        process = captured_run([binary, 'package', 'execute', '--json', '--cases', str(cases), 'gooo.workspace.json'],
                               out, label + '-execution.json', label + '-execution.stderr', summary, label,
                               cwd=bridge, env=env, timeout=90)
        return json.loads(process.stdout), cases, process.returncode

    try:
        if args.require_published_source:
            provenance = base.read_json(BRIDGE / 'provenance.json')
            published_source(provenance)
            require(args.manifest_sha256 == provenance['manifest_sha256'], 'active input differs from published source pin')
        captured = snapshot(args.bundle)
        (out / 'source').mkdir()
        for name, data in captured.items():
            (out / 'source' / name).write_bytes(data)
        bundle = load_bundle(out / 'source', args.manifest_sha256)
        context_bytes = args.context.read_bytes()
        (out / 'context.json').write_bytes(context_bytes)
        context = parsed(context_bytes)
        wrapper = make_wrapper(bundle, context)
        (out / 'input.json').write_bytes(base.encoded(wrapper))
        version = captured_run([binary, 'version', '--build', '--json'], out, 'compiler.json',
                               'compiler.stderr', summary, 'compiler', timeout=10)
        require(version.returncode == 0 and json.loads(version.stdout).get('version') == '0.6.38-dev', 'unsupported compiler')
        packet = wrapper['packet']
        previous = base.reference(base.facts(packet))
        receipt, cases, code = execute('base', base.BRIDGE, base.KEY, base.facts(packet), previous)
        base_result = base.verify_receipt(receipt, [{'packet': packet, 'expected': previous}], cases, code)[0]
        expected = profile.reference(profile.facts(wrapper, base_result))
        receipt, cases, code = execute('profile', profile.BRIDGE, profile.KEY, profile.facts(wrapper, base_result), expected)
        planned = profile.verify_receipt(receipt, [{'input': wrapper, 'expected': expected}], [base_result], cases, code)[0]
        value = response_result(bundle, planned)
        (out / 'result.json').write_bytes(base.encoded(value))
        (out / 'response.md').write_text(render(bundle, value))
        (out / 'plan-detail.txt').write_text(profile.render(planned))
        summary.update(decision='PASS', stage='complete', producer_manifest_sha256=bundle['manifest_sha256'],
                       producer_records=3, selected_cases=50, selected_batches=7, receipt_references=14,
                       reported_complete_reader_suites=bundle['appendix']['complete_reader_suite_count'],
                       planning_decision=planned['decision'],
                       gooo_decision_executions=2,
                       native_acceptance=False, producer_authenticated=False, compiler_sha256=sha(Path(binary).read_bytes()))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    paths = list(out.rglob('*')) + list(BRIDGE.rglob('*')) + [Path(__file__), Path(base.__file__), Path(profile.__file__),
                                                          ROOT / 'tools/check_candidates.py']
    paths += list(base.BRIDGE.iterdir()) + list(profile.BRIDGE.rglob('*'))
    summary['sha256'] = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(paths) if p.is_file()}
    (out / 'attempt-manifest.json').write_bytes(base.encoded(summary))
    summary['sha256'].update({p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(root.rglob('*'))
                              if p.is_file() and p != root / 'summary.json'})
    (root / 'summary.json').write_bytes(base.encoded(summary))
    print(json.dumps(summary))
    return 0 if summary['decision'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
