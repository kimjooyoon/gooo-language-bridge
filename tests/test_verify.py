import unittest
from tools.verify import accepted, cases


class EvidenceGate(unittest.TestCase):
    def receipt(self, passed=120, total=120, decision='PASS'):
        return {'decision': decision, 'result': {'runtime': {
            'finite_passed': passed, 'finite_total': total}}}

    def test_scope_and_negative_counterexample(self):
        rows = cases()['cases']
        self.assertEqual(len(rows), 120)
        self.assertTrue(any(r['inputs'] == {'bridge/python:FloorDivide.input0': -7,
                                         'bridge/python:FloorDivide.input1': 3}
                            and r['expected']['bridge/python:FloorDivide'] == -3 for r in rows))

    def test_gate_rejects_partial_empty_and_forged_counts(self):
        self.assertTrue(accepted(self.receipt(), 0))
        for receipt in ({}, self.receipt(119), self.receipt(0, 0),
                        self.receipt(True), self.receipt(120, 120, 'PROGRESS'),
                        self.receipt('120')):
            self.assertFalse(accepted(receipt, 0))
        self.assertFalse(accepted(self.receipt(), 1))
