import copy
import unittest

from tools.verify_input_defaults import (ACTIVITY, INPUTS, OUTPUTS, compare, corpus,
                                         native_rows, reset_counts)


class InputDefaultsEvidence(unittest.TestCase):
    def setUp(self):
        self.rows = corpus()
        self.native = [dict(id=r['id'], overrides=copy.deepcopy(r['overrides']), actual=copy.deepcopy(r['expected']))
                       for r in self.rows]
        traces = []
        for index, row in enumerate(self.rows):
            delivery = dict(activity_id=ACTIVITY, input=copy.deepcopy(row['input']),
                            input_fields=[dict(id=id, name=k, value=row['input'][k]) for k, id in INPUTS.items()],
                            actual=copy.deepcopy(row['expected']), expected=copy.deepcopy(row['expected']), passed=True,
                            actual_fields=[dict(id=id, name=k, value=row['expected'][k]) for k, id in OUTPUTS.items()])
            traces.append(dict(case_index=index, deliveries=[delivery]))
        self.receipt = dict(decision='PASS', cases_digest='cases', manifest_digest='manifest',
                            result=dict(runtime=dict(finite_total=48, finite_passed=48, traces=traces)))

    def test_native_order_domain_and_bool_integer_distinctions_are_required(self):
        variants = [self.native[:-1], self.native + [self.native[0]], list(reversed(self.native))]
        for target, field, value in [('overrides', 'a', False), ('actual', 'b', False), ('actual', 'enabled', 0)]:
            changed = copy.deepcopy(self.native)
            position = next(i for i, r in enumerate(changed) if field in r[target] and r[target][field] == 0)
            changed[position][target][field] = value
            variants.append(changed)
        changed = copy.deepcopy(self.native)
        changed[1]['id'] = changed[0]['id']
        variants.append(changed)
        for value in variants:
            with self.assertRaises(ValueError):
                native_rows(self.rows, value)

    def test_receipt_requires_complete_cases_typed_values_and_stable_ids(self):
        mutations = [
            lambda d: d.update(cases_digest='stale'),
            lambda d: d['result']['runtime'].update(finite_passed=47),
            lambda d: d['result']['runtime']['traces'].pop(),
            lambda d: d['result']['runtime']['traces'][1].update(case_index=0),
            lambda d: d['result']['runtime']['traces'][0]['deliveries'][0].update(activity_id='wrong'),
            lambda d: d['result']['runtime']['traces'][0]['deliveries'][0].update(passed=False),
            lambda d: d['result']['runtime']['traces'][0]['deliveries'][0]['input'].update(enabled_value=0),
            lambda d: d['result']['runtime']['traces'][0]['deliveries'][0]['actual'].update(enabled=0),
            lambda d: d['result']['runtime']['traces'][0]['deliveries'][0]['input_fields'][0].update(id='wrong'),
            lambda d: d['result']['runtime']['traces'][0]['deliveries'][0]['actual_fields'][0].update(id='wrong'),
        ]
        for change in mutations:
            changed = copy.deepcopy(self.receipt)
            change(changed)
            with self.assertRaises(ValueError):
                compare(self.rows, self.native, changed, 'cases', 'manifest')

    def test_corpus_preserves_zero_false_and_exercises_reset_transitions(self):
        self.assertEqual(len(self.rows), 48)
        self.assertEqual(len({r['id'] for r in self.rows}), 48)
        self.assertEqual(len({tuple(sorted(r['overrides'].items())) for r in self.rows}), 48)
        resolved = compare(self.rows, self.native, self.receipt, 'cases', 'manifest')
        self.assertTrue(all(type(n) is int and n > 0 for n in reset_counts(resolved).values()))
        zero_false = next(r for r in resolved if r['overrides'] == {'b': 0, 'enabled': False})
        self.assertEqual(zero_false['native'], {'a': 0, 'b': 0, 'enabled': False})
        self.assertIs(zero_false['input']['a_present'], False)
        self.assertIs(zero_false['input']['b_present'], True)
        with self.assertRaises(ValueError):
            reset_counts([next(r for r in resolved if not r['overrides'])])
