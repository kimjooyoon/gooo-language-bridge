"""Saved bytes must be linked to the requested revision, not merely present."""
from copy import deepcopy
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import check_gist_readback as tool


GIST_ID = 'a' * 32
TARGET = 'https://gist.github.com/example/' + GIST_ID


def git_object(kind, content):
    header = kind.encode() + b' ' + str(len(content)).encode() + b'\0'
    oid = hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
    return oid, kind, content


def batch(*objects):
    return b''.join(oid.encode() + b' ' + kind.encode() + b' '
                    + str(len(content)).encode() + b'\n' + content + b'\n'
                    for oid, kind, content in objects)


def tree_entry(name, oid, mode=b'100644'):
    encoded = name.encode() if isinstance(name, str) else name
    return mode + b' ' + encoded + b'\0' + bytes.fromhex(oid)


def commit_bytes(tree, message=b'Captured example\n'):
    return (b'tree ' + tree.encode()
            + b'\nauthor Example <example@example.com> 1 +0000'
            + b'\ncommitter Example <example@example.com> 1 +0000\n\n' + message)


def scenario(files=None):
    if files is None:
        files = {'alpha.txt': b'alpha\n', 'bravo.txt': b'bravo\n',
                 'manifest.json': b'{"published":true}\n'}
    blobs = {name: git_object('blob', content) for name, content in files.items()}
    tree = git_object('tree', b''.join(
        tree_entry(name, blobs[name][0]) for name in sorted(files, key=lambda x: x.encode())))
    commit = git_object('commit', commit_bytes(tree[0]))
    # The external expected manifest also covers the published inner manifest.
    manifest = {name: {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                for name, content in files.items()}
    api = {'id': GIST_ID, 'html_url': TARGET, 'owner': {'login': 'example'},
           'history': [{'version': commit[0]}], 'files': {}}
    for name, content in files.items():
        api['files'][name] = {
            'filename': name, 'size': len(content), 'truncated': False,
            'encoding': 'utf-8', 'content': content.decode(),
            # This is a blob OID, deliberately different from the revision.
            'raw_url': 'https://gist.githubusercontent.com/example/' + GIST_ID
                       + '/raw/' + blobs[name][0] + '/' + name}
    unique_blobs = {obj[0]: obj for obj in blobs.values()}
    return {'manifest': manifest, 'api': api, 'blobs': blobs, 'tree': tree,
            'commit': commit, 'revision': commit[0],
            'raw': batch(*unique_blobs.values(), tree, commit)}


def with_tree(fixture, content, message=b'Captured example\n'):
    result = deepcopy(fixture)
    tree = git_object('tree', content)
    commit = git_object('commit', commit_bytes(tree[0], message))
    blobs = {obj[0]: obj for obj in result['blobs'].values()}
    result.update(tree=tree, commit=commit, revision=commit[0],
                  raw=batch(*blobs.values(), tree, commit))
    result['api']['history'][0]['version'] = commit[0]
    return result


def evaluate(fixture):
    return tool.check(fixture['manifest'], fixture['api'], fixture['raw'],
                      TARGET, fixture['revision'])


class GistReadbackTests(unittest.TestCase):
    def assert_no_authority_or_effects(self, report):
        for field in ('source_authenticated', 'remote_freshness_established',
                      'patch_approval_verified', 'captured_source_executed',
                      'repost_recommended'):
            self.assertFalse(report[field], field)
        self.assertEqual(report['network_requests'], 0)
        self.assertEqual(report['publication_effects'], 0)

    def test_linked_flat_revision_covers_every_file_including_published_manifest(self):
        fixture = scenario()
        report = evaluate(fixture)
        self.assertEqual(report['decision'], 'GIT_BLOBS_MATCH_MANIFEST')
        self.assertTrue(report['git_blob_bytes_match'])
        self.assertTrue(report['api_metadata_matches'])
        self.assertEqual({r['filename'] for r in report['file_bindings']},
                         set(fixture['manifest']))
        self.assertEqual(report['root_tree'], fixture['tree'][0])
        self.assertNotEqual(fixture['blobs']['alpha.txt'][0], fixture['revision'])
        self.assert_no_authority_or_effects(report)

    def test_empty_and_shared_blobs_are_valid_without_duplicate_object_records(self):
        fixture = scenario({'empty.txt': b'', 'one.txt': b'same',
                            'two.txt': b'same', 'manifest.json': b'{}\n'})
        report = evaluate(fixture)
        self.assertEqual(report['decision'], 'GIT_BLOBS_MATCH_MANIFEST')
        bindings = {row['filename']: row for row in report['file_bindings']}
        self.assertEqual(bindings['empty.txt']['bytes'], 0)
        self.assertEqual(bindings['one.txt']['blob'], bindings['two.txt']['blob'])

    def test_binary_payload_with_newlines_and_header_text_is_read_by_byte_length(self):
        fixture = scenario({'binary.dat': b'placeholder', 'manifest.json': b'{}\n'})
        content = b'\0\xff\n' + b'0' * 40 + b' blob 0\n\nnot another object\n'
        blob = git_object('blob', content)
        fixture['blobs']['binary.dat'] = blob
        fixture['manifest']['binary.dat'] = {
            'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        fixture['api']['files']['binary.dat'].update(
            size=len(content), encoding='base64',
            content=base64.b64encode(content).decode(),
            raw_url='https://gist.githubusercontent.com/example/' + GIST_ID
                    + '/raw/' + blob[0] + '/binary.dat')
        changed = with_tree(fixture, b''.join(
            tree_entry(name, obj[0]) for name, obj in sorted(fixture['blobs'].items())))
        report = evaluate(changed)
        self.assertEqual(report['decision'], 'GIT_BLOBS_MATCH_API_TEXT_INCOMPLETE')
        self.assertTrue(report['git_blob_bytes_match'])
        self.assertEqual(report['api_text_incomplete'], ['binary.dat'])
        binding = next(row for row in report['file_bindings'] if row['filename'] == 'binary.dat')
        self.assertEqual(binding['sha256'], hashlib.sha256(content).hexdigest())

    def test_correct_loose_objects_cannot_replace_a_missing_commit_tree_or_blob(self):
        fixture = scenario()
        for missing in (fixture['commit'], fixture['tree'], fixture['blobs']['alpha.txt']):
            with self.subTest(missing=missing):
                changed = deepcopy(fixture)
                objects = list({o[0]: o for o in fixture['blobs'].values()}.values())
                objects += [fixture['tree'], fixture['commit']]
                changed['raw'] = batch(*(o for o in objects if o != missing))
                report = evaluate(changed)
                self.assertEqual(report['decision'], 'GIT_OBJECTS_NEEDED')
                self.assertEqual(report['missing_object_ids'], [missing[0]])
                self.assertFalse(report['git_blob_bytes_match'])
                self.assertFalse(report['api_metadata_matches'])
                self.assert_no_authority_or_effects(report)

    def test_disconnected_correct_tree_and_blobs_do_not_prove_another_commit(self):
        fixture = scenario()
        changed = with_tree(fixture, tree_entry('other.txt', fixture['blobs']['alpha.txt'][0]))
        changed['raw'] += batch(fixture['tree'], fixture['commit'])
        report = evaluate(changed)
        self.assertEqual(report['decision'], 'CAPTURE_MISMATCH')
        self.assertFalse(report['git_blob_bytes_match'])
        self.assertIn('MANIFEST_TREE_FILE_NAMES_DIFFER', report['issues'])

    def test_validly_rehashed_swapped_equal_length_blobs_fail_per_filename_binding(self):
        fixture = scenario()
        tree = b''.join(tree_entry(name, fixture['blobs'][
            'bravo.txt' if name == 'alpha.txt' else
            'alpha.txt' if name == 'bravo.txt' else name][0])
                        for name in sorted(fixture['blobs']))
        report = evaluate(with_tree(fixture, tree))
        self.assertEqual(report['decision'], 'CAPTURE_MISMATCH')
        self.assertFalse(report['git_blob_bytes_match'])
        self.assertEqual({r['filename'] for r in report['file_bindings']
                          if not r['matches_manifest']}, {'alpha.txt', 'bravo.txt'})

    def test_valid_git_hashes_still_require_manifest_size_and_sha256(self):
        for field, value in [('bytes', 7), ('sha256', '0' * 64)]:
            with self.subTest(field=field):
                fixture = scenario()
                fixture['manifest']['alpha.txt'][field] = value
                report = evaluate(fixture)
                self.assertEqual(report['decision'], 'CAPTURE_MISMATCH')
                self.assertFalse(report['git_blob_bytes_match'])
                self.assertIn('alpha.txt:GIT_BYTES_DIFFER', report['issues'])

    def test_git_only_mismatch_does_not_invalidate_matching_api_metadata_by_filename(self):
        fixture = scenario({'API_notes.txt': b'right', 'manifest.json': b'{}\n'})
        wrong = git_object('blob', b'wrong')
        tree = b''.join(tree_entry(name, wrong[0] if name == 'API_notes.txt'
                                  else fixture['blobs'][name][0])
                        for name in sorted(fixture['blobs']))
        changed = with_tree(fixture, tree)
        changed['raw'] += batch(wrong)
        report = evaluate(changed)
        self.assertFalse(report['git_blob_bytes_match'])
        self.assertTrue(report['api_metadata_matches'])
        self.assertEqual(report['api_text_differences'], [])

    def test_tree_filename_set_is_exact_and_manifest_is_not_exempt(self):
        fixture = scenario()
        for excluded, extra in [('manifest.json', None), (None, 'unexpected.txt')]:
            with self.subTest(excluded=excluded, extra=extra):
                entries = {name: obj[0] for name, obj in fixture['blobs'].items()
                           if name != excluded}
                if extra:
                    entries[extra] = fixture['blobs']['alpha.txt'][0]
                changed = with_tree(fixture, b''.join(
                    tree_entry(name, oid) for name, oid in sorted(entries.items())))
                report = evaluate(changed)
                self.assertFalse(report['git_blob_bytes_match'])
                self.assertIn('MANIFEST_TREE_FILE_NAMES_DIFFER', report['issues'])

    def test_duplicate_unsorted_or_unsupported_tree_entries_are_rejected(self):
        fixture = scenario()
        oid = fixture['blobs']['alpha.txt'][0]
        invalid = [
            tree_entry('same.txt', oid) * 2,
            tree_entry('z.txt', oid) + tree_entry('a.txt', oid),
            *(tree_entry('entry', oid, mode) for mode in
              (b'120000', b'40000', b'160000', b'0100644')),
            tree_entry(b'dir/file', oid), tree_entry(b'..', oid),
            tree_entry(b'\xff', oid), tree_entry('short.txt', oid)[:-1],
        ]
        for raw_tree in invalid:
            with self.subTest(raw_tree=raw_tree), self.assertRaises(ValueError):
                evaluate(with_tree(fixture, raw_tree))

    def test_regular_executable_mode_remains_a_regular_blob(self):
        fixture = scenario()
        changed = with_tree(fixture, b''.join(
            tree_entry(name, obj[0], b'100755')
            for name, obj in sorted(fixture['blobs'].items())))
        self.assertEqual(evaluate(changed)['decision'], 'GIT_BLOBS_MATCH_MANIFEST')

    def test_commit_message_tree_text_cannot_redirect_the_root(self):
        fixture = scenario()
        changed = with_tree(fixture, fixture['tree'][2],
                            b'Message\n\ntree ' + b'0' * 40 + b'\n')
        self.assertEqual(evaluate(changed)['decision'], 'GIT_BLOBS_MATCH_MANIFEST')
        invalid_headers = [
            b'author Example\n\nMessage\ntree ' + fixture['tree'][0].encode() + b'\n',
            b'tree ' + fixture['tree'][0].encode() + b'\ntree '
            + fixture['tree'][0].encode() + b'\n\nMessage\n',
            b'tree ' + fixture['tree'][0].encode(),
        ]
        for content in invalid_headers:
            with self.subTest(content=content), self.assertRaises(ValueError):
                changed = deepcopy(fixture)
                commit = git_object('commit', content)
                changed.update(raw=fixture['raw'] + batch(commit), revision=commit[0])
                changed['api']['history'][0]['version'] = commit[0]
                evaluate(changed)

    def test_requested_commit_must_have_commit_type(self):
        fixture = scenario()
        fixture['revision'] = fixture['blobs']['alpha.txt'][0]
        fixture['api']['history'][0]['version'] = fixture['revision']
        with self.assertRaises(ValueError):
            evaluate(fixture)

    def test_tampered_batch_hash_size_terminator_and_trailing_records_are_rejected(self):
        fixture = scenario()
        blob = git_object('blob', b'payload')
        record = batch(blob)
        bad_oid = b'0' * 40 + record[40:]
        bad_size = record.replace(b' blob 7\n', b' blob 8\n', 1)
        invalid = [bad_oid, bad_size, record[:-1], fixture['raw'] + b'garbage\n',
                   fixture['raw'] + b'\n', fixture['raw'] + batch(blob, blob),
                   b'0' * 40 + b' missing\n',
                   b'0' * 40 + b' blob ' + b'9' * 30 + b'\n']
        for raw in invalid:
            with self.subTest(raw=raw[:100]), self.assertRaises(ValueError):
                tool.check(fixture['manifest'], fixture['api'], raw, TARGET,
                           fixture['revision'])

    def test_byte_object_and_file_count_budgets_are_enforced(self):
        fixture = scenario()
        with patch.object(tool, 'LIMIT', len(fixture['raw']) - 1):
            with self.assertRaises(ValueError):
                evaluate(fixture)
        many = [git_object('blob', str(i).encode()) for i in range(1025)]
        with self.assertRaises(ValueError):
            tool.check(fixture['manifest'], fixture['api'], batch(*many),
                       TARGET, fixture['revision'])
        files = {'file%03d.txt' % i: b'' for i in range(100)}
        at_limit = scenario(files)
        self.assertEqual(evaluate(at_limit)['decision'], 'GIT_BLOBS_MATCH_MANIFEST')
        too_many = scenario(dict(files, extra=b''))
        with self.assertRaises(ValueError):
            evaluate(too_many)
        entries = at_limit['tree'][2] + tree_entry('zzz.txt', at_limit['blobs']['file000.txt'][0])
        with self.assertRaises(ValueError):
            evaluate(with_tree(at_limit, entries))

    def test_manifest_schema_refuses_ambiguous_types_hashes_and_names(self):
        fixture = scenario({'manifest.json': b'{}', 'one.txt': b'x'})
        invalid_entries = [
            {'bytes': True, 'sha256': hashlib.sha256(b'x').hexdigest()},
            {'bytes': -1, 'sha256': '0' * 64},
            {'bytes': 1.0, 'sha256': '0' * 64},
            {'bytes': '1', 'sha256': '0' * 64},
            {'bytes': 1, 'sha256': 'A' * 64},
            {'bytes': 1, 'sha256': 'g' * 64},
            {'bytes': 1, 'sha256': '0' * 63},
            {'bytes': 1, 'sha256': '0' * 64, 'extra': True},
        ]
        for entry in invalid_entries:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                changed = deepcopy(fixture)
                changed['manifest']['one.txt'] = entry
                evaluate(changed)
        for name in ['', '.', '..', 'a/b', 'a\\b', '\0name', '\u0085name', '\ud800', 'x' * 256]:
            with self.subTest(name=repr(name)), self.assertRaises(ValueError):
                tool.check({name: {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}},
                           fixture['api'], fixture['raw'], TARGET, fixture['revision'])
        with self.assertRaises(ValueError):
            tool.check({}, fixture['api'], fixture['raw'], TARGET, fixture['revision'])

    def test_api_text_is_compared_once_without_escape_unicode_or_newline_normalization(self):
        samples = [
            (b'literal \\u0080\n', 'literal \\^@\n'),
            ('é\n'.encode(), 'e\u0301\n'),
            (b'line\r\n', 'line\n'),
        ]
        for expected, api_text in samples:
            with self.subTest(expected=expected):
                fixture = scenario({'manifest.json': b'{}\n', 'patch.diff': expected})
                fixture['api']['files']['patch.diff']['content'] = api_text
                report = evaluate(fixture)
                self.assertEqual(report['decision'], 'GIT_BLOBS_MATCH_API_TEXT_DIFFERS')
                self.assertTrue(report['git_blob_bytes_match'])
                self.assertTrue(report['api_metadata_matches'])
                self.assertEqual(report['api_text_differences'][0]['filename'], 'patch.diff')
                self.assert_no_authority_or_effects(report)

    def test_truncation_missing_text_and_unsupported_encoding_are_incomplete(self):
        for mode in ('truncated', 'missing', 'encoding'):
            with self.subTest(mode=mode):
                fixture = scenario()
                item = fixture['api']['files']['alpha.txt']
                if mode == 'truncated':
                    item.update(truncated=True, content='a')
                elif mode == 'missing':
                    del item['content']
                else:
                    item['encoding'] = 'base64'
                report = evaluate(fixture)
                self.assertEqual(report['decision'], 'GIT_BLOBS_MATCH_API_TEXT_INCOMPLETE')
                self.assertEqual(report['api_text_incomplete'], ['alpha.txt'])
                self.assertEqual(report['api_text_differences'], [])
                self.assertTrue(report['git_blob_bytes_match'])
                self.assert_no_authority_or_effects(report)

    def test_api_revision_identity_names_and_per_file_metadata_must_match(self):
        mutations = [
            lambda a: a.update(id='b' * 32),
            lambda a: a.update(html_url=TARGET + '/wrong'),
            lambda a: a['owner'].update(login='another'),
            lambda a: a.update(history=[]),
            lambda a: a.update(history=[{'version': 'b' * 40},
                                        {'version': a['history'][0]['version']}]),
            lambda a: a['files'].pop('manifest.json'),
            lambda a: a['files'].update(extra=deepcopy(a['files']['alpha.txt'])),
            lambda a: a['files']['alpha.txt'].update(filename='other.txt'),
            lambda a: a['files']['alpha.txt'].update(size=True),
        ]
        for change in mutations:
            with self.subTest(change=change):
                fixture = scenario()
                change(fixture['api'])
                report = evaluate(fixture)
                self.assertEqual(report['decision'], 'CAPTURE_MISMATCH')
                self.assertFalse(report['api_metadata_matches'])
                self.assertTrue(report['git_blob_bytes_match'])
                self.assert_no_authority_or_effects(report)

    def test_invalid_api_text_metadata_is_refused_instead_of_coerced(self):
        for entry in [None, {'truncated': 'false'}, {'truncated': False, 'content': 1},
                      {'truncated': False, 'encoding': True},
                      {'truncated': False, 'content': '\ud800'}]:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                fixture = scenario()
                fixture['api']['files']['alpha.txt'] = entry
                evaluate(fixture)
        for target in [None, True, 'http://' + TARGET[8:], TARGET + '?x=1',
                       TARGET + '#' + 'a', TARGET + '/' + 'a' * 40]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                fixture = scenario()
                tool.check(fixture['manifest'], fixture['api'], fixture['raw'],
                           target, fixture['revision'])


class CLITests(unittest.TestCase):
    def inputs(self, directory, fixture=None):
        fixture = scenario() if fixture is None else fixture
        payloads = {'manifest': json.dumps(fixture['manifest'], indent=2).encode() + b'\n',
                    'api': b'\n' + json.dumps(fixture['api'], ensure_ascii=True).encode() + b'\n',
                    'objects': fixture['raw']}
        for name, content in payloads.items():
            (directory / name).write_bytes(content)
        args = ['--gist', TARGET, '--revision', fixture['revision']]
        args += [arg for name in payloads for arg in ('--' + name, str(directory / name))]
        return args, payloads

    def run_main(self, args):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                code = tool.main(args)
        text = output.getvalue()
        return code, json.loads(text) if text else None, errors.getvalue()

    def test_cli_retains_exact_inputs_and_does_not_execute_or_fetch(self):
        fixture = scenario({'manifest.json': b'{}\n',
                            'script.py': b'raise RuntimeError("must not execute")\n'})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args, payloads = self.inputs(root, fixture)
            with patch('subprocess.Popen', side_effect=AssertionError('unexpected process')):
                with patch('socket.create_connection', side_effect=AssertionError('unexpected fetch')):
                    code, report, _ = self.run_main(args + ['--out', str(root / 'result')])
            self.assertEqual(code, 0)
            self.assertEqual(report['decision'], 'GIT_BLOBS_MATCH_MANIFEST')
            for name, content in payloads.items():
                retained = root / 'result' / (name + '.original')
                self.assertEqual(retained.read_bytes(), content)
                self.assertEqual(report['sha256'][retained.name],
                                 hashlib.sha256(content).hexdigest())
            self.assertEqual(json.loads((root / 'result/report.json').read_text()), report)
            GistReadbackTests.assert_no_authority_or_effects(self, report)

    def test_existing_and_symlinked_output_directories_remain_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args, payloads = self.inputs(root)
            old = root / 'existing'
            old.mkdir()
            sentinel = old / 'report.json'
            sentinel.write_bytes(b'keep original evidence\n')
            destinations = [old]
            if hasattr(os, 'symlink'):
                linked = root / 'linked'
                try:
                    linked.symlink_to(old, target_is_directory=True)
                    destinations.append(linked)
                except OSError:
                    pass
            for destination in destinations:
                with self.subTest(destination=destination):
                    code, report, _ = self.run_main(args + ['--out', str(destination)])
                    self.assertEqual(code, 2)
                    self.assertIsNone(report)
                    self.assertEqual(sentinel.read_bytes(), b'keep original evidence\n')
                    self.assertEqual(list(old.iterdir()), [sentinel])
                    for name, content in payloads.items():
                        self.assertEqual((root / name).read_bytes(), content)

    def test_invalid_json_and_surrogates_preserve_the_original_diagnostic_capture(self):
        for kind in ('duplicate-manifest', 'duplicate-api', 'nonfinite-api',
                     'invalid-utf8', 'surrogate-api'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                args, _ = self.inputs(root)
                name = 'api' if 'api' in kind else 'manifest'
                original = (root / name).read_bytes().lstrip()
                if kind == 'duplicate-manifest':
                    entry = json.dumps(scenario()['manifest']['alpha.txt']).encode()
                    bad = b'{"alpha.txt":' + entry + b',' + original[1:]
                elif kind == 'duplicate-api':
                    bad = b'{"id":"' + GIST_ID.encode() + b'",' + original[1:]
                elif kind == 'nonfinite-api':
                    bad = b'{"uninterpreted":NaN,' + original[1:]
                elif kind == 'surrogate-api':
                    fixture = scenario()
                    fixture['api']['files']['alpha.txt']['content'] = '\ud800'
                    bad = json.dumps(fixture['api']).encode()
                else:
                    bad = b'\xff'
                (root / name).write_bytes(bad)
                code, report, _ = self.run_main(args + ['--out', str(root / 'result')])
                self.assertEqual(code, 2)
                self.assertEqual(report['decision'], 'INVALID_CAPTURE')
                self.assertIn('error', report)
                self.assertEqual((root / 'result' / (name + '.original')).read_bytes(), bad)
                GistReadbackTests.assert_no_authority_or_effects(self, report)

    def test_oversized_input_is_not_retained_as_a_complete_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args, _ = self.inputs(root)
            (root / 'objects').write_bytes(b'x' * 4097)
            with patch.object(tool, 'LIMIT', 4096):
                code, report, _ = self.run_main(args + ['--out', str(root / 'result')])
            self.assertEqual(code, 2)
            self.assertEqual(report['decision'], 'INVALID_CAPTURE')
            self.assertFalse((root / 'result/objects.original').exists())
            self.assertNotIn('objects.original', report['sha256'])


if __name__ == '__main__':
    unittest.main()
