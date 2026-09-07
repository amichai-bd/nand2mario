"""Portable wall-budget tests; no simulator or hardware is launched."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.test_budget import supervise


class BudgetTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / 'workdir/builds/budget-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_success_and_failure_preserve_output_and_raw_status(self):
        for code in (0, 7):
            with self.subTest(code=code):
                actual, text = supervise([sys.executable, '-c', f'print("done");raise SystemExit({code})'], self.root, f'run{code}')
                self.assertEqual(actual, code)
                self.assertEqual(text.strip(), 'done')
                record = json.loads(next((self.root/f'workdir/builds/run{code}/wall-budget').glob('*.json')).read_text())
                self.assertEqual(record['raw_exit_code'], code)
                self.assertEqual(record['wall_limit_seconds'], 600)

    def test_timeout_reaps_real_host_process_and_preserves_partial_output(self):
        # Charge 598 seconds of prior work; exercise the same hard 600-second
        # budget with only two seconds of real host execution.
        marker = self.root / 'orphan.txt'
        child = f"import time;from pathlib import Path;time.sleep(3);Path({str(marker)!r}).write_text('orphan')"
        parent = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);print('partial',flush=True);time.sleep(30)"
        with patch('n2m.test_budget.time', Mock(monotonic=Mock(side_effect=[0, 598, 600.1]))):
            code, text = supervise([sys.executable, '-u', '-c', parent], self.root, 'expiry')
        time.sleep(1.5)
        self.assertFalse(marker.exists(), 'timed-out descendant survived')
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(text)['status'], 'FAIL')
        record = json.loads(next((self.root/'workdir/builds/expiry/wall-budget').glob('*.json')).read_text())
        self.assertEqual(record['status'], 'TIMEOUT')
        self.assertNotEqual(record['raw_exit_code'], 0)
        self.assertIn('partial', (self.root/record['output']).read_text())

    def test_expiry_uses_process_tree_cleanup(self):
        process = Mock(pid=123, returncode=9)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 600), (b'partial', None)]
        with patch('n2m.test_budget.subprocess.Popen', return_value=process), \
             patch('n2m.test_budget.subprocess.run') as cleanup, \
             patch('n2m.test_budget.os.killpg', create=True) as kill_group:
            cleanup.return_value.returncode = 0
            supervise(['worker'], self.root, 'tree')
            import os
            if os.name == 'nt':
                self.assertEqual(cleanup.call_args.args[0], ['taskkill', '/PID', '123', '/T', '/F'])
            else:
                kill_group.assert_called_once()
            self.assertEqual(process.communicate.call_count, 2)

    def test_invalid_tag_never_launches(self):
        with patch('n2m.test_budget.subprocess.Popen') as launch:
            with self.assertRaises(ValueError):
                supervise(['worker'], self.root, '../outside')
            launch.assert_not_called()

    def test_reap_timeout_is_bounded_even_after_successful_tree_kill(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 600),
                                           subprocess.TimeoutExpired('pipe', 5, output=b'last')]
        with patch('n2m.test_budget.subprocess.Popen', return_value=process), \
             patch('n2m.test_budget.subprocess.run', return_value=Mock(returncode=0)), \
             patch('n2m.test_budget.os.killpg', create=True):
            code, text = supervise(['worker'], self.root, 'reap-failure')
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)['cleanup_complete'])
        self.assertEqual(process.communicate.call_args.kwargs['timeout'], 5)
        process.wait.assert_called_once_with(timeout=2)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows taskkill failure')
    def test_failed_tree_cleanup_cannot_wait_forever_on_surviving_pipe(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = subprocess.TimeoutExpired('worker', 600, output=b'partial')
        process.wait.side_effect = subprocess.TimeoutExpired('worker', 2)
        with patch('n2m.test_budget.subprocess.Popen', return_value=process), \
             patch('n2m.test_budget.subprocess.run', return_value=Mock(returncode=1)) as cleanup:
            code, text = supervise(['worker'], self.root, 'cleanup-failure')
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)['cleanup_complete'])
        self.assertEqual(cleanup.call_args.kwargs['timeout'], 5)
        process.wait.assert_called_once_with(timeout=2)
        process.communicate.assert_called_once()
        record = json.loads(next((self.root/'workdir/builds/cleanup-failure/wall-budget').glob('*.json')).read_text())
        self.assertEqual(record['status'], 'TIMEOUT')
        self.assertIn('cleanup failed', record['cleanup_error'])
        self.assertIn('reap_error', record)
        self.assertEqual((self.root/record['output']).read_text(), 'partial')

    def test_registry_has_no_long_exception(self):
        root = Path(__file__).resolve().parents[3]
        targets = json.loads((root/'src/dv/builder/targets.json').read_text())
        self.assertTrue(all(type(row.get('timeout_seconds', 60)) is int and
                            1 <= row.get('timeout_seconds', 60) <= 600 for row in targets.values()))


if __name__ == '__main__':
    unittest.main()
