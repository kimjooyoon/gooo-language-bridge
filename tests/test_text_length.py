"""Adversarial checks for unit identity and incomplete observation rejection."""
from copy import deepcopy
import unittest

from tools.compare_text_length import ACTIVITY, FIELDS, compare, corpus, python_lengths


class TextLengthEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'id': 'astral', 'text': '🙂'}]
        value = {'utf8_bytes': 4, 'code_points': 1, 'utf16_units': 2}
        self.native = [dict(self.rows[0], lengths=dict(value))]
        self.receipt = {'decision': 'PASS', 'result': {'runtime': {
            'finite_total': 1, 'finite_passed': 1, 'traces': [{
                'case_index': 0, 'deliveries': [{
                    'activity_id': ACTIVITY, 'input': '🙂', 'actual': dict(value),
                    'expected': dict(value), 'passed': True,
                    'actual_fields': [{'name': k, 'id': v, 'value': value[k]}
                                      for k, v in FIELDS.items()]}]}]}}}

    def test_unit_swaps_and_boolean_counts_are_rejected(self):
        self.assertEqual(len(compare(self.rows, self.native, self.receipt, 0)), 1)
        for changes in ({'code_points': 2, 'utf16_units': 1}, {'code_points': True}):
            with self.subTest(changes=changes):
                changed = deepcopy(self.native)
                changed[0]['lengths'].update(changes)
                with self.assertRaises(ValueError):
                    compare(self.rows, changed, self.receipt, 0)

    def test_typed_field_ids_and_values_are_checked(self):
        for key, value in [('id', 'urn:wrong:unit'), ('value', True), ('value', 99)]:
            changed = deepcopy(self.receipt)
            field = changed['result']['runtime']['traces'][0]['deliveries'][0]['actual_fields'][1]
            field[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                compare(self.rows, self.native, changed, 0)

    def test_complete_summary_cannot_hide_missing_or_wrong_input(self):
        for mutation in ('missing', 'boolean-index', 'wrong-text'):
            changed = deepcopy(self.receipt)
            traces = changed['result']['runtime']['traces']
            if mutation == 'missing':
                traces.clear()
            elif mutation == 'boolean-index':
                traces[0]['case_index'] = False
            else:
                traces[0]['deliveries'][0]['input'] = 'x'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                compare(self.rows, self.native, changed, 0)
        for native in ([], self.native * 2):
            with self.assertRaises(ValueError):
                compare(self.rows, native, self.receipt, 0)

    def test_corpus_boundaries_and_scope(self):
        rows = corpus()
        self.assertEqual(len(rows), 27)
        self.assertEqual(max(len(r['text'].encode()) for r in rows), 1024)
        self.assertEqual(python_lengths('e\u0301'),
                         {'utf8_bytes': 3, 'code_points': 2, 'utf16_units': 2})
        for text in ('a' * 1025, '\ud800'):
            with self.assertRaises(ValueError):
                python_lengths(text)


if __name__ == '__main__':
    unittest.main()
