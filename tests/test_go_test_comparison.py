"""Recorded Go outcomes must be complete before a difference is interpreted."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from tools.compare_go_tests import capture as read_capture, compare, domain, main, observations

PACKAGE = 'example.test/flags'
CASES = json.dumps([{'id': 'case', 'package': PACKAGE, 'test': 'TestContract'}]).encode()


def event(action, test=None, **extra):
    value = dict(Action=action, Package=PACKAGE, **extra)
    if test is not None:
        value['Test'] = test
    return value


def raw(events):
    return ('\n'.join(json.dumps(x) for x in events) + '\n').encode()


def capture(status, test='TestContract'):
    return raw([event('start'), event('run', test), event(status, test),
                event('fail' if status == 'fail' else 'pass')])


class ComparisonTests(unittest.TestCase):
    def test_all_four_transitions_are_distinct_and_comparison_is_not_approval(self):
        for base, head, group in [('pass', 'pass', 'passed_both'),
                                   ('pass', 'fail', 'introduced_failures'),
                                   ('fail', 'pass', 'resolved_failures'),
                                   ('fail', 'fail', 'failed_both')]:
            with self.subTest(base=base, head=head):
                result = compare(CASES, capture(base), capture(head))
                self.assertEqual(result[group], ['case'])
                self.assertEqual(sum(len(result[k]) for k in (
                    'passed_both', 'introduced_failures', 'resolved_failures', 'failed_both')), 1)
                self.assertFalse(result['patch_approved'])
                self.assertFalse(result['source_revision_authenticated'])
                self.assertFalse(result['go_runtime_observed'])
                self.assertFalse(result['failure_causes_compared'])

    def test_mixed_failures_in_both_runs_do_not_hide_an_introduced_failure(self):
        cases = json.dumps([{'id': x, 'package': PACKAGE, 'test': x}
                            for x in ['TestOldFailure', 'TestNewFailure']]).encode()
        def run(a, b):
            return raw([event('start'), event('run', 'TestOldFailure'),
                        event(a, 'TestOldFailure'), event('run', 'TestNewFailure'),
                        event(b, 'TestNewFailure'), event('fail')])
        result = compare(cases, run('fail', 'pass'), run('pass', 'fail'))
        self.assertEqual(result['resolved_failures'], ['TestOldFailure'])
        self.assertEqual(result['introduced_failures'], ['TestNewFailure'])

    def test_identity_includes_package_and_labels_cannot_duplicate_one_case(self):
        for rows in [[], [{'id': 'a', 'package': PACKAGE, 'test': 'T'}] * 2,
                     [{'id': x, 'package': PACKAGE, 'test': 'T'} for x in ['a', 'b']],
                     [{'id': 'a', 'package': PACKAGE, 'test': 'T', 'expected': 'pass'}],
                     [{'id': 'a', 'package': PACKAGE, 'test': '\ud800'}]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                domain(json.dumps(rows).encode())
        cases = json.dumps([{'id': 'one', 'package': PACKAGE, 'test': 'T'},
                            {'id': 'two', 'package': 'another/pkg', 'test': 'T'}]).encode()
        self.assertEqual(len(domain(cases)), 2)

    def test_missing_skipped_or_parent_case_is_not_a_semantic_result(self):
        parent = raw([event('start'), event('run', 'TestContract'),
                      event('run', 'TestContract/child'), event('pass', 'TestContract/child'),
                      event('pass', 'TestContract'), event('pass')])
        for log in [capture('pass', 'DifferentTest'), capture('skip'), parent,
                    raw([event('start'), event('pass')])]:
            with self.subTest(log=log), self.assertRaises(ValueError):
                observations(log, domain(CASES))

    def test_truncation_duplicate_runs_and_build_failures_are_rejected(self):
        good = [event('start'), event('run', 'TestContract'),
                event('pass', 'TestContract'), event('pass')]
        bad = [good[:-1], good[:2] + [event('fail')], good + good,
               good[:2] + [event('pass', 'TestContract')] * 2 + [event('pass')],
               [event('start'), event('fail', FailedBuild=PACKAGE)],
               [{'Action': 'build-fail', 'ImportPath': PACKAGE}],
               good[:2] + [event('pass')],
               good[:-1] + [event('fail')],
               good[:-1] + [event('skip')],
               good[:2] + [event('pause', 'TestContract'),
                           event('pass', 'TestContract'), event('pass')]]
        for rows in bad:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                observations(raw(rows), domain(CASES))

    def test_parallel_pause_continue_and_build_diagnostics_are_preserved(self):
        log = raw([{'Action': 'build-output', 'ImportPath': PACKAGE, 'Output': 'warning'},
                   event('start'), event('run', 'TestContract'), event('pause', 'TestContract'),
                   event('cont', 'TestContract'), event('output', 'TestContract', Output='ok'),
                   event('pass', 'TestContract'), event('pass')])
        self.assertEqual(observations(log, domain(CASES))[0]['case']['result'], 'pass')

    def test_unselected_leaf_failure_is_visible_but_parent_rollups_are_not_extra_cases(self):
        log = raw([event('start'), event('run', 'TestContract'),
                   event('fail', 'TestContract'), event('run', 'TestOther'),
                   event('run', 'TestOther/child'), event('fail', 'TestOther/child'),
                   event('fail', 'TestOther'), event('fail')])
        context = observations(log, domain(CASES))[1]
        self.assertEqual(context['unselected_failures'],
                         [{'package': PACKAGE, 'test': 'TestOther/child'}])
        self.assertEqual(context['parent_failures'],
                         [{'package': PACKAGE, 'test': 'TestOther'}])

    def test_parent_failure_after_a_passing_child_is_retained(self):
        cases = json.dumps([{'id': 'child', 'package': PACKAGE,
                             'test': 'TestContract/child'}]).encode()
        log = raw([event('start'), event('run', 'TestContract'),
                   event('run', 'TestContract/child'), event('pass', 'TestContract/child'),
                   event('fail', 'TestContract'), event('fail')])
        observed, context = observations(log, domain(cases))
        self.assertEqual(observed['child']['result'], 'pass')
        self.assertEqual(context['packages'][PACKAGE], 'fail')
        self.assertEqual(context['parent_failures'],
                         [{'package': PACKAGE, 'test': 'TestContract'}])

    def test_bad_json_and_unknown_actions_cannot_silently_disappear(self):
        for log in [b'\xff', b'{}\n', b'\n', b'{"Action":"run","Action":"pass"}\n',
                    b'{"Action":NaN}\n', raw([event('start'), event('mystery')])]:
            with self.subTest(log=log), self.assertRaises(ValueError):
                observations(log, domain(CASES))

    def test_limits_and_package_identity_are_enforced(self):
        with patch('tools.compare_go_tests.LIMIT', 8):
            for run in [lambda: domain(CASES),
                        lambda: observations(capture('pass'), {'case': (PACKAGE, 'T')})]:
                with self.assertRaises(ValueError):
                    run()
        other = capture('pass').replace(PACKAGE.encode(), b'different/package')
        with self.assertRaises(ValueError):
            observations(other, domain(CASES))

    def test_parent_detection_is_not_fooled_by_an_adjacent_sibling_name(self):
        log = raw([event('start'), event('run', 'TestContract'),
                   event('run', 'TestContract/child'), event('pass', 'TestContract/child'),
                   event('pass', 'TestContract'), event('run', 'TestContract!'),
                   event('pass', 'TestContract!'), event('pass')])
        with self.assertRaisesRegex(ValueError, 'parent'):
            observations(log, domain(CASES))


class CLITests(unittest.TestCase):
    def test_documented_script_entrypoint_returns_a_complete_failing_comparison(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run([
                sys.executable, str(repo / 'tools/compare_go_tests.py'),
                '--cases', str(repo / 'examples/go-test-comparison/cases.json'),
                '--base', str(repo / 'examples/go-test-comparison/base.jsonl'),
                '--head', str(repo / 'examples/go-test-comparison/head.jsonl'),
                '--out', str(Path(temp) / 'comparison')],
                cwd=temp, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['decision'], 'RECORDED_OUTCOMES_COMPARED')
            self.assertEqual(report['introduced_failures'], ['new-failure'])

    @unittest.skipUnless(hasattr(os, 'mkfifo') and hasattr(os, 'O_NONBLOCK'), 'POSIX pipes')
    def test_named_pipe_input_is_rejected_without_waiting_for_a_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            fifo = Path(temp) / 'capture'
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, 'regular file'):
                read_capture(fifo)

    def test_input_read_stops_at_the_byte_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'capture'
            path.write_bytes(b'x' * 20)
            with self.assertRaises(ValueError):
                read_capture(path, limit=8)

    def test_checked_in_example_is_explicitly_a_four_transition_protocol_fixture(self):
        example = Path(__file__).resolve().parents[1] / 'examples/go-test-comparison'
        result = compare((example / 'cases.json').read_bytes(),
                         (example / 'base.jsonl').read_bytes(),
                         (example / 'head.jsonl').read_bytes())
        self.assertEqual(result['introduced_failures'], ['new-failure'])
        self.assertEqual(result['resolved_failures'], ['resolved'])
        self.assertEqual(result['failed_both'], ['still-failing'])
        self.assertEqual(result['passed_both'], ['control'])

    def test_complete_comparison_copies_inputs_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, content in [('cases', CASES), ('base', capture('pass')),
                                  ('head', capture('fail'))]:
                (root / name).write_bytes(content)
            args = [item for name in ['cases', 'base', 'head']
                    for item in ['--' + name, str(root / name)]] + ['--out', str(root / 'out')]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 1)
            before = (root / 'out/report.json').read_bytes()
            report = json.loads(before)
            self.assertEqual(report['introduced_failures'], ['case'])
            self.assertEqual((root / 'out/base.original').read_bytes(), capture('pass'))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
            self.assertEqual((root / 'out/report.json').read_bytes(), before)

    def test_clean_head_returns_zero_without_claiming_patch_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, content in [('cases', CASES), ('base', capture('fail')),
                                  ('head', capture('pass'))]:
                (root / name).write_bytes(content)
            args = [item for name in ['cases', 'base', 'head']
                    for item in ['--' + name, str(root / name)]] + ['--out', str(root / 'out')]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
            report = json.loads((root / 'out/report.json').read_text())
            self.assertEqual(report['resolved_failures'], ['case'])
            self.assertFalse(report['patch_approved'])

    def test_invalid_capture_retains_failure_and_original_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, content in [('cases', CASES), ('base', b'broken'),
                                  ('head', capture('pass'))]:
                (root / name).write_bytes(content)
            args = [item for name in ['cases', 'base', 'head']
                    for item in ['--' + name, str(root / name)]] + ['--out', str(root / 'out')]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 2)
            report = json.loads((root / 'out/report.json').read_text())
            self.assertEqual(report['decision'], 'INVALID_CAPTURE')
            self.assertEqual((root / 'out/base.original').read_bytes(), b'broken')


if __name__ == '__main__':
    unittest.main()
