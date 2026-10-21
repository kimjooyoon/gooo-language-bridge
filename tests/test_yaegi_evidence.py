import json
import subprocess
import unittest
from tools.verify_yaegi import check_events


class RegressionEvidence(unittest.TestCase):
    def result(self, action, count, code):
        rows = [{'Action': action, 'Test': 'Regression/operator/case' + str(i)}
                for i in range(count)]
        return subprocess.CompletedProcess([], code, '\n'.join(map(json.dumps, rows)), '')

    def test_compile_failure_cannot_count_as_reproduced_bug(self):
        self.assertFalse(check_events(subprocess.CompletedProcess([], 1, '', 'compile failed'), 'fail', 8))
        self.assertTrue(check_events(self.result('fail', 8, 1), 'fail', 8))

    def test_fixed_evidence_requires_all_cases_and_success_exit(self):
        self.assertTrue(check_events(self.result('pass', 10, 0), 'pass', 10))
        for result in (self.result('pass', 9, 0), self.result('skip', 10, 0),
                       self.result('pass', 10, 1), self.result('fail', 10, 1)):
            self.assertFalse(check_events(result, 'pass', 10))
