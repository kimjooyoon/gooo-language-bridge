import copy
import json
from pathlib import Path
import unittest

from tools.verify_hcl_defaults import ACTIVITY, INPUTS, OUTPUTS, compare, corpus, native_rows


class HCLDefaultsEvidence(unittest.TestCase):
    def setUp(self):
        self.rows = corpus()
        self.constraints = json.loads((Path(__file__).resolve().parents[1] / 'bridges/hcl-null-defaults/provenance.json').read_text())['constraints']
        self.native = []
        traces = []
        for i, r in enumerate(self.rows):
            before = {} if r['state'] == 'missing' else {'v': None if r['state'] == 'null' else r['value']}
            after = dict(before)
            if r['input']['is_optional'] and r['input']['default_present'] and r['state'] in ('missing', 'null'):
                after = {'v': r['input']['default_value']}
            expected = r['expected']
            self.native.append(dict(id=r['id'], declaration=r['declaration'], state=r['state'], value=r['value'],
                                    constraint=self.constraints[r['declaration']], input=before, after_defaults=after,
                                    actual=copy.deepcopy(expected), result={'v': None if expected['is_null'] else expected['value']} if expected['accepted'] else None,
                                    diagnostic='' if expected['accepted'] else 'attribute "v" is required'))
            delivery = dict(activity_id=ACTIVITY, input=copy.deepcopy(r['input']), actual=copy.deepcopy(expected),
                            expected=copy.deepcopy(expected), passed=True,
                            input_fields=[dict(name=k, id=v, value=r['input'][k]) for k, v in INPUTS.items()],
                            actual_fields=[dict(name=k, id=v, value=expected[k]) for k, v in OUTPUTS.items()])
            traces.append(dict(case_index=i, deliveries=[delivery]))
        self.receipt = dict(decision='PASS', cases_digest='cases', manifest_digest='manifest',
                            result=dict(runtime=dict(finite_total=20, finite_passed=20, traces=traces)))

    def test_domain_keeps_missing_null_zero_and_default_zero_distinct(self):
        self.assertEqual(len({tuple(sorted(r['input'].items())) for r in self.rows}), 20)
        indexed = {r['id']: r['expected'] for r in self.rows}
        self.assertEqual(indexed['required/missing/0'], dict(accepted=False, is_null=False, value=0))
        self.assertEqual(indexed['required/null/0'], dict(accepted=True, is_null=True, value=0))
        self.assertEqual(indexed['default-zero/null/0'], dict(accepted=True, is_null=False, value=0))
        self.assertEqual(indexed['default-42/number/0'], dict(accepted=True, is_null=False, value=0))
        self.assertEqual(indexed['default-42/null/0']['value'], 42)
        compare(self.rows, self.native, self.receipt, 'cases', 'manifest', self.constraints)

    def test_native_projection_cannot_hide_missing_fields_null_or_boolean_zero(self):
        mutations = [lambda d: d.pop(), lambda d: d.reverse(),
                     lambda d: d[0].update(input={'v': None}),
                     lambda d: d[0].update(diagnostic=''),
                     lambda d: d[1]['actual'].update(is_null=False),
                     lambda d: d[3].update(input={'v': False}),
                     lambda d: d[10].update(after_defaults={}),
                     lambda d: d[10]['actual'].update(value=False),
                     lambda d: d[15].update(constraint='different')]
        for mutate in mutations:
            data = copy.deepcopy(self.native); mutate(data)
            with self.assertRaises(ValueError): native_rows(self.rows, data, self.constraints)

    def test_receipt_requires_complete_typed_source_bound_semantic_fields(self):
        mutations = [lambda d: d.update(cases_digest='stale'),
                     lambda d: d['result']['runtime'].update(finite_passed=19),
                     lambda d: d['result']['runtime']['traces'][1].update(case_index=0),
                     lambda d: d['result']['runtime']['traces'][0]['deliveries'][0].update(activity_id='wrong'),
                     lambda d: d['result']['runtime']['traces'][0]['deliveries'][0].update(passed=False),
                     lambda d: d['result']['runtime']['traces'][0]['deliveries'][0]['input'].update(input_value=False),
                     lambda d: d['result']['runtime']['traces'][0]['deliveries'][0]['actual'].update(value=False),
                     lambda d: d['result']['runtime']['traces'][0]['deliveries'][0]['input_fields'][0].update(id='wrong'),
                     lambda d: d['result']['runtime']['traces'][0]['deliveries'][0]['actual_fields'].pop()]
        for mutate in mutations:
            data = copy.deepcopy(self.receipt); mutate(data)
            with self.assertRaises(ValueError): compare(self.rows, self.native, data, 'cases', 'manifest', self.constraints)
