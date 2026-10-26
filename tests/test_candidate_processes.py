"""Bounded collection retains bytes and stops its owned POSIX process group."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from tools import check_candidates as collector


CHILD_CODE = r'''
import os
from pathlib import Path
import sys
import time

root = Path(sys.argv[1])
(root / 'child.pid').write_text(str(os.getpid()))
os.write(1, b'child-out\x00\xff\n')
os.write(2, b'child-err\x00\xfe\n')
(root / 'ready').write_text('ready')
time.sleep(20)
'''

PARENT_CODE = r'''
import os
from pathlib import Path
import sys
import time

root = Path(sys.argv[1])
(root / 'leader.pid').write_text(str(os.getpid()))
(root / 'group.pid').write_text(str(os.getpgrp()))
# Inherit both output handles, as an ordinary compiler/tool subprocess would.
if os.fork() == 0:
    os.execv(sys.executable, [sys.executable, '-c', sys.argv[3], str(root)])
deadline = time.monotonic() + 10
while not (root / 'ready').exists():
    if time.monotonic() >= deadline:
        raise SystemExit('descendant did not become ready')
    time.sleep(0.01)
os.write(1, b'parent-out\x00\n')
os.write(2, b'parent-err\xff\n')
if sys.argv[2] == 'timeout':
    time.sleep(20)
'''

PROBE_STDOUT = b'child-out\x00\xff\nparent-out\x00\n'
PROBE_STDERR = b'child-err\x00\xfe\nparent-err\xff\n'


class CandidateProcessTests(unittest.TestCase):
    def test_binary_input_output_and_nonzero_exit(self):
        payload = b'input\x00\xff\r\n'
        script = ("import os, sys; data = sys.stdin.buffer.read(); "
                  "os.write(1, b'out\\x00' + data); "
                  "os.write(2, b'err\\xff\\n'); sys.exit(7)")
        command = [sys.executable, '-c', script]
        result = collector._run_bounded(command, timeout=5, input=payload)
        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.args, command)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, b'out\x00' + payload)
        self.assertEqual(result.stderr, b'err\xff\n')

    def test_cleanup_timeout_retains_output_and_both_timeout_flags(self):
        command = ['mocked-tool']
        output, diagnostics = b'partial\x00\xff', b'diagnostic\x00\xfe'
        process = Mock(pid=123456789, returncode=None)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired(command, 1),
                                    subprocess.TimeoutExpired(command, 5)]

        def start_process(args, **kwargs):
            self.assertEqual(args, command)
            kwargs['stdout'].write(output)
            kwargs['stderr'].write(diagnostics)
            return process

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = {}
            with patch.object(collector.subprocess, 'Popen', side_effect=start_process), \
                    patch.object(collector.os, 'killpg', create=True), \
                    self.assertRaises(subprocess.TimeoutExpired) as caught:
                collector.captured_run(command, root, 'stdout', 'stderr', summary,
                                       'probe', timeout=1)
            self.assertEqual(caught.exception.output, output)
            self.assertEqual(caught.exception.stderr, diagnostics)
            self.assertTrue(caught.exception.cleanup_timed_out)
            self.assertEqual((root / 'stdout').read_bytes(), output)
            self.assertEqual((root / 'stderr').read_bytes(), diagnostics)
            self.assertTrue(summary['probe_timed_out'])
            self.assertTrue(summary['probe_cleanup_timed_out'])
            self.assertNotIn('probe_exit_code', summary)

    @staticmethod
    def _pid(root, name):
        try:
            return int((root / name).read_text())
        except (FileNotFoundError, ValueError):
            return None

    @classmethod
    def _cleanup_probe(cls, root):
        leader = cls._pid(root, 'leader.pid')
        group = cls._pid(root, 'group.pid')
        child = cls._pid(root, 'child.pid')
        if group == leader and group is not None and group > 1 \
                and group != os.getpgrp():
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        # Also contain a regression that failed to create a separate session.
        for pid in (leader, child):
            if pid is not None and pid > 1 and pid != os.getpid():
                try:
                    if os.getpgid(pid) == group:
                        os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def _assert_descendant_stopped(self, root):
        self.assertTrue((root / 'ready').exists(), 'descendant never became ready')
        child = self._pid(root, 'child.pid')
        self.assertIsNotNone(child)
        self.assertEqual(self._pid(root, 'leader.pid'), self._pid(root, 'group.pid'))
        deadline = time.monotonic() + 3
        while True:
            status = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)],
                                    capture_output=True, timeout=1)
            state = status.stdout.decode('ascii').strip()
            self.assertIn(status.returncode, (0, 1), status.stderr)
            # An orphan may briefly remain a zombie until the OS reaps it.
            if not state or state.startswith('Z'):
                return
            if time.monotonic() >= deadline:
                self.fail('descendant is still running: {}'.format(state))
            time.sleep(0.05)

    @unittest.skipUnless(os.name == 'posix', 'requires owned POSIX process groups')
    def test_timeout_stops_descendant_and_retains_partial_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = [sys.executable, '-c', PARENT_CODE, str(root), 'timeout', CHILD_CODE]
            summary = {}
            try:
                started = time.monotonic()
                with self.assertRaises(subprocess.TimeoutExpired) as caught:
                    collector.captured_run(command, root, 'stdout', 'stderr', summary,
                                           'probe', timeout=5)
                self.assertLess(time.monotonic() - started, 10)
                self.assertEqual(caught.exception.cmd, command)
                self.assertEqual(caught.exception.timeout, 5)
                self.assertEqual(caught.exception.output, PROBE_STDOUT)
                self.assertEqual(caught.exception.stderr, PROBE_STDERR)
                self.assertEqual((root / 'stdout').read_bytes(), PROBE_STDOUT)
                self.assertEqual((root / 'stderr').read_bytes(), PROBE_STDERR)
                self.assertTrue(summary['probe_timed_out'])
                self._assert_descendant_stopped(root)
            finally:
                self._cleanup_probe(root)

    @unittest.skipUnless(os.name == 'posix', 'requires owned POSIX process groups')
    def test_normal_parent_exit_stops_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = [sys.executable, '-c', PARENT_CODE, str(root), 'normal', CHILD_CODE]
            summary = {}
            try:
                result = collector.captured_run(command, root, 'stdout', 'stderr', summary,
                                                'probe', timeout=5)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, PROBE_STDOUT)
                self.assertEqual(result.stderr, PROBE_STDERR)
                self.assertEqual((root / 'stdout').read_bytes(), PROBE_STDOUT)
                self.assertEqual((root / 'stderr').read_bytes(), PROBE_STDERR)
                self.assertEqual(summary['probe_exit_code'], 0)
                self._assert_descendant_stopped(root)
            finally:
                self._cleanup_probe(root)


if __name__ == '__main__':
    unittest.main()
