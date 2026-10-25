"""Reuse requires identical bound bytes and a completed, intact inspection."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools import check_saved_followup as followup


ROLES = ('head', 'feedback', 'checks', 'implementation', 'policy', 'schemas',
         'invocation', 'scope')
FILE_ROLES = tuple(role for role in ROLES if role != 'invocation')


class SavedFollowupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sequence = 0

    def bundle(self):
        self.sequence += 1
        directory = self.root / ('bundle-%d' % self.sequence)
        directory.mkdir()
        (directory / 'capture').mkdir()
        components = {}
        for role in FILE_ROLES:
            name = 'capture/' + role + '.txt'
            (directory / name).write_bytes((role + ': original\n').encode())
            components[role] = {'coverage': 'complete', 'files': [name]}
        components['invocation'] = {
            'coverage': 'complete',
            'argv': ['inspect', '--source', 'capture/implementation.txt'],
            'selection': 'one supplied source and its saved feedback/check context',
        }
        value = {'schema': 'gooo/saved-followup-snapshot/v1',
                 'subject': 'example/tool#12', 'components': components}
        self.write_snapshot(directory, value)
        return directory

    def read_snapshot(self, directory):
        return json.loads((directory / 'snapshot.json').read_bytes())

    def write_snapshot(self, directory, value):
        (directory / 'snapshot.json').write_bytes(
            (json.dumps(value, sort_keys=True, ensure_ascii=False) + '\n').encode())

    def completed(self, directory):
        bound = followup.snapshot(directory)
        result = b'Private inspection result; no publication or acceptance claim.\n'
        (directory / 'result.txt').write_bytes(result)
        receipt = {'schema': 'gooo/saved-followup-inspection/v1',
                   'status': 'completed', 'exit_code': 0,
                   'snapshot_sha256': bound['snapshot_sha256'],
                   'evaluation_sha256': bound['evaluation_sha256'],
                   'result': {'path': 'result.txt', 'sha256': followup.digest(result)}}
        self.write_receipt(directory, receipt)
        return receipt

    def write_receipt(self, directory, receipt):
        (directory / 'inspection.json').write_bytes(
            (json.dumps(receipt, sort_keys=True) + '\n').encode())

    def pair(self):
        previous, current = self.bundle(), self.bundle()
        self.completed(previous)
        return current, previous

    def assert_inspect(self, current, previous=None):
        report = followup.check(current, previous)
        self.assertEqual(report['decision'], 'INSPECT')
        self.assertEqual(report['effect'], 'none')
        self.assertIsInstance(report['reason'], str)
        self.assertTrue(report['reason'])
        return report

    def assert_current_refused(self, directory):
        with self.assertRaises((ValueError, OSError)):
            followup.snapshot(directory)
        with self.assertRaises((ValueError, OSError)):
            followup.check(directory)

    def test_identical_complete_bound_snapshot_retains_completed_result(self):
        current, previous = self.pair()
        current_bound = followup.snapshot(current)
        prior_bound = followup.snapshot(previous)
        self.assertEqual(current_bound['subject'], 'example/tool#12')
        self.assertEqual(set(current_bound['component_sha256']), set(ROLES))
        self.assertEqual(current_bound['incomplete_components'], [])
        self.assertEqual(current_bound, prior_bound)
        report = followup.check(current, previous)
        self.assertEqual(report['decision'], 'RETAIN_UNCHANGED')
        self.assertEqual(report['changed_components'], [])
        self.assertEqual(report['incomplete_components'], [])
        self.assertEqual(report['effect'], 'none')
        self.assertIn('current_binding', report)
        self.assertIn('prior_binding', report)

    def test_no_previous_inspection_requires_inspection(self):
        self.assert_inspect(self.bundle())

    def test_each_component_change_requires_inspection(self):
        for role in ROLES:
            with self.subTest(role=role):
                current, previous = self.pair()
                if role == 'invocation':
                    value = self.read_snapshot(current)
                    value['components'][role]['argv'].append('--include-new-feedback')
                    self.write_snapshot(current, value)
                else:
                    (current / ('capture/' + role + '.txt')).write_bytes(
                        (role + ': changed\n').encode())
                report = self.assert_inspect(current, previous)
                self.assertIn(role, report['changed_components'])

    def test_feedback_from_any_peer_role_is_new_information(self):
        for role in ('maintainer', 'collaborator', 'contributor', 'unknown'):
            with self.subTest(role=role):
                current, previous = self.pair()
                self.assertEqual((current / 'capture/implementation.txt').read_bytes(),
                                 (previous / 'capture/implementation.txt').read_bytes())
                (current / 'capture/feedback.txt').write_bytes(
                    ('author_role=' + role + '\nPlease inspect this saved finding.\n').encode())
                self.assertIn('feedback', self.assert_inspect(current, previous)['changed_components'])

    def test_subject_argument_selection_and_scope_changes_are_not_reused(self):
        for change in ('subject', 'argv', 'selection', 'scope'):
            with self.subTest(change=change):
                current, previous = self.pair()
                value = self.read_snapshot(current)
                if change == 'subject':
                    value['subject'] = 'example/other#12'
                elif change == 'scope':
                    (current / 'capture/scope.txt').write_bytes(b'new supplied scope\n')
                else:
                    value['components']['invocation'][change] = (
                        ['inspect', '--different-source'] if change == 'argv' else 'another selection')
                self.write_snapshot(current, value)
                self.assert_inspect(current, previous)

    def test_snapshot_binds_raw_manifest_bytes_and_file_bytes(self):
        directory = self.bundle()
        original = followup.snapshot(directory)
        value = self.read_snapshot(directory)
        (directory / 'snapshot.json').write_text(json.dumps(value, indent=2) + '\n')
        reformatted = followup.snapshot(directory)
        self.assertNotEqual(original['snapshot_sha256'], reformatted['snapshot_sha256'])
        self.assertEqual(original['evaluation_sha256'], reformatted['evaluation_sha256'])
        (directory / 'capture/implementation.txt').write_bytes(b'changed implementation\n')
        changed = followup.snapshot(directory)
        self.assertNotEqual(reformatted['snapshot_sha256'], changed['snapshot_sha256'])
        self.assertNotEqual(reformatted['evaluation_sha256'], changed['evaluation_sha256'])

    def test_evaluation_binding_excludes_only_head_feedback_and_checks(self):
        for role in ROLES:
            with self.subTest(role=role):
                directory = self.bundle()
                before = followup.snapshot(directory)
                if role == 'invocation':
                    value = self.read_snapshot(directory)
                    value['components'][role]['selection'] += '; changed'
                    self.write_snapshot(directory, value)
                else:
                    (directory / ('capture/' + role + '.txt')).write_bytes(b'changed bytes\n')
                after = followup.snapshot(directory)
                self.assertNotEqual(before['snapshot_sha256'], after['snapshot_sha256'])
                if role in ('head', 'feedback', 'checks'):
                    self.assertEqual(before['evaluation_sha256'], after['evaluation_sha256'])
                else:
                    self.assertNotEqual(before['evaluation_sha256'], after['evaluation_sha256'])

    def test_current_or_prior_incomplete_component_requires_inspection(self):
        for side in ('current', 'previous'):
            for coverage in ('partial', 'unknown', 'missing'):
                for role in ROLES:
                    with self.subTest(side=side, coverage=coverage, role=role):
                        current, previous = self.pair()
                        target = current if side == 'current' else previous
                        value = self.read_snapshot(target)
                        value['components'][role]['coverage'] = coverage
                        self.write_snapshot(target, value)
                        if side == 'previous':
                            self.completed(previous)
                        self.assert_inspect(current, previous)

    def test_raw_unknown_text_is_opaque_and_cannot_supply_coverage(self):
        current, previous = self.pair()
        for directory in (current, previous):
            (directory / 'capture/feedback.txt').write_bytes(b'UNKNOWN\n')
        self.completed(previous)
        self.assertEqual(followup.check(current, previous)['decision'], 'RETAIN_UNCHANGED')
        for directory in (current, previous):
            value = self.read_snapshot(directory)
            value['components']['feedback']['coverage'] = 'unknown'
            self.write_snapshot(directory, value)
        self.completed(previous)
        self.assert_inspect(current, previous)

    def test_completed_receipt_must_have_zero_integer_exit_and_completed_status(self):
        for field, values in (('status', ['running', 'failed', 'partial', 'unknown']),
                              ('exit_code', [1, -1, True, False, '0', None])):
            for value in values:
                with self.subTest(field=field, value=value):
                    current, previous = self.pair()
                    receipt = json.loads((previous / 'inspection.json').read_bytes())
                    receipt[field] = value
                    self.write_receipt(previous, receipt)
                    self.assert_inspect(current, previous)

    def test_missing_empty_changed_or_misbound_prior_result_is_not_reused(self):
        for mutation in ('missing_receipt', 'missing_result', 'empty_result', 'changed_result',
                         'snapshot_binding', 'evaluation_binding', 'result_binding', 'result_is_input'):
            with self.subTest(mutation=mutation):
                current, previous = self.pair()
                receipt = json.loads((previous / 'inspection.json').read_bytes())
                if mutation == 'missing_receipt':
                    (previous / 'inspection.json').unlink()
                elif mutation == 'missing_result':
                    (previous / 'result.txt').unlink()
                elif mutation == 'empty_result':
                    (previous / 'result.txt').write_bytes(b'')
                elif mutation == 'changed_result':
                    (previous / 'result.txt').write_bytes(b'substituted\n')
                else:
                    if mutation == 'result_is_input':
                        receipt['result'] = {'path': 'capture/head.txt',
                                             'sha256': followup.digest((previous / 'capture/head.txt').read_bytes())}
                    elif mutation == 'result_binding':
                        receipt['result']['sha256'] = 'sha256:' + '0' * 64
                    else:
                        receipt[mutation.replace('_binding', '_sha256')] = 'sha256:' + '0' * 64
                    self.write_receipt(previous, receipt)
                self.assert_inspect(current, previous)

    def test_invalid_prior_receipt_is_inspected_not_a_current_input_error(self):
        for mutation in ('schema', 'extra', 'missing', 'duplicate', 'nonfinite', 'bad_path'):
            with self.subTest(mutation=mutation):
                current, previous = self.pair()
                receipt = json.loads((previous / 'inspection.json').read_bytes())
                if mutation == 'schema':
                    receipt['schema'] = 'other/v1'
                elif mutation == 'extra':
                    receipt['approval'] = True
                elif mutation == 'missing':
                    del receipt['result']
                elif mutation == 'bad_path':
                    receipt['result']['path'] = '../result.txt'
                if mutation == 'duplicate':
                    raw = json.dumps(receipt)
                    (previous / 'inspection.json').write_text(raw[:-1] + ', "exit_code": 0}\n')
                elif mutation == 'nonfinite':
                    receipt['exit_code'] = float('nan')
                    self.write_receipt(previous, receipt)
                else:
                    self.write_receipt(previous, receipt)
                self.assert_inspect(current, previous)

    def test_invalid_previous_snapshot_is_not_reused(self):
        for mutation in ('missing', 'schema', 'bad_json', 'duplicate_path'):
            with self.subTest(mutation=mutation):
                current, previous = self.pair()
                value = self.read_snapshot(previous)
                if mutation == 'missing':
                    (previous / 'snapshot.json').unlink()
                elif mutation == 'bad_json':
                    (previous / 'snapshot.json').write_bytes(b'{')
                else:
                    if mutation == 'schema':
                        value['schema'] = 'other/v1'
                    else:
                        value['components']['policy']['files'] = ['capture/head.txt']
                    self.write_snapshot(previous, value)
                self.assert_inspect(current, previous)

    def test_strict_current_manifest_fields_types_and_invocation(self):
        mutations = [
            lambda v: v.update(schema='other/v1'),
            lambda v: v.update(extra=True),
            lambda v: v.update(subject=''),
            lambda v: v.update(subject=12),
            lambda v: v.update(components=[]),
            lambda v: v['components'].pop('head'),
            lambda v: v['components'].update(extra={'coverage': 'complete', 'files': []}),
            lambda v: v['components']['head'].update(extra=True),
            lambda v: v['components']['head'].update(coverage=True),
            lambda v: v['components']['head'].update(files='capture/head.txt'),
            lambda v: v['components']['head'].update(files=[]),
            lambda v: v['components']['head'].update(files=[1]),
            lambda v: v['components']['invocation'].update(extra=True),
            lambda v: v['components']['invocation'].update(argv=[]),
            lambda v: v['components']['invocation'].update(argv='inspect'),
            lambda v: v['components']['invocation'].update(argv=['inspect', 1]),
            lambda v: v['components']['invocation'].update(selection=''),
            lambda v: v['components']['invocation'].update(selection=None),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                directory = self.bundle()
                value = self.read_snapshot(directory)
                mutate(value)
                self.write_snapshot(directory, value)
                self.assert_current_refused(directory)

    def test_duplicate_keys_and_nonfinite_json_are_refused(self):
        for mutation in ('top_duplicate', 'nested_duplicate', 'nan', 'infinity'):
            with self.subTest(mutation=mutation):
                directory = self.bundle()
                raw = (directory / 'snapshot.json').read_text()
                if mutation == 'top_duplicate':
                    raw = raw.rstrip()[:-1] + ', "subject": "another"}\n'
                elif mutation == 'nested_duplicate':
                    raw = raw.replace('"coverage": "complete"',
                                      '"coverage": "complete", "coverage": "complete"', 1)
                else:
                    value = self.read_snapshot(directory)
                    value['subject'] = float('nan') if mutation == 'nan' else float('inf')
                    raw = json.dumps(value)
                (directory / 'snapshot.json').write_text(raw)
                self.assert_current_refused(directory)

    def test_unsafe_missing_and_duplicate_paths_are_refused(self):
        for path in ('../outside.txt', '/absolute.txt', 'capture\\head.txt',
                     'capture/../head.txt', 'capture//head.txt', './capture/head.txt',
                     'capture/missing.txt', 'snapshot.json', 'inspection.json'):
            with self.subTest(path=path):
                directory = self.bundle()
                value = self.read_snapshot(directory)
                value['components']['head']['files'] = [path]
                self.write_snapshot(directory, value)
                self.assert_current_refused(directory)
        for cross_role in (False, True):
            with self.subTest(cross_role=cross_role):
                directory = self.bundle()
                value = self.read_snapshot(directory)
                if cross_role:
                    value['components']['policy']['files'] = ['capture/head.txt']
                else:
                    value['components']['head']['files'].append('capture/head.txt')
                self.write_snapshot(directory, value)
                self.assert_current_refused(directory)

    def test_file_parent_directory_and_bundle_symlinks_are_refused(self):
        directory = self.bundle()
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'outside\n')
        (directory / 'capture/head.txt').unlink()
        (directory / 'capture/head.txt').symlink_to(outside)
        self.assert_current_refused(directory)

        directory = self.bundle()
        outside_directory = self.root / 'outside-directory'
        outside_directory.mkdir()
        (outside_directory / 'head.txt').write_bytes(b'outside\n')
        (directory / 'linked').symlink_to(outside_directory, target_is_directory=True)
        value = self.read_snapshot(directory)
        value['components']['head']['files'] = ['linked/head.txt']
        self.write_snapshot(directory, value)
        self.assert_current_refused(directory)

        directory = self.bundle()
        alias = self.root / 'linked-bundle'
        alias.symlink_to(directory, target_is_directory=True)
        self.assert_current_refused(alias)

    def test_file_count_per_file_and_total_byte_limits_are_refused(self):
        directory = self.bundle()
        (directory / 'capture/head.txt').write_bytes(b'x' * (128 * 1024 + 1))
        self.assert_current_refused(directory)

        directory = self.bundle()
        value = self.read_snapshot(directory)
        names = []
        for index in range(65):
            name = 'capture/extra-%d.txt' % index
            (directory / name).write_bytes(b'x')
            names.append(name)
        value['components']['head']['files'] = names
        self.write_snapshot(directory, value)
        self.assert_current_refused(directory)

        directory = self.bundle()
        value = self.read_snapshot(directory)
        names = []
        for index in range(9):
            name = 'capture/large-%d.txt' % index
            (directory / name).write_bytes(b'x' * (120 * 1024))
            names.append(name)
        value['components']['head']['files'] = names
        self.write_snapshot(directory, value)
        self.assert_current_refused(directory)

    def test_cli_reports_to_stdout_without_creating_a_cache(self):
        current, previous = self.pair()
        before = {p.relative_to(self.root): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = followup.main(['--current', str(current), '--previous', str(previous)])
        report = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report['decision'], 'RETAIN_UNCHANGED')
        self.assertEqual(report['effect'], 'none')
        self.assertEqual({p.relative_to(self.root): p.read_bytes()
                          for p in self.root.rglob('*') if p.is_file()}, before)

    def test_cli_writes_only_explicit_report_output(self):
        current, previous = self.pair()
        before = {p.relative_to(self.root): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        output = self.root / 'explicit-report.json'
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = followup.main(['--current', str(current), '--previous', str(previous),
                                 '--output', str(output)])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(json.loads(output.read_bytes())['decision'], 'RETAIN_UNCHANGED')
        after = {p.relative_to(self.root): p.read_bytes()
                 for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(set(after) - set(before), {Path('explicit-report.json')})
        for path, data in before.items():
            self.assertEqual(after[path], data)

    def test_output_cannot_replace_bundle_evidence_or_follow_a_symlink(self):
        current, previous = self.pair()
        for bundle in (current, previous):
            path = bundle / 'snapshot.json'
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                followup.main(['--current', str(current), '--previous', str(previous),
                               '--output', str(path)])
            self.assertEqual(path.read_bytes(), original)
        outside = self.root / 'existing.txt'
        outside.write_bytes(b'preserve\n')
        link = self.root / 'report-link.json'
        link.symlink_to(outside)
        with self.assertRaises(OSError):
            followup.main(['--current', str(current), '--previous', str(previous),
                           '--output', str(link)])
        self.assertEqual(outside.read_bytes(), b'preserve\n')

    def test_existing_or_hardlinked_output_is_not_overwritten(self):
        current, previous = self.pair()
        evidence = current / 'capture/head.txt'
        original = evidence.read_bytes()
        hardlink = self.root / 'hardlinked-report.json'
        os.link(evidence, hardlink)
        existing = self.root / 'existing-report.json'
        existing.write_bytes(b'previous report\n')
        for path in (hardlink, existing):
            with self.subTest(path=path), self.assertRaises(OSError):
                followup.main(['--current', str(current), '--previous', str(previous),
                               '--output', str(path)])
        self.assertEqual(evidence.read_bytes(), original)
        self.assertEqual(hardlink.read_bytes(), original)
        self.assertEqual(existing.read_bytes(), b'previous report\n')


if __name__ == '__main__':
    unittest.main()
