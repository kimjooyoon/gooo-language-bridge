"""A failed collection must not destroy the evidence that preceded it."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import check_candidates as collector


class CandidateRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = self.root / 'bridges/contribution-review'
        self.bridge.mkdir(parents=True)
        for source in collector.BRIDGE.iterdir():
            if source.is_file():
                (self.bridge / source.name).write_bytes(source.read_bytes())
        source = self.root / 'tools/check_candidates.py'
        source.parent.mkdir()
        source.write_bytes(Path(collector.__file__).read_bytes())
        self.binary = self.root / 'gooo'
        self.binary.write_bytes(b'fake compiler for mocked process tests')
        self.output = self.root / 'evidence/candidate-scan'
        self.output.mkdir(parents=True)
        self.response = {'data': {'rateLimit': {'cost': 1, 'remaining': 4999, 'resetAt': '2026-10-25T01:00:00Z'},
                                'r0': {'nameWithOwner': 'example/tool', 'isPrivate': False,
                                       'pullRequests': {'nodes': [], 'pageInfo': {'hasNextPage': False}},
                                       'openPullRequests': {'nodes': [], 'pageInfo': {'hasNextPage': False}},
                                       'i0': {'number': 1, 'url': 'https://github.com/example/tool/issues/1',
                                              'state': 'OPEN', 'title': 'Synthetic fixture',
                                              'body': 'Prior work\n한글 🙂',
                                              'comments': {'nodes': [], 'pageInfo': {'hasPreviousPage': False}},
                                              'timelineItems': {'nodes': [], 'pageInfo': {'hasPreviousPage': False}}}}}}

    def process(self, command, **kwargs):
        if command[0] == 'gh':
            return subprocess.CompletedProcess(command, 0, json.dumps(self.response).encode(), b'api diagnostic')
        if command[1] == 'version':
            return subprocess.CompletedProcess(command, 0, b'{"version":"0.6.38-dev"}', b'compiler diagnostic')
        cases_path = Path(command[command.index('--cases') + 1])
        cases = json.loads(cases_path.read_bytes())['cases']
        traces = []
        for i, case in enumerate(cases):
            traces.append({'case_index': i, 'deliveries': [{'activity_id': collector.ACTIVITY,
                           'input': case['inputs'][collector.KEY], 'actual': case['expected'][collector.KEY],
                           'expected': case['expected'][collector.KEY], 'passed': True}]})
        value = {'decision': 'PASS', 'cases_digest': collector.digest(cases_path),
                 'manifest_digest': collector.digest(self.bridge / 'gooo.workspace.json'),
                 'result': {'runtime': {'finite_total': len(cases), 'finite_passed': len(cases), 'traces': traces}}}
        return subprocess.CompletedProcess(command, 0, json.dumps(value).encode(), b'execution diagnostic')

    def run_collector(self, process=None, extra=None):
        stdout = io.StringIO()
        with patch.object(collector, 'ROOT', self.root), patch.object(collector, 'BRIDGE', self.bridge), \
                patch.object(collector, '_run_bounded', side_effect=process or self.process) as calls, \
                redirect_stdout(stdout):
            code = collector.main(['--gooo', str(self.binary)] + (extra or ['--candidate', 'example/tool#1']))
        return code, json.loads(stdout.getvalue()), calls

    def pointer(self):
        value = json.loads((self.output / 'latest-attempt.json').read_bytes())
        manifest = self.output / value['attempt_manifest']
        self.assertEqual(collector.digest(manifest), value['manifest_sha256'])
        summary = json.loads(manifest.read_bytes())
        self.assertEqual(value['decision'], summary['decision'])
        for name, fingerprint in summary['sha256'].items():
            self.assertEqual(collector.digest(self.root / name), fingerprint)
        for source, snapshot in summary['source_snapshots'].items():
            self.assertEqual(summary['sha256'][source], summary['sha256'][snapshot])
        return manifest.parent, summary

    def test_success_then_timeout_preserves_legacy_and_successful_attempt_bytes(self):
        legacy = {'summary.json': b'{"decision":"PASS","legacy":true}', 'request.json': b'old request',
                  'github.json': b'old response', 'github.stderr': b'old diagnostic'}
        for name, data in legacy.items():
            (self.output / name).write_bytes(data)
        code, summary, _ = self.run_collector()
        self.assertEqual(code, 0)
        first, _ = self.pointer()
        before = {p.relative_to(self.output): p.read_bytes() for p in self.output.rglob('*') if p.is_file()}

        def timeout(command, **kwargs):
            raise subprocess.TimeoutExpired(command, 60, output=b'{"partial":', stderr=b'rate limit diagnostic')

        code, failed, calls = self.run_collector(timeout)
        self.assertEqual(code, 1)
        self.assertEqual(calls.call_count, 1)
        last, manifest = self.pointer()
        self.assertNotEqual(first, last)
        self.assertEqual(manifest['stage'], 'api')
        self.assertTrue(manifest['api_timed_out'])
        self.assertEqual(manifest['github_requests'], 1)
        self.assertNotIn('api_exit_code', manifest)
        self.assertEqual((last / 'github.json').read_bytes(), b'{"partial":')
        self.assertEqual((last / 'github.stderr').read_bytes(), b'rate limit diagnostic')
        self.assertFalse((last / 'results.json').exists())
        for name, data in before.items():
            if str(name) != 'latest-attempt.json':
                self.assertEqual((self.output / name).read_bytes(), data)
        for name, data in legacy.items():
            self.assertEqual((self.output / name).read_bytes(), data)

    def test_capture_keeps_sources_body_and_all_success_diagnostics(self):
        code, summary, _ = self.run_collector()
        self.assertEqual(code, 0)
        out, manifest = self.pointer()
        self.assertEqual(manifest['stage'], 'complete')
        self.assertEqual(json.loads((out / 'results.json').read_bytes())[0]['issue_body'], 'Prior work\n한글 🙂')
        for name, source in [('collector-source.py', self.root / 'tools/check_candidates.py'),
                             ('policy-source.gooo', self.bridge / 'main.gooo'),
                             ('workspace-source.json', self.bridge / 'gooo.workspace.json'),
                             ('policy-provenance.json', self.bridge / 'provenance.json')]:
            self.assertEqual((out / name).read_bytes(), source.read_bytes())
        for name in ['github.stderr', 'compiler.stderr', 'execution.stderr']:
            self.assertTrue((out / name).read_bytes())
        self.assertFalse((self.output / 'summary.json').exists())
        self.assertFalse(list(self.output.glob('.latest-*.tmp')))

    def test_execution_timeout_keeps_request_response_version_and_partial_receipt(self):
        def timeout(command, **kwargs):
            if command[1] == 'package':
                raise subprocess.TimeoutExpired(command, 90, output=b'{"result":', stderr=b'partial runtime error')
            return self.process(command, **kwargs)

        code, _, _ = self.run_collector(timeout)
        self.assertEqual(code, 1)
        out, summary = self.pointer()
        self.assertEqual(summary['stage'], 'execution')
        self.assertTrue(summary['execution_timed_out'])
        self.assertEqual((out / 'execution.json').read_bytes(), b'{"result":')
        self.assertEqual((out / 'execution.stderr').read_bytes(), b'partial runtime error')
        for name in ['request.json', 'github.json', 'observations.json', 'cases.json', 'compiler.json']:
            self.assertTrue((out / name).exists())
        self.assertFalse((out / 'results.json').exists())

    def test_unlinked_draft_inventory_survives_raw_capture_and_policy_execution(self):
        draft = {'number': 5, 'url': 'https://github.com/example/tool/pull/5',
                 'title': 'Unlinked owner work', 'author': {'login': 'example'},
                 'isDraft': True, 'baseRefName': 'main', 'baseRefOid': 'a' * 40,
                 'headRefName': 'feat/parser-recovery', 'headRefOid': 'b' * 40,
                 'reviews': {'nodes': [], 'pageInfo': {'hasPreviousPage': False}}}
        inventory = {'nodes': [draft], 'pageInfo': {'hasNextPage': True}}
        self.response['data']['r0']['openPullRequests'] = inventory
        code, _, calls = self.run_collector()
        self.assertEqual(code, 0)
        self.assertEqual(calls.call_count, 3)
        out, summary = self.pointer()
        self.assertEqual(summary['github_requests'], 1)
        captured = json.loads((out / 'github.json').read_bytes())
        self.assertEqual(captured['data']['r0']['openPullRequests'], inventory)
        for name in ('observations.json', 'results.json'):
            row = json.loads((out / name).read_bytes())[0]
            self.assertEqual(row['repository_open_prs'], [draft])
            self.assertTrue(row['open_pr_sample_has_more'])
            self.assertFalse(row['observation']['open_pr'])
            self.assertTrue(row['observation']['history_complete'])

    def test_missing_open_pr_inventory_retains_raw_failure_without_running_policy(self):
        del self.response['data']['r0']['openPullRequests']
        code, _, calls = self.run_collector()
        self.assertEqual(code, 1)
        self.assertEqual(calls.call_count, 1)
        out, summary = self.pointer()
        self.assertEqual(summary['decision'], 'FAIL_CLOSED')
        self.assertEqual(json.loads((out / 'github.json').read_bytes()), self.response)
        self.assertFalse((out / 'results.json').exists())
        self.assertFalse((out / 'execution.json').exists())

    def test_api_failure_and_malformed_response_are_retained_without_compiler_execution(self):
        for status, payload in [(1, b'permission denied'), (0, b'{broken json')]:
            def failed(command, **kwargs):
                return subprocess.CompletedProcess(command, status, payload, b'real stderr')

            code, _, calls = self.run_collector(failed)
            self.assertEqual(code, 1)
            self.assertEqual(calls.call_count, 1)
            out, summary = self.pointer()
            self.assertEqual(summary['decision'], 'FAIL_CLOSED')
            self.assertEqual(summary['api_exit_code'], status)
            self.assertEqual((out / 'github.json').read_bytes(), payload)
            self.assertEqual((out / 'github.stderr').read_bytes(), b'real stderr')

    def test_attempt_budget_does_not_delete_data_change_pointer_or_call_github(self):
        self.run_collector()
        for i in range(collector.MAX_LIVE_ATTEMPTS - 1):
            (self.output / ('attempt-retained-%d' % i)).mkdir()
        before = {p.relative_to(self.output): p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        code, summary, calls = self.run_collector()
        self.assertEqual(code, 1)
        self.assertEqual(summary['github_requests'], 0)
        self.assertEqual(calls.call_count, 0)
        self.assertIn('budget', summary['error'])
        self.assertEqual({p.relative_to(self.output): p.read_bytes() for p in self.output.rglob('*') if p.is_file()}, before)

    def test_compiler_timeout_preserves_diagnostics_without_a_policy_result(self):
        def timeout(command, **kwargs):
            if command[1] == 'version':
                raise subprocess.TimeoutExpired(command, 10, output=b'partial version', stderr=b'compiler stalled')
            return self.process(command, **kwargs)

        code, _, calls = self.run_collector(timeout)
        self.assertEqual(code, 1)
        self.assertEqual(calls.call_count, 2)
        out, summary = self.pointer()
        self.assertTrue(summary['compiler_timed_out'])
        self.assertEqual(summary['stage'], 'compiler')
        self.assertEqual((out / 'compiler.json').read_bytes(), b'partial version')
        self.assertEqual((out / 'compiler.stderr').read_bytes(), b'compiler stalled')
        self.assertFalse((out / 'execution.json').exists())

    def test_unbound_receipt_is_retained_without_creating_results(self):
        def unbound(command, **kwargs):
            process = self.process(command, **kwargs)
            if command[1] == 'package':
                receipt = json.loads(process.stdout)
                receipt['cases_digest'] = 'sha256:' + '0' * 64
                process.stdout = json.dumps(receipt).encode()
            return process

        code, _, _ = self.run_collector(unbound)
        self.assertEqual(code, 1)
        out, summary = self.pointer()
        self.assertEqual(summary['execution_exit_code'], 0)
        self.assertIn('digest', summary['error'])
        self.assertTrue((out / 'execution.json').exists())
        self.assertFalse((out / 'results.json').exists())

    def test_changed_source_is_not_presented_as_a_verified_captured_source(self):
        original = (self.bridge / 'main.gooo').read_bytes()

        def changed(command, **kwargs):
            process = self.process(command, **kwargs)
            if command[1] == 'package':
                (self.bridge / 'main.gooo').write_bytes(original + b'\n# changed during execution\n')
            return process

        code, summary, _ = self.run_collector(changed)
        self.assertEqual(code, 1)
        self.assertIn('source changed', summary['error'])
        pointer = json.loads((self.output / 'latest-attempt.json').read_bytes())
        manifest = self.output / pointer['attempt_manifest']
        self.assertEqual(collector.digest(manifest), pointer['manifest_sha256'])
        self.assertEqual((manifest.parent / 'policy-source.gooo').read_bytes(), original)
        self.assertFalse((manifest.parent / 'results.json').exists())

    def test_offline_policy_still_has_32_cases_and_does_not_touch_live_history(self):
        (self.output / 'summary.json').write_bytes(b'legacy live bytes')
        code, summary, calls = self.run_collector(extra=['--self-test'])
        self.assertEqual(code, 0)
        self.assertEqual(summary['cases'], 32)
        self.assertEqual(summary['github_requests'], 0)
        self.assertEqual(calls.call_count, 2)
        self.assertEqual((self.output / 'summary.json').read_bytes(), b'legacy live bytes')
        self.assertTrue((self.root / 'evidence/candidate-policy/summary.json').exists())
