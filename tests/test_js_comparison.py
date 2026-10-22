"""Adversarial snapshot and subprocess checks for the reusable comparison tool."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.compare_js import classify, observer_source, run_step, snapshots, verify_source_module


def one(result, **extra):
    return snapshots(json.dumps([dict(id='case', result=result, **extra)]).encode())


class SnapshotTests(unittest.TestCase):
    def test_engine_selection_binds_repository_module_and_rendered_import(self):
        template = 'import engine "github.com/dop251/goja"\n'
        for engine, owner in [('goja', 'dop251/goja'), ('sobek', 'grafana/sobek')]:
            with self.subTest(engine=engine):
                repository, module, source = observer_source(engine, template)
                self.assertEqual(repository, 'https://github.com/' + owner + '.git')
                self.assertEqual(module, 'github.com/' + owner)
                self.assertEqual(source, 'import engine "' + module + '"\n')
                verify_source_module('module ' + module + '\n\ngo 1.26.0\n', module)
                with self.assertRaisesRegex(ValueError, 'source module differs'):
                    verify_source_module('module github.com/wrong/source\n', module)
        for engine, invalid in [('other', template), ('sobek', ''), ('sobek', template * 2)]:
            with self.assertRaises(ValueError):
                observer_source(engine, invalid)

    def test_boolean_numeric_and_recursive_types_remain_distinct(self):
        for a, b in [(True, 1), (False, 0), ([True], [1]), ({'x': False}, {'x': 0}), ('1', 1)]:
            with self.subTest(a=a, b=b):
                self.assertEqual(classify(one(a), one(b))['head_differences'], ['case'])
        self.assertEqual(classify(one(1), one(1.0))['head_differences'], [])

    def test_duplicate_keys_nonfinite_and_incomplete_snapshots_fail(self):
        for raw in (b'[{"id":"x","id":"y","result":1}]',
                    b'[{"id":"x","result":{"a":1,"a":2}}]',
                    b'[{"id":"x","result":NaN}]', b'[]',
                    b'[{"id":"x","result":1},{"id":"x","result":2}]',
                    b'[{"id":"x"}]', b'{"id":"x","result":1}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                snapshots(raw)

    def test_changed_or_missing_input_identity_is_not_a_result_difference(self):
        for head in (one('same'), one('same', input=True), one('same', input=[2])):
            with self.assertRaises(ValueError):
                classify(one('same', input=[1]), head)
        with self.assertRaises(ValueError):
            classify(one('same'), {'different': {'id': 'different', 'result': 'same'}})

    def test_regression_categories_preserve_preexisting_and_changed_differences(self):
        cases = [('corrected', 1, 0, 1), ('introduced', 1, 1, 0),
                 ('unchanged_differences', 1, 0, 0), ('changed_but_still_differs', 1, 0, 2)]
        for category, reference, base, head in cases:
            with self.subTest(category=category):
                groups = classify(one(reference), one(head), one(base))
                self.assertEqual(groups[category], ['case'])

    def test_escaped_surrogates_remain_separate_from_replacement(self):
        self.assertEqual(classify(one('\ud800'), one('\ufffd'))['head_differences'], ['case'])
        self.assertEqual(classify(one({'a': 1, 'b': 2}), one({'b': 2, 'a': 1}))['head_differences'], [])


class ProcessTests(unittest.TestCase):
    def test_inherited_git_context_cannot_redirect_the_temporary_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            foreign = work / 'foreign'
            foreign.mkdir()
            sentinel = foreign / 'keep.txt'
            sentinel.write_text('unchanged')
            out = work / 'logs'
            out.mkdir()
            hostile = dict(os.environ, GIT_DIR=str(foreign / '.git'), GIT_WORK_TREE=str(foreign),
                           GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.worktree',
                           GIT_CONFIG_VALUE_0=str(foreign))
            run_step('git-isolation', ['git', 'init', '--object-format=sha1', '-q', 'owned'],
                     work, hostile, out, [])
            self.assertTrue((work / 'owned/.git').is_dir())
            self.assertFalse((foreign / '.git').exists())
            self.assertEqual(sentinel.read_text(), 'unchanged')
            self.assertEqual(hostile['GIT_DIR'], str(foreign / '.git'))

    def test_timeout_is_recorded_and_process_is_reaped(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            steps = []
            with self.assertRaisesRegex(ValueError, 'timed out'):
                run_step('deadline', [sys.executable, '-c', 'import time; time.sleep(10)'],
                         out, dict(os.environ), out, steps, timeout=0.1)
            self.assertIsNotNone(steps[0]['exit_code'])
            self.assertNotEqual(steps[0]['exit_code'], 0)

    def test_oversized_output_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            steps = []
            with patch('tools.compare_js.LIMIT', 512), self.assertRaisesRegex(ValueError, 'output exceeds'):
                run_step('oversized', [sys.executable, '-c', 'print("x" * 2048)'],
                         out, dict(os.environ), out, steps)
            self.assertIn('output exceeds', steps[0]['error'])

    def test_nonzero_exit_cannot_look_like_a_successful_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            steps = []
            with self.assertRaisesRegex(ValueError, 'exited 3'):
                run_step('failed', [sys.executable, '-c', 'print("[]"); raise SystemExit(3)'],
                         out, dict(os.environ), out, steps)
            self.assertEqual(steps[0]['exit_code'], 3)
            self.assertEqual((out / 'failed.stdout').read_text().strip(), '[]')


if __name__ == '__main__':
    unittest.main()
