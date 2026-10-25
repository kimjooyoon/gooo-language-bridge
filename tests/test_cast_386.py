"""Captured 386 evidence must be complete even when the observed base fails."""
import copy
import json
import unittest

from tools.verify_cast_386 import parse_capture


PACKAGE = 'github.com/spf13/cast'
RUNTIME_TEST = 'TestBridge386Runtime'
BOUNDS_TEST = 'TestBridge386Bounds'
BOUNDS = (
    'int/min', 'int/max', 'int/overflow', 'int/underflow',
    'uint/max', 'uint/overflow', 'int64/min', 'int64/max', 'uint64/max',
)
PARENTS = ('TestNumber', RUNTIME_TEST, BOUNDS_TEST)
RUNTIME = {'go_version': 'go1.27.3', 'os': 'linux', 'arch': '386', 'int_bits': 32}
MARKER = 'CAST386_RUNTIME '


def event(action, test=None, **fields):
    row = {'Action': action, 'Package': PACKAGE}
    if test is not None:
        row['Test'] = test
    row.update(fields)
    return row


def encoded(rows):
    return ''.join(json.dumps(row) + '\n' for row in rows)


def capture(number='pass', failing_bound=None):
    """Include intermediate subtest events, as a real nested Go run does."""
    rows = [event('start'), event('run', 'TestNumber'), event(number, 'TestNumber'),
            event('run', RUNTIME_TEST),
            event('output', RUNTIME_TEST,
                  Output=MARKER + json.dumps(RUNTIME) + '\n'),
            event('pass', RUNTIME_TEST), event('run', BOUNDS_TEST)]
    for group in ('int', 'uint', 'int64', 'uint64'):
        group_test = BOUNDS_TEST + '/' + group
        rows.append(event('run', group_test))
        for name in BOUNDS:
            if name.split('/')[0] == group:
                test = BOUNDS_TEST + '/' + name
                rows += [event('run', test),
                         event('fail' if name == failing_bound else 'pass', test)]
        group_failed = failing_bound is not None and failing_bound.startswith(group + '/')
        rows.append(event('fail' if group_failed else 'pass', group_test))
    failed = number == 'fail' or failing_bound is not None
    rows += [event('fail' if failing_bound else 'pass', BOUNDS_TEST),
             event('fail' if failed else 'pass')]
    return rows, int(failed)


