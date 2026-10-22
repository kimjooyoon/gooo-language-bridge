"""Check evidence substitution and omission boundaries against a real local Git object."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.audit_evidence import audit, LEGACY, REPORTS, SUMMARIES, safe_path


class EvidenceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.temporary.name) / 'repository'
        cls.repo.mkdir()
        (cls.repo / 'tools').mkdir()
        (cls.repo / 'tools/source.py').write_bytes(b'trusted source\n')
        def git(*args):
            return subprocess.check_output(['git', '-C', str(cls.repo), *args], stderr=subprocess.DEVNULL)
        git('init')
        git('add', '.')
        git('-c', 'user.name=Evidence test', '-c', 'user.email=test@example.invalid',
            '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'fixture')
        cls.legacy_revision = git('rev-parse', 'HEAD').decode().strip()
        marker = cls.repo / 'bridges/input-defaults/gooo.workspace.json'
        marker.parent.mkdir(parents=True)
        marker.write_text('{}\n')
        git('add', '.')
        git('-c', 'user.name=Evidence test', '-c', 'user.email=test@example.invalid',
            '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'new inventory')
        cls.revision = git('rev-parse', 'HEAD').decode().strip()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        for name, schema in SUMMARIES.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            captured = path.parent / 'capture.txt'
            captured.write_bytes(b'original output\n')
            data = dict(schema='gooo-language-bridge/' + schema + '/v1', decision='PASS',
                        sha256={'capture.txt': hashlib.sha256(captured.read_bytes()).hexdigest()})
            if name not in LEGACY:
                data.update(commit=self.revision, run_id='123')
            if name == 'summary.json':
                data['sha256']['tools/source.py'] = hashlib.sha256(b'trusted source\n').hexdigest()
            path.write_text(json.dumps(data))
        for name in REPORTS:
            path = self.root / name
            data = dict(schema='gooo-language-bridge/js-differential/v1', decision='DIFFERENCES',
                        commit=self.revision, run_id='123', sha256={'capture.txt': hashlib.sha256(b'original output\n').hexdigest()})
            path.write_text(json.dumps(data))
            summary = path.parent / 'summary.json'
            data = json.loads(summary.read_text())
            data['sha256']['report.json'] = hashlib.sha256(path.read_bytes()).hexdigest()
            summary.write_text(json.dumps(data))

    def check(self):
        return audit(self.root, self.revision, self.revision, '123', self.repo)

    def edit(self, name, change):
        path = self.root / name
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def test_complete_bundle_binds_sources_and_differences_are_valid_evidence(self):
        result = self.check()
        self.assertEqual(result['decision'], 'PASS_INTEGRITY')
        self.assertEqual(result['summaries'], 14)
        self.assertEqual(result['native_reports'], 2)
        self.assertEqual(result['source_files'], 1)
        self.assertEqual(result['bound_contexts'], 14)
        self.assertEqual(result['captured_files'], 16)

    def test_output_substitution_and_unhashed_additions_fail(self):
        target = self.root / 'capture.txt'
        target.write_bytes(b'substituted\n')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.check()
        target.write_bytes(b'original output\n')
        (self.root / 'extra.txt').write_text('unbound')
        with self.assertRaisesRegex(ValueError, 'unhashed captured files'):
            self.check()

    def test_local_source_hash_comes_from_commit_not_dirty_checkout(self):
        source = self.repo / 'tools/source.py'
        try:
            source.write_bytes(b'dirty source\n')
            self.check()
            self.edit('summary.json', lambda d: d['sha256'].update({'tools/source.py': hashlib.sha256(source.read_bytes()).hexdigest()}))
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                self.check()
        finally:
            source.write_bytes(b'trusted source\n')

    def test_missing_manifest_or_capture_and_failed_summary_fail(self):
        target = self.root / 'read-reset/summary.json'
        original = target.read_bytes()
        target.unlink()
        with self.assertRaisesRegex(ValueError, 'summary inventory'):
            self.check()
        target.write_bytes(original)
        self.edit('read-reset/summary.json', lambda d: d.update(decision='FAIL_CLOSED'))
        with self.assertRaisesRegex(ValueError, 'unsuccessful'):
            self.check()
        target.write_bytes(original)
        (self.root / 'read-reset/capture.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'missing captured file'):
            self.check()

    def test_wrong_run_missing_context_and_partial_legacy_context_fail(self):
        for name in ('division-comparison/summary.json', 'chroma-gooo/summary.json'):
            path = self.root / name
            original = path.read_bytes()
            for change in (lambda d: d.update(run_id='999'), lambda d: d.update(commit=None)):
                self.edit(name, change)
                with self.assertRaisesRegex(ValueError, 'execution tuple mismatch'):
                    self.check()
                path.write_bytes(original)

    def test_traversal_aliases_and_symlinks_fail(self):
        for path in ('../secret', '/secret', './capture.txt', 'a//b', '.', 'a/../b', 'C:\\secret', 'a\x00b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(path)
        (self.root / 'linked.txt').symlink_to(self.root / 'capture.txt')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.check()

    def test_duplicate_json_keys_and_empty_hashes_fail(self):
        path = self.root / 'summary.json'
        original = path.read_bytes()
        path.write_bytes(original[:-1] + b',"decision":"PASS"}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            self.check()
        path.write_bytes(original)
        self.edit('summary.json', lambda d: d.update(sha256={}))
        with self.assertRaisesRegex(ValueError, 'missing file hashes'):
            self.check()

    def test_revision_arguments_are_not_git_expressions(self):
        for revision in ('HEAD', '--help', 'a' * 39, 'A' * 40):
            with self.assertRaisesRegex(ValueError, 'full lowercase Git SHAs'):
                audit(self.root, revision, self.revision, '123', self.repo)

    def test_inventory_comes_from_trusted_source_and_old_bundles_still_work(self):
        import shutil
        shutil.rmtree(self.root / 'input-defaults')
        with self.assertRaisesRegex(ValueError, 'summary inventory'):
            self.check()
        for name in set(SUMMARIES) | REPORTS:
            path = self.root / name
            if path.exists():
                data = json.loads(path.read_text())
                if name not in LEGACY:
                    data['commit'] = self.legacy_revision
                path.write_text(json.dumps(data))
        for name in REPORTS:
            path = self.root / name
            summary = path.parent / 'summary.json'
            data = json.loads(summary.read_text())
            data['sha256']['report.json'] = hashlib.sha256(path.read_bytes()).hexdigest()
            summary.write_text(json.dumps(data))
        old = audit(self.root, self.legacy_revision, self.legacy_revision, '123', self.repo)
        self.assertEqual(old['summaries'], 13)
        self.assertEqual(old['source_inventory'], 'base-13')
