"""Structured claims are retained; a presentation never creates authority."""
from copy import deepcopy
from itertools import product
from pathlib import Path
import tempfile
import unittest

from tools.plan_response import (
    ACTIVITY, BRIDGE, FIELDS, digest, encoded, facts, read_json, reference,
    render, result, validate, verify_receipt,
)


class ResponsePlanningTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = read_json(BRIDGE / 'fixtures.json')
        self.rows = self.fixtures['cases']
        self.packet = deepcopy(self.rows[4]['packet'])

    def test_six_original_scenarios_are_distinct_from_supplements(self):
        self.assertEqual([r['scenario'] for r in self.rows if r['scenario'] is not None],
                         [1, 2, 3, 4, 6, 15])
        self.assertEqual(len(self.fixtures['remaining_original_scenarios']), 10)
        for row in self.rows:
            with self.subTest(label=row['label']):
                self.assertEqual(reference(facts(row['packet'])), row['expected'])
                self.assertEqual(row['packet']['origin'], 'synthetic')

    def test_all_boolean_policy_inputs_have_one_no_effect_decision(self):
        outputs = set()
        for values in product((False, True), repeat=6):
            outputs.add(reference(dict(zip(FIELDS, values))).split(':')[0])
        self.assertEqual(outputs, {'REFUSED_INVALID_CLAIMS', 'NEEDS_CURRENT_EVIDENCE',
                                  'EXTERNAL_REQUIREMENT_UNSATISFIED', 'NO_POST', 'BOUNDED_DRAFT_READY'})
        with self.assertRaises(ValueError):
            reference(dict(zip(FIELDS, [1] * 6)))

    def test_exact_version_shape_and_bounds(self):
        for change in (
            lambda p: p.update(schema='unrecognized/v2'),
            lambda p: p.update(requested=1),
            lambda p: p.update(authority='approve'),
            lambda p: p['conversation'].update(max_age_seconds=True),
            lambda p: p['evidence'][0]['identities'].update(source_commit='blob:abc'),
            lambda p: p.update(uncertainty=['x'] * 17),
            lambda p: p['claims'].append(deepcopy(p['claims'][0])),
        ):
            packet = deepcopy(self.packet)
            change(packet)
            with self.assertRaises(ValueError):
                facts(packet)

    def test_wrong_role_and_missing_evidence_are_refused(self):
        self.packet['claims'][0]['asserted_role'] = 'author'
        self.assertEqual(reference(facts(self.packet)), 'REFUSED_INVALID_CLAIMS:ROLE_UNESTABLISHED')
        self.packet = deepcopy(self.rows[4]['packet'])
        self.packet['claims'][0]['evidence_ids'] = ['not-present']
        self.assertEqual(reference(facts(self.packet)), 'REFUSED_INVALID_CLAIMS:EVIDENCE_BINDING')

    def test_claims_execution_source_and_context_must_share_tested_revision(self):
        for mutate in (
            lambda p: p['conversation'].update(tested_head='5' * 40, current_head='5' * 40),
            lambda p: p['evidence'][0]['identities'].update(source_commit='6' * 40),
        ):
            packet = deepcopy(self.packet)
            mutate(packet)
            self.assertEqual(reference(facts(packet)), 'REFUSED_INVALID_CLAIMS:EVIDENCE_BINDING')

    def test_unknown_external_requirement_does_not_create_a_human_approval_lane(self):
        self.packet['policy']['external_requirement'] = 'unknown'
        value = result(self.packet, reference(facts(self.packet)))
        self.assertEqual(value['decision'], 'EXTERNAL_REQUIREMENT_UNSATISFIED')
        self.assertEqual(value['effect'], 'none')
        self.assertNotIn('human approval', render(value))

    def test_current_composer_does_not_establish_permission(self):
        packet = deepcopy(self.rows[1]['packet'])
        value = result(packet, reference(facts(packet)))
        self.assertEqual(value['packet']['conversation']['interaction']['permission'], 'unknown')
        text = render(value)
        self.assertIn('"composer": "editable"', text)
        self.assertIn('"permission": "unknown"', text)
        self.assertIn('Historical unavailable composer', text)
        self.assertNotIn('was unblocked', text)

    def test_freshness_includes_time_head_and_feedback(self):
        for field, value in (('as_of', '2026-10-23T20:00:00Z'),
                             ('current_head', '3' * 40),
                             ('current_snapshot_id', 'changed-feedback')):
            packet = deepcopy(self.packet)
            packet['conversation'][field] = value
            self.assertEqual(reference(facts(packet)), 'NEEDS_CURRENT_EVIDENCE:STALE_SNAPSHOT')
        self.packet['conversation']['observed_at'] = '2026-10-22T20:00:00'
        with self.assertRaises(ValueError):
            facts(self.packet)

    def test_base_comparison_and_unknown_execution_cannot_support_fixed_claim(self):
        for field, value in (('comparison', 'candidate_only'), ('base_outcome', 'not_compared'),
                             ('phase', 'not_executed'), ('candidate_outcome', 'fail')):
            packet = deepcopy(self.packet)
            packet['evidence'][0]['execution'][field] = value
            self.assertEqual(reference(facts(packet)), 'REFUSED_INVALID_CLAIMS:COMPARISON_UNSUPPORTED')

    def test_presentation_preserves_every_claim_uncertainty_failure_and_exclusion(self):
        value = result(self.packet, reference(facts(self.packet)))
        before = encoded(value)
        text = render(value)
        self.assertEqual(text, render(value))
        self.assertEqual(encoded(value), before)
        self.assertEqual(value['packet'], self.packet)
        self.assertIn('One next action:', text)
        self.assertEqual(text.count('One next action:'), 1)
        for record in [self.packet] + self.packet['claims'] + self.packet['evidence']:
            if 'id' in record:
                self.assertIn(record['id'], text)
            for field in ('uncertainty', 'failures', 'exclusions'):
                for entry in record[field]:
                    self.assertIn(entry, text)
        for field in ('input_digest', 'policy_digest'):
            changed = deepcopy(value)
            changed[field] = 'sha256:' + '0' * 64
            with self.assertRaises(ValueError):
                render(changed)

    def test_refused_or_stale_claim_is_not_presented_as_a_current_fix(self):
        for row in self.rows:
            value = result(row['packet'], row['expected'])
            if value['decision'] in ('REFUSED_INVALID_CLAIMS', 'NEEDS_CURRENT_EVIDENCE'):
                self.assertNotIn('reports the original finding resolved', render(value))

    def test_json_duplicate_keys_and_nonfinite_constants_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'packet.json'
            for content in ('{"id":1,"id":2}', '{"x":NaN}', 'x' * (128 * 1024 + 1)):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    read_json(path)

    def test_receipt_requires_bound_activity_inputs_complete_domain_and_actual_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.json'
            path.write_bytes(b'{}')
            traces = []
            for i, row in enumerate(self.rows):
                observed = facts(row['packet'])
                traces.append({'case_index': i, 'deliveries': [{
                    'activity_id': ACTIVITY, 'input': observed, 'actual': row['expected'],
                    'expected': row['expected'], 'passed': True}]})
            receipt = {'decision': 'PASS', 'cases_digest': digest(path.read_bytes()),
                       'manifest_digest': digest((BRIDGE / 'gooo.workspace.json').read_bytes()),
                       'result': {'runtime': {'finite_total': len(self.rows),
                                              'finite_passed': len(self.rows), 'traces': traces}}}
            outputs = verify_receipt(receipt, self.rows, path, 0)
            self.assertEqual(len(outputs), len(self.rows))
            mutations = [lambda r: r.update(cases_digest='stale'),
                         lambda r: r['result']['runtime'].update(finite_total=True),
                         lambda r: r['result']['runtime']['traces'].pop(),
                         lambda r: r['result']['runtime']['traces'][0]['deliveries'][0].update(activity_id='wrong'),
                         lambda r: r['result']['runtime']['traces'][0]['deliveries'][0].update(actual='made-up'),
                         lambda r: r['result']['runtime']['traces'][0]['deliveries'][0]['input'].update(roles_match=1)]
            for mutate in mutations:
                changed = deepcopy(receipt)
                mutate(changed)
                with self.assertRaises(ValueError):
                    verify_receipt(changed, self.rows, path, 0)

    def test_producer_evidence_contract_stands_alone(self):
        evidence = deepcopy(self.packet['evidence'][0])
        evidence['origin'] = 'producer_observation'
        validate(evidence, read_json(BRIDGE / 'evidence.schema.json'))
        self.assertNotIn('policy', evidence)
        self.assertNotIn('actor', evidence)
        evidence['decision'] = 'PUBLISH'
        with self.assertRaises(ValueError):
            validate(evidence, read_json(BRIDGE / 'evidence.schema.json'))

    def test_unknown_or_compiled_evidence_is_not_a_successful_behavior_test(self):
        for phase, outcome in (('unknown', 'unknown'), ('compile', 'pass')):
            packet = deepcopy(self.packet)
            packet['evidence'][0]['execution'].update(phase=phase, outcome=outcome)
            validate(packet['evidence'][0], read_json(BRIDGE / 'evidence.schema.json'))
            self.assertEqual(reference(facts(packet)), 'REFUSED_INVALID_CLAIMS:COMPARISON_UNSUPPORTED')
