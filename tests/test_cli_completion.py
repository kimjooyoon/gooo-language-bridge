"""Reject incomplete or contradictory native completion evidence."""
from copy import deepcopy
import json
import unittest

from tools.verify_cli_completion import case_domain, observations


class CompletionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        for id, (token, completion, incomplete, args) in case_domain().items():
            path = ['sub'] if id.startswith('child/') else ['sub', 'nested'] if id.startswith('nested/') else []
            expected = ('PENDING:' + token if completion else 'REJECT') if incomplete else 'CONSUMED'
            row = {'id': id, 'input': dict(token=token, completion=completion, incomplete=incomplete),
                   'argv': ['app'] + path + ['value'] + args + (['--generate-shell-completion'] if completion else []),
                   'completion_args': (['value', token] if incomplete else ['value']) if completion else None,
                   'action': not completion and not incomplete, 'completed': completion,
                   'error': not completion and incomplete, 'expected': expected, 'actual': expected}
            self.events.extend([
                {'Action': 'output', 'Test': 'TestBridgeCompletionIntent/' + id,
                 'Output': 'WITNESS ' + json.dumps(row) + '\n'},
                {'Action': 'pass', 'Test': 'TestBridgeCompletionIntent/' + id}])

    def encode(self, events):
        return '\n'.join(json.dumps(e) for e in events)

    def test_missing_duplicate_and_wrong_terminal_are_rejected(self):
        self.assertEqual(len(observations(self.encode(self.events), set())), 20)
        wrong = deepcopy(self.events)
        wrong[1]['Action'] = 'skip'
        for events in (self.events[:-2], self.events + self.events[:2], wrong):
            with self.assertRaises(ValueError):
                observations(self.encode(events), set())

    def test_declared_pass_cannot_hide_lost_token_or_executed_action(self):
        for key, value in [('completion_args', ['value']), ('action', True), ('error', True)]:
            events = deepcopy(self.events)
            row = json.loads(events[0]['Output'].split('WITNESS ', 1)[1])
            row[key] = value
            events[0]['Output'] = 'WITNESS ' + json.dumps(row)
            with self.subTest(key=key), self.assertRaises(ValueError):
                observations(self.encode(events), set())

    def test_input_types_argv_and_event_identity_are_bound(self):
        for mutation in ('boolean-type', 'argv', 'label'):
            events = deepcopy(self.events)
            row = json.loads(events[0]['Output'].split('WITNESS ', 1)[1])
            if mutation == 'boolean-type':
                row['input']['completion'] = 1
            elif mutation == 'argv':
                row['argv'][-2] = '-different'
            else:
                events[0]['Test'] = 'TestBridgeCompletionIntent/wrong'
            events[0]['Output'] = 'WITNESS ' + json.dumps(row)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                observations(self.encode(events), set())


if __name__ == '__main__':
    unittest.main()
