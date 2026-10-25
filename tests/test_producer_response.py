"""Real P1 records must retain their limits through the existing B1/B2 plans."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools import consume_producer_evidence as consumer


class ProducerResponseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = consumer.BRIDGE / 'fixtures/p1-40138087345'
        self.expected = '6d366be37ad56e97a371b9a6277cb800c5d1b169ee9481e67fbb94062e1fce82'
        self.bundle = consumer.load_bundle(self.fixture, self.expected)
        self.context = consumer.base.read_json(consumer.BRIDGE / 'review-context.json')

    def plan(self, wrapper=None):
        wrapper = wrapper or consumer.make_wrapper(self.bundle, self.context)
        base = consumer.base
        previous = base.result(wrapper['packet'], base.reference(base.facts(wrapper['packet'])))
        profile = consumer.profile
        return profile.result(wrapper, previous, profile.reference(profile.facts(wrapper, previous)))

    def modified(self, mutate):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name) / 'bundle'
        shutil.copytree(self.fixture, directory)
        mutate(directory)
        manifest = consumer.base.read_json(directory / 'manifest.json')
        for name in manifest['files']:
            data = (directory / name).read_bytes()
            manifest['files'][name] = {'bytes': len(data), 'sha256': consumer.sha(data)}
        (directory / 'manifest.json').write_bytes(consumer.base.encoded(manifest))
        return directory, consumer.sha((directory / 'manifest.json').read_bytes())

    def change_json(self, directory, name, change):
        value = consumer.base.read_json(directory / name)
        change(value)
        (directory / name).write_bytes(consumer.base.encoded(value))

    def test_real_saved_bundle_keeps_all_three_record_bytes_and_reported_counts(self):
        self.assertEqual(len(self.bundle['records']), 3)
        appendix = self.bundle['appendix']
        self.assertEqual((appendix['selected_cases'], appendix['selected_batches'], len(appendix['receipts'])), (50, 7, 14))
        self.assertEqual(appendix['complete_reader_suite_count'], 82)
        for record, phase in zip(self.bundle['records'], consumer.PHASES):
            self.assertEqual(record, consumer.base.read_json(self.fixture / (phase + '.evidence.json')))
            self.assertEqual(record['execution']['phase'], phase)
            self.assertEqual(record['execution']['outcome'], 'pass')
            self.assertEqual(record['execution']['comparison'], 'not_compared')
            self.assertIsNone(record['identities']['source_commit'])
            self.assertIsNone(record['identities']['candidate_commit'])

    def test_local_context_and_records_do_not_establish_a_repository_profile_or_posting_permission(self):
        result = self.plan()
        self.assertEqual(result['decision'], 'NEEDS_CONTEXT')
        self.assertEqual(result['reason'], 'POLICY_DISCOVERY')
        self.assertEqual(result['base_result']['decision'], 'EXTERNAL_REQUIREMENT_UNSATISFIED')
        self.assertEqual(result['effect'], 'none')
        self.assertEqual(result['input']['packet']['evidence'], self.bundle['records'])
        for claim in result['input']['packet']['claims']:
            self.assertEqual((claim['kind'], claim['status'], claim['tested_revision']), ('bounded_confirmation', 'observed', None))

    def test_summary_and_detail_keep_material_limits_original_failure_and_claim_statuses(self):
        planned = self.plan()
        value = consumer.response_result(self.bundle, planned)
        text = consumer.render(self.bundle, value)
        detail = consumer.profile.render(planned)
        self.assertIn('command deadline: header-host-consumer', text)
        self.assertIn('does not rerun that full reader', text)
        self.assertIn('authentication and native acceptance remain false', text)
        self.assertIn('Plan: NEEDS_CONTEXT:POLICY_DISCOVERY', text)
        self.assertEqual(sum(line.startswith('One next action:') for line in text.splitlines()), 1)
        self.assertIn('(source/appendix.json)', text)
        self.assertIn('(plan-detail.txt)', text)
        self.assertIn('(result.json)', text)
        for record in self.bundle['records']:
            self.assertIn(record['id'], detail)
            for field in ('uncertainty', 'failures', 'exclusions'):
                for item in record[field]:
                    self.assertIn(json.dumps(item), text)
                    self.assertIn(json.dumps(item), detail)
        self.assertEqual(value['producer_observations']['reported_complete_reader_suites'], 82)
        self.assertFalse(value['producer_observations']['producer_authenticated'])
        self.assertEqual(value['effect'], 'none')

    def test_wrong_manifest_digest_or_changed_payload_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'manifest digest'):
            consumer.load_bundle(self.fixture, '0' * 64)
        directory, expected = self.modified(lambda p: None)
        (directory / 'technical-preview.txt').write_text('replacement')
        with self.assertRaisesRegex(ValueError, 'payload size/digest'):
            consumer.load_bundle(directory, expected)

    def test_unknown_files_missing_files_and_symlinks_are_not_imported(self):
        for mutation in ('extra', 'missing', 'symlink'):
            directory, expected = self.modified(lambda p: None)
            if mutation == 'extra':
                (directory / 'unexpected.json').write_text('{}')
            elif mutation == 'missing':
                (directory / 'saved_replay.evidence.json').unlink()
            else:
                file = directory / 'technical-preview.txt'
                file.unlink()
                file.symlink_to(self.fixture / 'technical-preview.txt')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                consumer.load_bundle(directory, expected)

    def test_producer_authority_and_contract_substitution_are_refused(self):
        for key, value in [('native_acceptance', True), ('producer_authenticated', 0), ('contract_schema_sha256', '0' * 64)]:
            directory, expected = self.modified(lambda p: self.change_json(p, 'manifest.json', lambda x: x.update({key: value})))
            with self.subTest(key=key), self.assertRaises(ValueError):
                consumer.load_bundle(directory, expected)

    def test_reported_git_identifiers_and_full_suite_phase_cannot_replace_the_reference_only_contract(self):
        for change in (lambda r: r['identities'].update(source_commit='4548857e918d7c11d0e7fdf1138a78ae2d61c90a'),
                       lambda r: r['execution'].update(phase='full_suite'),
                       lambda r: r['execution'].update(comparison='base_and_candidate')):
            directory, expected = self.modified(lambda p: self.change_json(p, 'native_execution.evidence.json', change))
            with self.assertRaises(ValueError):
                consumer.load_bundle(directory, expected)

    def test_original_failure_and_each_record_material_limits_are_required(self):
        directory, expected = self.modified(lambda p: self.change_json(p, 'appendix.json', lambda x: x.pop('producer_first_failure')))
        with self.assertRaises((ValueError, KeyError)):
            consumer.load_bundle(directory, expected)
        for field in ('uncertainty', 'failures', 'exclusions'):
            directory, expected = self.modified(lambda p: self.change_json(p, 'native_execution.evidence.json', lambda x: x.update({field: []})))
            with self.subTest(field=field), self.assertRaises(ValueError):
                consumer.load_bundle(directory, expected)

    def test_case_domain_count_types_and_replay_parents_are_not_coerced(self):
        for change in (lambda a: a.update(selected_cases=True), lambda a: a['rows'].pop(),
                       lambda a: a['receipts'][1].update(original_receipt_sha256='sha256:' + '0' * 64)):
            directory, expected = self.modified(lambda p: self.change_json(p, 'appendix.json', change))
            with self.assertRaises(ValueError):
                consumer.load_bundle(directory, expected)

    def test_duplicate_json_keys_are_refused_after_transport_hash_validation(self):
        def duplicate(directory):
            path = directory / 'native_execution.evidence.json'
            text = path.read_text()
            path.write_text('{"schema":"gooo/contribution-evidence/v1",' + text[1:])
        directory, expected = self.modified(duplicate)
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            consumer.load_bundle(directory, expected)

    def test_supplied_context_cannot_replace_records_or_change_repository(self):
        for change in (lambda w: w['packet']['evidence'].append(self.bundle['records'][0]),
                       lambda w: w['packet'].update(repository='hashicorp/hcl'),
                       lambda w: w['packet']['conversation'].update(snapshot_id='different')):
            context = deepcopy(self.context)
            change(context)
            with self.assertRaises(ValueError):
                consumer.make_wrapper(self.bundle, context)

    def test_fix_revision_and_all_tests_overstatements_remain_refused_by_b1_b2(self):
        wrapper = consumer.make_wrapper(self.bundle, self.context)
        wrapper['packet']['claims'][0].update(kind='original_finding_fixed', status='resolved')
        self.assertEqual(self.plan(wrapper)['reason'], 'COMPARISON_UNSUPPORTED')
        wrapper = consumer.make_wrapper(self.bundle, self.context)
        wrapper['packet']['claims'][0]['tested_revision'] = self.bundle['appendix']['reported_run']['tested_commit']
        self.assertEqual(self.plan(wrapper)['reason'], 'EVIDENCE_BINDING')
        wrapper = consumer.make_wrapper(self.bundle, self.context)
        next(a for a in wrapper['assertions'] if a['field'] == 'overall_test_status')['value'] = 'all_passed'
        self.assertEqual(self.plan(wrapper)['reason'], 'CLAIM_OVERSTATEMENT')

    def test_result_or_presentation_substitution_does_not_upgrade_the_producer(self):
        value = consumer.response_result(self.bundle, self.plan())
        for change in (lambda r: r['producer_observations'].update(native_acceptance=True),
                       lambda r: r['producer_observations'].update(reported_complete_reader_suites=50),
                       lambda r: r.update(effect='post'),
                       lambda r: r['planning'].update(decision='BOUNDED_DRAFT_READY')):
            copied = deepcopy(value)
            change(copied)
            with self.assertRaises(ValueError):
                consumer.render(self.bundle, copied)

    def test_local_handoff_cannot_satisfy_the_ci_publication_precondition(self):
        provenance = consumer.base.read_json(consumer.BRIDGE / 'provenance.json')
        provenance['status'] = 'LOCAL_HANDOFF_REVIEW_PENDING_P1_ACCEPTANCE_AND_PUBLIC_ASSET'
        with self.assertRaisesRegex(ValueError, 'not ready'):
            consumer.published_source(provenance)


if __name__ == '__main__':
    unittest.main()
