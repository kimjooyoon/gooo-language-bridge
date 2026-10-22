import copy
import unittest
from tools.compare_division import ACTIVITY, EDGE_PAIRS, comparison_rows, include_lua, lua_edges
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

    def test_lua_requires_unique_complete_observations_and_exact_integers(self):
        rows = comparison_rows(self.cases, self.native, self.receipt)
        native = [{'a': r['a'], 'b': r['b'], 'quotient': r['python_floor']} for r in rows]
        joined = include_lua(rows, list(reversed(native)))
        self.assertEqual(len(joined), 120)
        self.assertTrue(all(r['lua_floor'] == r['gooo_actual'] for r in joined))
        variants = [native[:-1], native + [native[0]], native + [{'a': 100, 'b': 1, 'quotient': 100}]]
        for value in (True, 1.0, 999):
            changed = copy.deepcopy(native)
            changed[0]['quotient'] = value
            variants.append(changed)
        changed = copy.deepcopy(native)
        changed[0]['error'] = 'unexpected execution failure'
        variants.append(changed)
        for invalid in variants:
            with self.assertRaises(ValueError):
                include_lua(rows, invalid)

    def test_lua_boundaries_remain_outside_gooo_match_counts(self):
        native = [dict(EDGE_PAIRS[0], quotient=-(1 << 63)),
                  dict(EDGE_PAIRS[1], quotient=(1 << 63) - 1),
                  dict(EDGE_PAIRS[2], error='error: floor-reference:1: attempt to divide by zero')]
        rows = lua_edges(native)
        self.assertTrue(all(r['in_gooo_domain'] is False for r in rows))
        self.assertEqual(rows[0]['python_floor_decimal'], '9223372036854775808')
        self.assertEqual(rows[0]['lua_floor_decimal'], '-9223372036854775808')
        self.assertIs(rows[0]['same_integer_result'], False)
        self.assertIs(rows[1]['same_integer_result'], True)
        self.assertEqual(rows[2]['python_error'], 'ZeroDivisionError')
        for position, key, value in [(0, 'quotient', 1 << 63), (0, 'quotient', True),
                                     (2, 'error', 'memory quota exceeded')]:
            invalid = copy.deepcopy(native)
            invalid[position][key] = value
            with self.assertRaises(ValueError):
                lua_edges(invalid)
        with self.assertRaises(ValueError):
            lua_edges(native[:-1])
