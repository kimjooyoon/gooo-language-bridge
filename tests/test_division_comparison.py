import copy
import unittest
from tools.compare_division import ACTIVITY, comparison_rows
from tools.verify import cases


class DivisionEvidence(unittest.TestCase):
    def setUp(self):
        self.cases = cases()['cases']
        self.native = []
        traces = []
        for index, case in enumerate(self.cases):
            a = case['inputs']['bridge/python:FloorDivide.input0']
            b = case['inputs']['bridge/python:FloorDivide.input1']
            quotient = int(a / b)  # All fixture inputs are small enough for exact float conversion.
            self.native.append({'a': a, 'b': b, 'quotient': quotient, 'remainder': a - b * quotient})
            traces.append({'case_index': index, 'deliveries': [{
                'activity_id': ACTIVITY,
                'inputs': [{'port': 'input0', 'value': a, 'entity_id': 'urn:gooo:type:integer'},
                           {'port': 'input1', 'value': b, 'entity_id': 'urn:gooo:type:integer'}],
                'actual': a // b, 'expected': a // b, 'passed': True}]})
        self.receipt = {'decision': 'PASS', 'result': {'runtime': {
            'finite_passed': 120, 'finite_total': 120, 'traces': traces}}}

    def test_trace_order_is_not_case_identity(self):
        self.receipt['result']['runtime']['traces'].reverse()
        rows = comparison_rows(self.cases, list(reversed(self.native)), self.receipt)
        self.assertEqual(len(rows), 120)
        self.assertEqual(sum(r['go_quotient'] != r['python_floor'] for r in rows), 30)

    def test_a_pass_counter_does_not_replace_missing_or_unique_observations(self):
        for change in ('missing', 'duplicate'):
            with self.subTest(change=change):
                receipt = copy.deepcopy(self.receipt)
                traces = receipt['result']['runtime']['traces']
                if change == 'missing':
                    traces.pop()
                else:
                    traces[-1] = copy.deepcopy(traces[0])
                with self.assertRaises(ValueError):
                    comparison_rows(self.cases, self.native, receipt)
        self.native[-1] = self.native[0]
        with self.assertRaises(ValueError):
            comparison_rows(self.cases, self.native, self.receipt)

    def test_go_floor_division_cannot_impersonate_native_truncation(self):
        row = next(r for r in self.native if r['a'] == -7 and r['b'] == 3)
        row.update(quotient=-3, remainder=2)
        with self.assertRaises(ValueError):
            comparison_rows(self.cases, self.native, self.receipt)

    def test_wrong_activity_input_actual_and_expectation_are_rejected(self):
        for field in ('activity', 'input', 'actual', 'expected', 'boolean'):
            with self.subTest(field=field):
                receipt = copy.deepcopy(self.receipt)
                delivery = receipt['result']['runtime']['traces'][0]['deliveries'][0]
                if field == 'activity':
                    delivery['activity_id'] = 'urn:other:activity'
                elif field == 'input':
                    delivery['inputs'][0]['value'] = 999
                elif field == 'boolean':
                    delivery['actual'] = True  # First expected value is 1, but bool is not Integer.
                else:
                    delivery[field] = 999
                with self.assertRaises(ValueError):
                    comparison_rows(self.cases, self.native, receipt)
