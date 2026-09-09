"""Portable wall-budget tests; no simulator or hardware is launched."""
import json
import io
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.test_budget import supervise, wall_limit, MILESTONE_TARGETS


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
                self.assertEqual(record['wall_limit_seconds'], 300)

    def test_timeout_reaps_real_host_process_and_preserves_partial_output(self):
        # Charge 286 seconds of prior work, leaving two seconds before the
        # 288-second execution deadline and twelve seconds for cleanup.
        marker = self.root / 'orphan.txt'
        child = f"import time;from pathlib import Path;time.sleep(3);Path({str(marker)!r}).write_text('orphan')"
        parent = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);print('partial',flush=True);time.sleep(30)"
        with patch('n2m.test_budget.time', Mock(monotonic=Mock(side_effect=[0, 286, 288.1, 288.2, 288.3, 288.4]))):
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
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 300), (b'partial', None)]
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

    def test_preparation_and_launch_consume_the_execution_budget(self):
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (b'done', b'')
        with patch('n2m.test_budget.subprocess.Popen', return_value=process), \
             patch('n2m.test_budget.time', Mock(monotonic=Mock(side_effect=[10, 30, 31]))):
            code, _ = supervise(['worker'], self.root, 'preparation')
        self.assertEqual(code, 0)
        process.communicate.assert_called_once_with(timeout=268)

    def test_cleanup_timeouts_shrink_to_absolute_deadline(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 288),
                                          subprocess.TimeoutExpired('pipe', .5)]
        clock = Mock(monotonic=Mock(side_effect=[0, 1, 299, 299.5, 299.8, 300]))
        with patch('n2m.test_budget.subprocess.Popen', return_value=process), \
             patch('n2m.test_budget.subprocess.run', return_value=Mock(returncode=0)) as cleanup, \
             patch('n2m.test_budget.os.killpg', create=True), \
             patch('n2m.test_budget.time', clock):
            code, text = supervise(['worker'], self.root, 'shrinking')
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)['cleanup_complete'])
        if sys.platform == 'win32':
            self.assertEqual(cleanup.call_args.kwargs['timeout'], 1)
            self.assertEqual(process.communicate.call_args.kwargs['timeout'], .5)
            self.assertAlmostEqual(process.wait.call_args.kwargs['timeout'], .2)

    def test_reap_timeout_is_bounded_even_after_successful_tree_kill(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 300),
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
        process.communicate.side_effect = subprocess.TimeoutExpired('worker', 300, output=b'partial')
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

    def test_only_exact_authorized_names_receive_milestone_budget(self):
        self.assertEqual(MILESTONE_TARGETS, {'mooneye-reg-f', 'mooneye-corrupt', 'mooneye-missing'})
        with patch.dict('os.environ', {'N2M_TEST_WALL_SECONDS': '99999'}):
            for name in MILESTONE_TARGETS:
                self.assertEqual(wall_limit(name), 1500)
            for name in (None, '', 'ordinary', 'mooneye-reg-f-extra', 'MOONEYE-REG-F', 'mooneye', 'mooneye-missing '):
                self.assertEqual(wall_limit(name), 300)

    def test_selected_deadline_includes_preparation_and_overwrites_environment(self):
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (b'done', b'')
        fixed = datetime(2026, 9, 9, tzinfo=timezone.utc)
        with patch('n2m.test_budget.subprocess.Popen', return_value=process) as launch, \
             patch('n2m.test_budget.time', Mock(monotonic=Mock(side_effect=[10, 30, 31]))), \
             patch('n2m.test_budget.datetime', Mock(now=Mock(return_value=fixed))), \
             patch.dict('os.environ', {'N2M_TEST_EXECUTION_DEADLINE': '9999999999'}):
            code, _ = supervise(['worker'], self.root, 'selected', target='mooneye-reg-f')
        self.assertEqual(code, 0)
        process.communicate.assert_called_once_with(timeout=1468)
        self.assertEqual(float(launch.call_args.kwargs['env']['N2M_TEST_EXECUTION_DEADLINE']), fixed.timestamp()+1488)
        record = json.loads(next((self.root/'workdir/builds/selected/wall-budget').glob('*.json')).read_text())
        self.assertEqual((record['target'], record['wall_limit_seconds'], record['execution_limit_seconds']),
                         ('mooneye-reg-f', 1500, 1488))

    def test_selected_cleanup_still_shrinks_to_absolute_deadline(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 1488),
                                          subprocess.TimeoutExpired('pipe', .5)]
        clock = Mock(monotonic=Mock(side_effect=[0, 1, 1499, 1499.5, 1499.8, 1500]))
        with patch('n2m.test_budget.subprocess.Popen', return_value=process), \
             patch('n2m.test_budget.subprocess.run', return_value=Mock(returncode=0)) as cleanup, \
             patch('n2m.test_budget.os.killpg', create=True), \
             patch('n2m.test_budget.time', clock):
            code, text = supervise(['worker'], self.root, 'selected-expiry', target='mooneye-missing')
        self.assertEqual(code, 1)
        self.assertIn('1500 seconds total', json.loads(text)['error'])
        self.assertFalse(json.loads(text)['cleanup_complete'])
        if sys.platform == 'win32':
            self.assertEqual(cleanup.call_args.kwargs['timeout'], 1)
            self.assertEqual(process.communicate.call_args.kwargs['timeout'], .5)
            self.assertAlmostEqual(process.wait.call_args.kwargs['timeout'], .2)

    def test_public_supervisor_binds_budget_to_parsed_target(self):
        from n2m.test_budget import main
        with patch('sys.argv', ['tools/build.py', 'sim', 'test', 'mooneye-corrupt', '--tag', 'selected']), \
             patch('n2m.test_budget.supervise', return_value=(0, '{}')) as run, \
             patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(), 0)
        self.assertEqual(run.call_args.kwargs, {'target': 'mooneye-corrupt'})
        self.assertIn('mooneye-corrupt', run.call_args.args[0])

    def test_registry_and_validator_share_exact_budget(self):
        from n2m.simulation import load_target
        root = Path(__file__).resolve().parents[3]
        targets = json.loads((root/'src/dv/builder/targets.json').read_text())
        long_targets = {name for name, row in targets.items() if row.get('timeout_seconds', 60) > 300}
        self.assertEqual(long_targets, MILESTONE_TARGETS)
        self.assertTrue(all(type(row.get('timeout_seconds', 60)) is int and
                            1 <= row.get('timeout_seconds', 60) <= wall_limit(name) for name, row in targets.items()))
        for name in MILESTONE_TARGETS:
            self.assertEqual(load_target(root, name)[0]['timeout_seconds'], 1500)
            with patch('n2m.simulation.json.loads', return_value={name: {**targets[name], 'timeout_seconds': 1501}}):
                with self.assertRaisesRegex(ValueError, '1..1500'):
                    load_target(root, name)
        ordinary = next(name for name in targets if name not in MILESTONE_TARGETS)
        with patch('n2m.simulation.json.loads', return_value={ordinary: {**targets[ordinary], 'timeout_seconds': 301}}):
            with self.assertRaisesRegex(ValueError, '1..300'):
                load_target(root, ordinary)

    def test_worker_stderr_does_not_corrupt_json_stdout(self):
        with patch('sys.stderr', new_callable=io.StringIO) as errors:
            code, text = supervise([sys.executable, '-c',
                'import sys;print("{\\"status\\":\\"FAIL\\"}");print("diagnostic",file=sys.stderr)'],
                self.root, 'json-output')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)['status'], 'FAIL')
        self.assertEqual(errors.getvalue().strip(), 'diagnostic')
        record = json.loads(next((self.root/'workdir/builds/json-output/wall-budget').glob('*.json')).read_text())
        self.assertEqual((self.root/record['stderr']).read_text().strip(), 'diagnostic')


if __name__ == '__main__':
    unittest.main()
