"""A completed comparison step must not leave its owned descendants running."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from tools.compare_js import run_step


PROBE = r'''
import os
from pathlib import Path
import sys
import time

root = Path(sys.argv[1])
(root / 'leader.pid').write_text(str(os.getpid()))
(root / 'group.pid').write_text(str(os.getpgrp()))
if os.fork() == 0:
    (root / 'child.pid').write_text(str(os.getpid()))
    os.write(2, b'child-error\x00\xff\n')
    (root / 'ready').write_text('ready')
    time.sleep(20)
    os._exit(0)

deadline = time.monotonic() + 5
while not (root / 'ready').exists():
    if time.monotonic() >= deadline:
        raise SystemExit('descendant did not become ready')
    time.sleep(0.01)
os.write(1, b'[]\n')
os.write(2, b'parent-error\x00\xfe\n')
if sys.argv[2] == 'timeout':
    time.sleep(20)
else:
    raise SystemExit(int(sys.argv[2]))
'''

STDOUT = b'[]\n'
STDERR = b'child-error\x00\xff\nparent-error\x00\xfe\n'


@unittest.skipUnless(os.name == 'posix', 'requires owned POSIX process groups')
class ComparisonProcessTests(unittest.TestCase):
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
        owned = []
        for pid in (leader, child):
            if pid is not None and pid > 1 and pid != os.getpid():
                try:
                    if os.getpgid(pid) == group:
                        owned.append(pid)
                except ProcessLookupError:
                    pass
        if owned and group == leader and group != os.getpgrp():
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            # Contain the fixture even if session creation itself regresses.
            for pid in owned:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def _assert_descendant_stopped(self, root):
        self.assertTrue((root / 'ready').exists(), 'descendant never became ready')
        child = self._pid(root, 'child.pid')
        self.assertIsNotNone(child)
        self.assertEqual(self._pid(root, 'leader.pid'), self._pid(root, 'group.pid'))
        deadline = time.monotonic() + 2
        while True:
            result = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)],
                                    capture_output=True, timeout=1)
            self.assertIn(result.returncode, (0, 1), result.stderr)
            state = result.stdout.decode('ascii').strip()
            # A stopped orphan can remain a zombie until its new parent reaps it.
            if not state or state.startswith('Z'):
                return
            if time.monotonic() >= deadline:
                self.fail('descendant is still running: ' + state)
            time.sleep(0.05)

    def _check_probe(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = [sys.executable, '-c', PROBE, str(root), mode]
            steps = []
            try:
                if mode == '0':
                    result = run_step('probe', command, root, dict(os.environ),
                                      root, steps, timeout=5)
                    self.assertEqual(result, STDOUT)
                    self.assertEqual(steps[0]['exit_code'], 0)
                else:
                    error = 'timed out' if mode == 'timeout' else 'exited 3'
                    with self.assertRaisesRegex(ValueError, error):
                        run_step('probe', command, root, dict(os.environ),
                                 root, steps, timeout=5)
                    if mode == 'timeout':
                        self.assertIsNotNone(steps[0]['exit_code'])
                        self.assertNotEqual(steps[0]['exit_code'], 0)
                        self.assertIn('timed out', steps[0]['error'])
                    else:
                        self.assertEqual(steps[0]['exit_code'], 3)
                self.assertEqual((root / 'probe.stdout').read_bytes(), STDOUT)
                self.assertEqual((root / 'probe.stderr').read_bytes(), STDERR)
                self._assert_descendant_stopped(root)
            finally:
                self._cleanup_probe(root)

    def test_normal_leader_exit_stops_descendant_and_retains_output(self):
        self._check_probe('0')

    def test_nonzero_leader_exit_stops_descendant_and_retains_output(self):
        self._check_probe('3')

    def test_timeout_stops_descendant_and_retains_output(self):
        self._check_probe('timeout')


if __name__ == '__main__':
    unittest.main()
