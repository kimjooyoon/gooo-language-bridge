"""A readback gap must request missing GET evidence, never another publication."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.check_review_readback import check, main

PR = 'https://github.com/example/project/pull/12'
COMMIT = 'a' * 40


def scenario():
    request = {'commit_id': COMMIT, 'event': 'COMMENT', 'body': 'Review\nbody.',
               'comments': [{'path': 'module.go', 'line': 7, 'side': 'RIGHT',
                             'body': 'Keep the original value.'}]}
    review = {'id': 40, 'commit_id': COMMIT, 'body': request['body'],
              'html_url': PR + '#pullrequestreview-40', 'user': {'login': 'reviewer'},
              'pull_request_url': 'https://api.github.com/repos/example/project/pulls/12',
              'state': 'COMMENTED', 'submitted_at': '2026-10-27T20:00:00Z'}
    comment = {'id': 50, 'pull_request_review_id': 40,
               'html_url': PR + '#discussion_r50', 'user': {'login': 'reviewer'},
               'pull_request_url': 'https://api.github.com/repos/example/project/pulls/12',
               'commit_id': COMMIT, 'original_commit_id': COMMIT,
               'path': 'module.go', 'body': request['comments'][0]['body'],
               'position': 19, 'original_position': 19}
    detail = dict(comment, line=7, original_line=7, side='RIGHT', start_line=None,
                  original_start_line=None, start_side=None)
    return request, review, [comment], [detail]


def evaluate(parts, **kwargs):
    return check(*parts, target=PR, **kwargs)


class ReadbackTests(unittest.TestCase):
    def test_legacy_collection_needs_details_and_position_is_never_a_line(self):
        request, review, listed, _ = scenario()
        listed[0]['position'] = 7
        result = evaluate((request, review, listed, []))
        self.assertEqual(result['decision'], 'COMMENT_DETAILS_NEEDED')
        self.assertEqual(result['missing_comment_ids'], [50])
        self.assertEqual(result['next_action'], 'READ_COMMENT_DETAILS')
        self.assertEqual(result['publication_effects'], 0)
        self.assertFalse(result['repost_recommended'])

    def test_details_establish_recorded_fields_without_establishing_authentication(self):
        result = evaluate(scenario(), reviewer='reviewer')
        self.assertEqual(result['decision'], 'CAPTURED_REVIEW_MATCHES_REQUEST')
        self.assertEqual(result['captured_comment_anchors'], 1)
        self.assertEqual(result['comment_bindings'][0]['line'], 7)
        for field in ('source_authenticated', 'remote_freshness_established',
                      'patch_approval_verified', 'repost_recommended'):
            self.assertFalse(result[field])

    def test_full_collection_can_avoid_an_unnecessary_detail_read(self):
        request, review, _, details = scenario()
        self.assertEqual(evaluate((request, review, details, []))['decision'],
                         'CAPTURED_REVIEW_MATCHES_REQUEST')

    def test_multiple_comments_match_by_content_not_array_order(self):
        request, review, listed, details = scenario()
        request['comments'].append(dict(request['comments'][0], line=20, body='Second finding.'))
        second = dict(details[0], id=51, line=20, original_line=20,
                      html_url=PR + '#discussion_r51', body='Second finding.')
        listed.append({k: v for k, v in second.items() if k not in
                       ('line', 'original_line', 'side', 'start_line',
                        'original_start_line', 'start_side')})
        result = evaluate((request, review, listed, [second, details[0]]))
        self.assertEqual(result['decision'], 'CAPTURED_REVIEW_MATCHES_REQUEST')
        self.assertEqual(result['captured_comment_anchors'], 2)

    def test_original_anchor_survives_a_later_head_and_current_line_move(self):
        parts = scenario()
        parts[3][0].update(commit_id='b' * 40, line=11)
        result = evaluate(parts)
        self.assertEqual(result['decision'], 'CAPTURED_REVIEW_MATCHES_REQUEST')
        self.assertEqual(result['comment_bindings'][0]['anchor'], 'original')
        self.assertEqual(result['comment_bindings'][0]['line'], 7)

    def test_current_anchor_requires_the_exact_commit_when_original_is_absent(self):
        parts = scenario()
        for key in ('original_commit_id', 'original_line', 'original_start_line'):
            parts[3][0].pop(key)
        self.assertEqual(evaluate(parts)['comment_bindings'][0]['anchor'], 'current_exact_commit')
        parts[3][0]['commit_id'] = 'b' * 40
        self.assertEqual(evaluate(parts)['decision'], 'COMMENT_DETAILS_NEEDED')

    def test_multiline_anchor_and_missing_range_metadata(self):
        parts = scenario()
        parts[0]['comments'][0].update(start_line=5, start_side='RIGHT')
        parts[3][0].update(start_line=5, original_start_line=5, start_side='RIGHT')
        self.assertEqual(evaluate(parts)['decision'], 'CAPTURED_REVIEW_MATCHES_REQUEST')
        parts[3][0].pop('start_side')
        self.assertEqual(evaluate(parts)['decision'], 'COMMENT_DETAILS_NEEDED')

    def test_body_anchor_identity_and_target_mismatches_never_suggest_reposting(self):
        changes = [lambda p: p[1].update(body='Edited body'),
                   lambda p: p[1].update(commit_id='b' * 40),
                   lambda p: p[1].update(html_url=PR.replace('/12', '/13') + '#pullrequestreview-40'),
                   lambda p: p[1].update(pull_request_url='https://api.github.com/repos/other/repo/pulls/12'),
                   lambda p: p[3][0].update(body='Another finding'),
                   lambda p: p[3][0].update(original_line=8, line=8),
                   lambda p: p[3][0].update(side='LEFT'),
                   lambda p: p[3][0].update(path='other.go'),
                   lambda p: p[3][0].update(pull_request_review_id=41),
                   lambda p: p[3][0].update(pull_request_url='https://api.github.com/repos/other/repo/pulls/12'),
                   lambda p: p[3][0].update(original_commit_id='b' * 40),
                   lambda p: p[3][0].update(in_reply_to_id=49),
                   lambda p: p[3][0]['user'].update(login='someone-else')]
        for change in changes:
            with self.subTest(change=change):
                parts = deepcopy(scenario())
                change(parts)
                result = evaluate(parts)
                self.assertEqual(result['decision'], 'CAPTURE_MISMATCH')
                self.assertFalse(result['repost_recommended'])
                self.assertEqual(result['next_action'], 'INSPECT_CAPTURE')
        self.assertEqual(evaluate(scenario(), reviewer='another')['decision'], 'CAPTURE_MISMATCH')

    def test_shared_listing_and_detail_disagreement_is_visible(self):
        parts = scenario()
        parts[2][0]['body'] = 'Older body'
        self.assertIn('50:LIST_DETAIL_BODY', evaluate(parts)['issues'])
        parts = scenario()
        parts[2][0]['original_line'] = 99
        self.assertIn('50:LIST_DETAIL_ORIGINAL_LINE', evaluate(parts)['issues'])

    def test_visual_similarity_is_not_exact_comment_text_equality(self):
        parts = scenario()
        parts[0]['comments'][0]['body'] = '\uac00\nvalue'
        parts[2][0]['body'] = parts[3][0]['body'] = '\u1100\u1161\nvalue'
        self.assertEqual(evaluate(parts)['decision'], 'CAPTURE_MISMATCH')

    def test_duplicate_missing_and_unlisted_ids_cannot_cover_expected_comments(self):
        request, review, listed, details = scenario()
        for values in [(request, review, listed + listed, details),
                       (request, review, listed, details + details)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                evaluate(values)
        self.assertEqual(evaluate((request, review, [], details))['decision'], 'CAPTURE_MISMATCH')
        request['comments'].append(deepcopy(request['comments'][0]))
        self.assertIn('LISTED_COMMENT_COUNT_DIFFERS',
                      evaluate((request, review, listed, details))['issues'])

    def test_matching_two_ids_to_the_same_expected_finding_does_not_hide_another(self):
        request, review, listed, details = scenario()
        request['comments'].append(dict(request['comments'][0], body='Other issue'))
        other = dict(details[0], id=51, html_url=PR + '#discussion_r51')
        result = evaluate((request, review, listed + [other], details + [other]))
        self.assertEqual(result['decision'], 'CAPTURE_MISMATCH')
        self.assertIn('51:COMMENT_NOT_REQUESTED', result['issues'])

    def test_pending_and_missing_submission_capture_require_a_review_read(self):
        for change in [dict(state='PENDING', submitted_at=None), dict(submitted_at=None)]:
            parts = scenario()
            parts[1].update(change)
            result = evaluate(parts)
            self.assertEqual(result['decision'], 'REVIEW_DETAILS_NEEDED')
            self.assertEqual(result['next_action'], 'READ_REVIEW')

    def test_captured_approval_states_are_metadata_not_patch_approval(self):
        for event, state in [('APPROVE', 'APPROVED'), ('REQUEST_CHANGES', 'CHANGES_REQUESTED')]:
            parts = scenario()
            parts[0]['event'], parts[1]['state'] = event, state
            result = evaluate(parts)
            self.assertEqual(result['decision'], 'CAPTURED_REVIEW_MATCHES_REQUEST')
            self.assertFalse(result['patch_approval_verified'])
        parts[1]['state'] = 'DISMISSED'
        self.assertEqual(evaluate(parts)['decision'], 'CAPTURE_MISMATCH')

    def test_body_only_review_and_api_added_fields_are_supported(self):
        request, review, _, _ = scenario()
        request['comments'] = []
        review['new_api_field'] = {'uninterpreted': True}
        self.assertEqual(evaluate((request, review, [], []))['decision'],
                         'CAPTURED_REVIEW_MATCHES_REQUEST')

    def test_unsupported_requests_and_invalid_identity_types_are_refused(self):
        for change in [lambda p: p[0].update(commit_id='abc'),
                       lambda p: p[0].update(event='PENDING'),
                       lambda p: p[0]['comments'][0].update(line=True),
                       lambda p: p[0]['comments'][0].update(position=1),
                       lambda p: p[0]['comments'][0].update(start_line=5),
                       lambda p: p[3][0].update(id=True),
                       lambda p: p[3][0].update(pull_request_review_id=True),
                       lambda p: p[3][0].update(original_line=-1)]:
            with self.subTest(change=change):
                parts = deepcopy(scenario())
                change(parts)
                with self.assertRaises(ValueError):
                    evaluate(parts)
        with self.assertRaises(ValueError):
            check(*scenario(), target=PR + '?unexpected=1')


class CLITests(unittest.TestCase):
    def test_published_example_from_an_external_working_directory(self):
        repo = Path(__file__).resolve().parents[1]
        example = repo / 'examples/review-readback'
        common = [sys.executable, str(repo / 'tools/check_review_readback.py'),
                  '--pull-request', PR, '--request', str(example / 'request.json'),
                  '--review', str(example / 'review.json'),
                  '--comments', str(example / 'comments.json')]
        with tempfile.TemporaryDirectory() as directory:
            for label, extra, code in [('missing', [], 1),
                                       ('complete', ['--details', str(example / 'details.json')], 0)]:
                result = subprocess.run(common + extra + ['--out', str(Path(directory) / label)],
                                        cwd=directory, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertFalse(json.loads(result.stdout)['repost_recommended'])

    def inputs(self, root):
        parts = scenario()
        for name, value in zip(('request', 'review', 'comments', 'details'), parts):
            (root / (name + '.json')).write_text(json.dumps(value) + '\n')
        return ['--pull-request', PR] + [arg for name in ('request', 'review', 'comments')
                                        for arg in ('--' + name, str(root / (name + '.json')))]

    def run_main(self, args):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(args)
        return code, json.loads(output.getvalue())

    def test_two_stage_cli_retains_missing_detail_and_successful_originals_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.inputs(root)
            code, first = self.run_main(args + ['--out', str(root / 'first')])
            self.assertEqual(code, 1)
            self.assertEqual(first['missing_comment_ids'], [50])
            code, second = self.run_main(args + ['--details', str(root / 'details.json'),
                                               '--out', str(root / 'second')])
            self.assertEqual(code, 0)
            self.assertEqual(second['decision'], 'CAPTURED_REVIEW_MATCHES_REQUEST')
            self.assertEqual((root / 'second/details.original').read_bytes(),
                             (root / 'details.json').read_bytes())
            self.assertIn('check_review_readback.py', second['sha256'])
            before = (root / 'first/report.json').read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args + ['--out', str(root / 'first')]), 2)
            self.assertEqual(before, (root / 'first/report.json').read_bytes())

    def test_invalid_json_keeps_first_diagnostic_and_input(self):
        for bad in [b'{"commit_id":1,"commit_id":2}', b'{"event":NaN}', b'\xff']:
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args = self.inputs(root)
                (root / 'request.json').write_bytes(bad)
                code, result = self.run_main(args + ['--out', str(root / 'result')])
                self.assertEqual(code, 2)
                self.assertEqual(result['decision'], 'INVALID_CAPTURE')
                self.assertEqual((root / 'result/request.original').read_bytes(), bad)

    def test_oversized_capture_is_refused_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.inputs(root)
            (root / 'request.json').write_bytes(b' ' * (8 * 1024 * 1024 + 1))
            code, result = self.run_main(args + ['--out', str(root / 'result')])
            self.assertEqual(code, 2)
            self.assertEqual(result['decision'], 'INVALID_CAPTURE')
            self.assertNotIn('request.original', result['sha256'])

    @unittest.skipUnless(hasattr(os, 'mkfifo') and hasattr(os, 'O_NONBLOCK'), 'POSIX pipes')
    def test_pipe_input_is_refused_without_waiting_for_a_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.inputs(root)
            (root / 'request.json').unlink()
            os.mkfifo(root / 'request.json')
            tool = Path(__file__).resolve().parents[1] / 'tools/check_review_readback.py'
            result = subprocess.run([sys.executable, str(tool), *args,
                                     '--out', str(root / 'result')],
                                    capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['decision'], 'INVALID_CAPTURE')


if __name__ == '__main__':
    unittest.main()
