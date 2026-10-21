"""Reject incomplete or malformed native observations before Gooo comparison."""
import json
import unittest

from tools.verify_bubbles_delete import CORRECTED, IDS, observations


class BubblesDeleteEvidenceTests(unittest.TestCase):
    def events(self, failures):
        events = []
        for id in sorted(IDS):
            row = {'id': id, 'input': {'text': 'a\nb', 'byte_column': 0},
                   'rune_column': 0, 'expected': '\nb', 'actual': 'b' if id in failures else '\nb'}
            name = 'TestBridgeForwardDelete/' + id
            events += [{'Test': name, 'Action': 'output', 'Output': 'WITNESS ' + json.dumps(row)},
                       {'Test': name, 'Action': 'fail' if id in failures else 'pass'}]
        return events

    def parse(self, events, failures=CORRECTED):
        return observations('\n'.join(json.dumps(e) for e in events), failures)

    def test_expected_before_and_after_failure_sets(self):
        self.assertEqual(set(self.parse(self.events(CORRECTED))), IDS)
        self.assertEqual(set(self.parse(self.events(set()), set())), IDS)
        with self.assertRaises(ValueError):
            self.parse(self.events(set()))

    def test_missing_duplicate_and_skipped_evidence_is_rejected(self):
        for mutation in ('missing-row', 'missing-terminal', 'duplicate-row', 'duplicate-terminal', 'skip'):
            events = self.events(CORRECTED)
            if mutation == 'missing-row':
                del events[0]
            elif mutation == 'missing-terminal':
                del events[1]
            elif mutation == 'duplicate-row':
                events.append(events[0])
            elif mutation == 'duplicate-terminal':
                events.append(events[1])
            else:
                events[1]['Action'] = 'skip'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.parse(events)

    def test_cursor_types_utf8_boundary_and_first_line_are_checked(self):
        for mutation in ('boolean-column', 'inside-rune', 'next-line', 'wrong-rune-column', 'non-text-output'):
            events = self.events(CORRECTED)
            row = json.loads(events[0]['Output'].split('WITNESS ', 1)[1])
            if mutation == 'boolean-column':
                row['input']['byte_column'] = False
            elif mutation == 'inside-rune':
                row['input'] = {'text': '界', 'byte_column': 1}
            elif mutation == 'next-line':
                row['input']['byte_column'] = 2
                row['rune_column'] = 2
            elif mutation == 'wrong-rune-column':
                row['rune_column'] = 1
            else:
                row['actual'] = None
            events[0]['Output'] = 'WITNESS ' + json.dumps(row)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.parse(events)