class Cast386CaptureTests(unittest.TestCase):
    def parse(self, rows, code=0):
        return parse_capture(encoded(rows), code)

    def reject(self, rows, code=0):
        with self.assertRaises(ValueError):
            self.parse(rows, code)

    def witness(self, rows):
        return next(row for row in rows if row.get('Output', '').startswith(MARKER))

    def set_runtime(self, rows, payload):
        self.witness(rows)['Output'] = MARKER + json.dumps(payload) + '\n'

    def bounds(self, report):
        # The contract identifies leaves relative to TestBridge386Bounds.
        # Accept either that representation or fully qualified Go test names.
        return {name.removeprefix(BOUNDS_TEST + '/'): value
                for name, value in report['bounds'].items()}

    def test_complete_passing_capture_has_exact_identity_and_required_results(self):
        rows, code = capture()
        report = self.parse(rows, code)
        self.assertEqual(set(report), {'runtime', 'tests', 'bounds', 'go_exit_code',
                                       'skipped_events'})
        self.assertEqual(report['runtime'], RUNTIME)
        self.assertIs(type(report['runtime']['int_bits']), int)
        self.assertEqual(report['tests'], dict.fromkeys(PARENTS, 'pass'))
        self.assertEqual(self.bounds(report), dict.fromkeys(BOUNDS, 'pass'))
        self.assertEqual(report['go_exit_code'], 0)
        self.assertIs(type(report['go_exit_code']), int)
        self.assertEqual(report['skipped_events'], 0)

    def test_complete_base_failures_remain_valid_observations(self):
        for number, bound in [('fail', None), ('pass', 'int/overflow'),
                              ('fail', 'uint/overflow')]:
            with self.subTest(number=number, bound=bound):
                rows, code = capture(number, bound)
                report = self.parse(rows, code)
                self.assertEqual(report['tests'], {
                    'TestNumber': number, RUNTIME_TEST: 'pass',
                    BOUNDS_TEST: 'fail' if bound else 'pass',
                })
                expected = dict.fromkeys(BOUNDS, 'pass')
                if bound is not None:
                    expected[bound] = 'fail'
                self.assertEqual(self.bounds(report), expected)
                self.assertEqual(report['go_exit_code'], 1)

    def test_unrelated_build_events_and_ordinary_output_are_not_runtime_witnesses(self):
        rows, code = capture()
        rows[:0] = [
            {'Action': 'build-start', 'ImportPath': 'example.invalid/build'},
            {'Action': 'build-output', 'ImportPath': 'example.invalid/build',
             'Output': 'compiler diagnostic\n'},
            {'Action': 'build-pass', 'ImportPath': 'example.invalid/build'},
        ]
        rows.insert(1, event('output', 'TestNumber', Output='ordinary test output\n'))
        report = self.parse(rows, code)
        self.assertEqual(report['runtime'], RUNTIME)
        self.assertEqual(self.bounds(report), dict.fromkeys(BOUNDS, 'pass'))

    def test_skips_outside_required_tests_are_counted(self):
        rows, code = capture()
        rows.insert(-1, event('skip', 'TestOptionalUnrelated'))
        report = self.parse(rows, code)
        self.assertEqual(report['skipped_events'], 1)
        self.assertIs(type(report['skipped_events']), int)

    def test_missing_and_duplicate_runtime_witnesses_are_refused(self):
        rows, _ = capture()
        marker = self.witness(rows)
        self.reject([row for row in rows if row is not marker])
        rows.insert(-1, copy.deepcopy(marker))
        self.reject(rows)

    def test_marker_requires_output_action_exact_package_and_runtime_test(self):
        for field, value in [('Action', 'run'), ('Package', 'example.invalid/cast'),
                             ('Test', 'TestNumber'), ('Test', None)]:
            with self.subTest(field=field, value=value):
                rows, _ = capture()
                witness = self.witness(rows)
                if value is None:
                    witness.pop(field)
                else:
                    witness[field] = value
                self.reject(rows)

    def test_runtime_identity_and_integer_width_are_exact(self):
        changes = [('go_version', 'go1.26.9'), ('os', 'darwin'),
                   ('arch', 'amd64'), ('int_bits', 64), ('int_bits', '32'),
                   ('int_bits', 32.0), ('int_bits', True)]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                rows, _ = capture()
                payload = dict(RUNTIME, **{field: value})
                self.set_runtime(rows, payload)
                self.reject(rows)

    def test_runtime_payload_has_exact_fields_and_is_a_json_object(self):
        missing = dict(RUNTIME)
        missing.pop('arch')
        payloads = [missing, dict(RUNTIME, host_arch='amd64'), [], None, '386']
        for payload in payloads:
            with self.subTest(payload=payload):
                rows, _ = capture()
                self.set_runtime(rows, payload)
                self.reject(rows)
        rows, _ = capture()
        self.witness(rows)['Output'] = MARKER + '{broken JSON}\n'
        self.reject(rows)

    def test_runtime_must_finish_successfully(self):
        for terminal in (None, 'skip', 'fail'):
            with self.subTest(terminal=terminal):
                rows, _ = capture()
                result = next(row for row in rows
                              if row.get('Test') == RUNTIME_TEST and row['Action'] == 'pass')
                if terminal is None:
                    rows.remove(result)
                else:
                    result['Action'] = terminal
                code = 1 if terminal == 'fail' else 0
                if code:
                    rows[-1]['Action'] = 'fail'
                self.reject(rows, code)

    def test_every_required_parent_needs_a_pass_or_fail_terminal(self):
        for test in PARENTS:
            for terminal in (None, 'skip'):
                with self.subTest(test=test, terminal=terminal):
                    rows, _ = capture()
                    result = next(row for row in rows
                                  if row.get('Test') == test and row['Action'] == 'pass')
                    if terminal is None:
                        rows.remove(result)
                    else:
                        result['Action'] = terminal
                    self.reject(rows)

    def test_all_nine_bounds_need_their_own_terminal_result(self):
        for name in BOUNDS:
            for terminal in (None, 'skip'):
                with self.subTest(bound=name, terminal=terminal):
                    rows, _ = capture()
                    test = BOUNDS_TEST + '/' + name
                    result = next(row for row in rows
                                  if row.get('Test') == test and row['Action'] == 'pass')
                    if terminal is None:
                        rows.remove(result)
                    else:
                        result['Action'] = terminal
                    self.reject(rows)

    def test_unrecognized_bounds_cannot_replace_the_required_leaf_set(self):
        rows, _ = capture()
        rows.insert(-2, event('pass', BOUNDS_TEST + '/int/not-a-boundary'))
        self.reject(rows)

    def test_other_package_results_cannot_supply_missing_target_evidence(self):
        rows, _ = capture()
        for row in rows:
            row['Package'] = 'example.invalid/cast'
        self.reject(rows)
        rows, _ = capture()
        for row in rows:
            if row.get('Test') == 'TestNumber':
                row['Package'] = 'example.invalid/cast'
        self.reject(rows)

    def test_package_terminal_is_required_and_must_match_exit_code(self):
        rows, _ = capture()
        self.reject(rows[:-1])
        rows[-1]['Action'] = 'skip'
        self.reject(rows)
        rows, _ = capture()
        self.reject(rows, 1)
        rows[-1]['Action'] = 'fail'
        self.reject(rows, 0)

    def test_only_go_exit_zero_or_one_are_allowed(self):
        rows, _ = capture()
        for code in (-1, 2, 124, '0', 0.0, True):
            with self.subTest(code=code):
                self.reject(rows, code)

    def test_each_raw_line_must_be_a_valid_json_object(self):
        rows, code = capture()
        text = encoded(rows)
        for bad_line in ('not JSON', '{', '[]', 'null', '0', '"text"', ''):
            with self.subTest(line=bad_line):
                with self.assertRaises(ValueError):
                    parse_capture(text + bad_line + '\n', code)
        with self.assertRaises(ValueError):
            parse_capture('', 0)


if __name__ == '__main__':
    unittest.main()
