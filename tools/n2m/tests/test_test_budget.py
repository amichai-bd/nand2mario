"""Portable wall-budget tests; no simulator or hardware is launched."""
import json
import io
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.test_budget import (supervise, wall_limit, wall_selection, declared_allowance,
                            MILESTONE_TARGETS, WALL_DEFAULT, WALL_ALLOWANCE_CEILING)

# A worker that keeps spawning a sleeper every 5 ms, so some spawns land while
# cleanup starts, and records each pid in a file the test reads afterwards.
SPAWNER = ("import subprocess,sys,time\nf=open(%r,'a')\nwhile True:\n"
           "    f.write(str(subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']).pid)+chr(10))\n"
           "    f.flush(); time.sleep(0.005)")


def mock_tree(process):
    """Patch the owned process tree with a mock whose launched process is `process`."""
    tree = MagicMock(process=process)
    tree.__enter__.return_value = tree
    tree.survivors.return_value = []
    return patch('n2m.process_tree.Tree', Mock(return_value=tree)), tree


def assert_dead(test, pids):
    """Bounded wait proving every pid exited; 258 (WAIT_TIMEOUT) would be a live pid."""
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    alive = []
    for pid in pids:
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            continue  # gone or reused; nothing of ours to wait on
        try:
            if kernel.WaitForSingleObject(handle, 5000) != 0:
                alive.append(pid)
        finally:
            kernel.CloseHandle(handle)
    test.assertEqual(alive, [], f'{len(alive)} of {len(pids)} descendants survived cleanup')


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

    def test_expiry_releases_the_killed_workers_tag_lock(self):
        # The worker takes the tag lock exactly as the sim-test worker does,
        # then outlives the smallest ceiling: one second of execution.
        tools = str(Path(__file__).resolve().parents[2])
        worker = (f"import sys, time; sys.path.insert(0, {tools!r}); from pathlib import Path\n"
                  f"from n2m.records import workspace\n"
                  f"with workspace(Path({str(self.root)!r}), 'held'): print('holding', flush=True); time.sleep(30)\n")
        code, text = supervise([sys.executable, '-c', worker], self.root, 'held', ceiling=13)
        self.assertEqual(code, 1)
        result = json.loads(text)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['cleanup_complete'])
        self.assertTrue(result['stale_lock_removed'])
        self.assertNotIn('lock_left', result)
        self.assertFalse((self.root / 'workdir/builds/held/.lock').exists())
        record = json.loads(next((self.root / 'workdir/builds/held/wall-budget').glob('*.json')).read_text())
        self.assertEqual(record['status'], 'TIMEOUT')
        self.assertTrue(record['stale_lock_removed'])
        # The tag is free again: a later workspace takes it without a notice.
        from n2m.records import workspace
        notices = []
        with workspace(self.root, 'held', notices):
            pass
        self.assertEqual(notices, [])

    @unittest.skipUnless(os.name == 'nt', 'Windows owned-tree cleanup')
    def test_expiry_reaps_a_descendant_racing_the_cleanup(self):
        # The worker holds the tag lock and spawns a grandchild every 5 ms, so
        # some land while cleanup starts. taskkill /T walked a snapshot and left
        # four alive per run while the lock was reclaimed; the job reaps them all.
        tools = str(Path(__file__).resolve().parents[2])
        pids = self.root / 'pids.txt'
        worker = (f"import sys; sys.path.insert(0, {tools!r}); from pathlib import Path\n"
                  f"from n2m.records import workspace\n"
                  f"with workspace(Path({str(self.root)!r}), 'race'):\n"
                  f"    exec({SPAWNER % str(pids)!r})\n")
        code, text = supervise([sys.executable, '-u', '-c', worker], self.root, 'race', ceiling=13)
        self.assertEqual(code, 1)
        spawned = [int(line) for line in pids.read_text().split()]
        self.assertGreater(len(spawned), 10, 'the worker must have been mid-spawn at expiry')
        assert_dead(self, spawned)
        result = json.loads(text)
        self.assertTrue(result['cleanup_complete'], result.get('cleanup_error'))
        self.assertTrue(result['stale_lock_removed'])
        self.assertNotIn('lock_left', result)

    def test_a_live_foreign_lock_is_left_and_named(self):
        lock = self.root / 'workdir/builds/foreign/.lock'
        lock.parent.mkdir(parents=True)
        lock.write_text(f'pid={os.getpid()}\n')
        process = Mock(pid=123, returncode=9)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 300), (b'partial', None)]
        launch, _ = mock_tree(process)
        with launch:
            code, text = supervise(['worker'], self.root, 'foreign')
        result = json.loads(text)
        self.assertEqual(code, 1)
        self.assertTrue(result['cleanup_complete'])
        self.assertEqual(result['lock_left'], lock.as_posix())
        self.assertNotIn('stale_lock_removed', result)
        self.assertEqual(lock.read_text(), f'pid={os.getpid()}\n')

    def test_an_unreadable_lock_marks_the_cleanup_incomplete(self):
        lock = self.root / 'workdir/builds/unread/.lock'
        lock.parent.mkdir(parents=True)
        lock.write_text('')
        process = Mock(pid=123, returncode=9)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 300), (b'partial', None)]
        launch, _ = mock_tree(process)
        with launch:
            code, text = supervise(['worker'], self.root, 'unread')
        result = json.loads(text)
        self.assertFalse(result['cleanup_complete'])
        self.assertEqual(result['lock_left'], lock.as_posix())
        self.assertTrue(lock.exists())

    def test_expiry_terminates_the_owned_process_tree(self):
        process = Mock(pid=123, returncode=9)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 300), (b'partial', None)]
        launch, tree = mock_tree(process)
        with launch:
            code, text = supervise(['worker'], self.root, 'tree')
            self.assertEqual(launch.new.call_args.args[0], ['worker'])
            tree.terminate.assert_called_once_with(timeout=5)
            self.assertEqual(process.communicate.call_count, 2)
            process.kill.assert_not_called()
        self.assertTrue(json.loads(text)['cleanup_complete'])

    def test_invalid_tag_never_launches(self):
        with patch('n2m.process_tree.Tree') as launch:
            with self.assertRaises(ValueError):
                supervise(['worker'], self.root, '../outside')
            launch.assert_not_called()

    def test_preparation_and_launch_consume_the_execution_budget(self):
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (b'done', b'')
        launch, _ = mock_tree(process)
        with launch, patch('n2m.test_budget.time', Mock(monotonic=Mock(side_effect=[10, 30, 31]))):
            code, _ = supervise(['worker'], self.root, 'preparation')
        self.assertEqual(code, 0)
        process.communicate.assert_called_once_with(timeout=268)

    def test_cleanup_timeouts_shrink_to_absolute_deadline(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 288),
                                          subprocess.TimeoutExpired('pipe', .5)]
        clock = Mock(monotonic=Mock(side_effect=[0, 1, 299, 299.5, 299.8, 300]))
        launch, tree = mock_tree(process)
        with launch, patch('n2m.test_budget.time', clock):
            code, text = supervise(['worker'], self.root, 'shrinking')
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)['cleanup_complete'])
        self.assertEqual(tree.terminate.call_args.kwargs['timeout'], 1)
        self.assertEqual(process.communicate.call_args.kwargs['timeout'], .5)
        self.assertAlmostEqual(process.wait.call_args.kwargs['timeout'], .2)

    def test_reap_timeout_is_bounded_even_after_successful_tree_kill(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 300),
                                           subprocess.TimeoutExpired('pipe', 5, output=b'last')]
        launch, _ = mock_tree(process)
        with launch:
            code, text = supervise(['worker'], self.root, 'reap-failure')
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)['cleanup_complete'])
        self.assertEqual(process.communicate.call_args.kwargs['timeout'], 5)
        process.wait.assert_called_once_with(timeout=2)

    def test_failed_tree_cleanup_names_survivors_and_cannot_wait_forever_on_their_pipe(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = subprocess.TimeoutExpired('worker', 300, output=b'partial')
        process.wait.side_effect = subprocess.TimeoutExpired('worker', 2)
        launch, tree = mock_tree(process)
        tree.terminate.side_effect = subprocess.TimeoutExpired('worker', 5)
        tree.survivors.return_value = [4242]
        with launch:
            code, text = supervise(['worker'], self.root, 'cleanup-failure')
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)['cleanup_complete'])
        self.assertEqual(tree.terminate.call_args.kwargs['timeout'], 5)
        process.wait.assert_called_once_with(timeout=2)
        process.communicate.assert_called_once()
        record = json.loads(next((self.root/'workdir/builds/cleanup-failure/wall-budget').glob('*.json')).read_text())
        self.assertEqual(record['status'], 'TIMEOUT')
        self.assertIn('timed out', record['cleanup_error'])
        self.assertEqual(record['survivors'], [4242])
        self.assertIn('reap_error', record)
        self.assertEqual((self.root/record['output']).read_text(), 'partial')

    def test_a_failed_survivor_query_still_records_and_releases(self):
        lock = self.root / 'workdir/builds/query-failure/.lock'
        lock.parent.mkdir(parents=True)
        lock.write_text('pid=123\n')
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = subprocess.TimeoutExpired('worker', 300)
        launch, tree = mock_tree(process)
        tree.terminate.side_effect = subprocess.TimeoutExpired('worker', 5)
        tree.survivors.side_effect = OSError(6, 'handle gone')
        with launch, patch('n2m.test_budget.release_lock') as release:
            code, text = supervise(['worker'], self.root, 'query-failure')
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(text)['cleanup_complete'])
        release.assert_called_once()
        record = json.loads(next((self.root/'workdir/builds/query-failure/wall-budget').glob('*.json')).read_text())
        self.assertEqual(record['status'], 'TIMEOUT')
        self.assertIn('handle gone', record['survivors_error'])
        self.assertNotIn('survivors', record)

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
        launch, _ = mock_tree(process)
        with launch, patch('n2m.test_budget.time', Mock(monotonic=Mock(side_effect=[10, 30, 31]))), \
             patch('n2m.test_budget.datetime', Mock(now=Mock(return_value=fixed))), \
             patch.dict('os.environ', {'N2M_TEST_EXECUTION_DEADLINE': '9999999999'}):
            code, _ = supervise(['worker'], self.root, 'selected', target='mooneye-reg-f')
        self.assertEqual(code, 0)
        process.communicate.assert_called_once_with(timeout=1468)
        self.assertEqual(float(launch.new.call_args.kwargs['env']['N2M_TEST_EXECUTION_DEADLINE']), fixed.timestamp()+1488)
        record = json.loads(next((self.root/'workdir/builds/selected/wall-budget').glob('*.json')).read_text())
        self.assertEqual((record['target'], record['wall_limit_seconds'], record['execution_limit_seconds']),
                         ('mooneye-reg-f', 1500, 1488))

    def test_selected_cleanup_still_shrinks_to_absolute_deadline(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired('worker', 1488),
                                          subprocess.TimeoutExpired('pipe', .5)]
        clock = Mock(monotonic=Mock(side_effect=[0, 1, 1499, 1499.5, 1499.8, 1500]))
        launch, tree = mock_tree(process)
        with launch, patch('n2m.test_budget.time', clock):
            code, text = supervise(['worker'], self.root, 'selected-expiry', target='mooneye-missing')
        self.assertEqual(code, 1)
        self.assertIn('1500 seconds total', json.loads(text)['error'])
        self.assertFalse(json.loads(text)['cleanup_complete'])
        self.assertEqual(tree.terminate.call_args.kwargs['timeout'], 1)
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
        declared = {name for name, row in targets.items() if 'wall_allowance' in row}
        self.assertEqual(long_targets, MILESTONE_TARGETS | declared)
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

    def registry(self, rows):
        """Write a target registry under this test root and return that root."""
        path = self.root / 'src/dv/builder/targets.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding='utf-8')
        return self.root

    def test_declared_allowance_raises_the_limit_up_to_the_ceiling(self):
        for seconds in (301, 420, WALL_ALLOWANCE_CEILING):
            with self.subTest(seconds=seconds):
                root = self.registry({'slow': {'wall_allowance': {'seconds': seconds,
                                                                 'reason': 'measured 289s of work'}}})
                self.assertEqual(wall_selection('slow', root), (seconds, 'measured 289s of work'))

    def test_declaration_above_the_ceiling_is_refused_not_clamped(self):
        root = self.registry({'slow': {'wall_allowance': {'seconds': WALL_ALLOWANCE_CEILING + 1,
                                                          'reason': 'too long'}}})
        with self.assertRaisesRegex(ValueError, '301..900'):
            wall_selection('slow', root)

    def test_non_integer_or_below_default_declaration_is_refused(self):
        for seconds in (300, 0, -1, 420.0, True, '420'):
            with self.subTest(seconds=seconds):
                with self.assertRaisesRegex(ValueError, '301..900'):
                    declared_allowance('slow', {'wall_allowance': {'seconds': seconds, 'reason': 'why'}})

    def test_allowance_without_a_recorded_reason_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'exactly seconds and reason'):
            declared_allowance('slow', {'wall_allowance': {'seconds': 420}})
        for reason in ('', '   ', None, 7):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, 'recorded reason'):
                    declared_allowance('slow', {'wall_allowance': {'seconds': 420, 'reason': reason}})
        with self.assertRaisesRegex(ValueError, 'exactly seconds and reason'):
            declared_allowance('slow', {'wall_allowance': {'seconds': 420, 'reason': 'why', 'extra': 1}})
        with self.assertRaisesRegex(ValueError, 'exactly seconds and reason'):
            declared_allowance('slow', {'wall_allowance': 420})

    def test_targets_that_declare_nothing_keep_the_default(self):
        root = self.registry({'ordinary': {'timeout_seconds': 120},
                              'slow': {'wall_allowance': {'seconds': 900, 'reason': 'why'}}})
        for name in ('ordinary', 'missing', '', None, 'SLOW', 'slow '):
            with self.subTest(name=name):
                self.assertEqual(wall_selection(name, root), (WALL_DEFAULT, None))
        self.assertEqual(wall_limit('ordinary', root), 300)

    def test_shipped_targets_declare_only_measured_allowances(self):
        # Only the measured motion, power, pause and entity fixtures declare one; every
        # other target keeps the 300 default or its named Mooneye authorization.
        root = Path(__file__).resolve().parents[3]
        targets = json.loads((root / 'src/dv/builder/targets.json').read_text(encoding='utf-8'))
        declared = {name: row['wall_allowance'] for name, row in targets.items() if 'wall_allowance' in row}
        self.assertEqual(sorted(declared), ['python-entity-render-changed', 'python-entity-render-normal', 'python-mgu', 'python-mr', 'python-pgu', 'python-pgx', 'python-pr'])
        for name in ('python-entity-render-changed', 'python-entity-render-normal'):
            self.assertEqual(declared[name]['seconds'], 420)
        for name in ('python-mr', 'python-pr'):
            self.assertEqual(declared[name]['seconds'], 480)
        for name, allowance in declared.items():
            self.assertEqual(set(allowance), {'seconds', 'reason'})
            self.assertTrue(300 < allowance['seconds'] <= 900)
            self.assertIn('measured', allowance['reason'])
        for name in targets:
            expected = 1500 if name in MILESTONE_TARGETS else declared[name]['seconds'] if name in declared else 300
            self.assertEqual(wall_limit(name, root), expected)

    def test_supervisor_enforces_and_records_a_declared_allowance(self):
        root = self.registry({'slow': {'wall_allowance': {'seconds': 480, 'reason': 'preload dominates'}}})
        process = Mock(pid=123, returncode=0)
        process.communicate.return_value = (b'done', b'')
        fixed = datetime(2026, 9, 9, tzinfo=timezone.utc)
        launch, _ = mock_tree(process)
        with launch, patch('n2m.test_budget.time', Mock(monotonic=Mock(side_effect=[10, 30, 31]))),              patch('n2m.test_budget.datetime', Mock(now=Mock(return_value=fixed))):
            code, _ = supervise(['worker'], root, 'declared', target='slow')
        self.assertEqual(code, 0)
        process.communicate.assert_called_once_with(timeout=448)
        self.assertEqual(float(launch.new.call_args.kwargs['env']['N2M_TEST_EXECUTION_DEADLINE']), fixed.timestamp() + 468)
        record = json.loads(next((root / 'workdir/builds/declared/wall-budget').glob('*.json')).read_text())
        self.assertEqual((record['wall_limit_seconds'], record['execution_limit_seconds'],
                          record['wall_allowance_reason']), (480, 468, 'preload dominates'))

    def test_validator_accepts_a_declared_timeout_and_refuses_above_it(self):
        from n2m.simulation import load_target
        root = Path(__file__).resolve().parents[3]
        targets = json.loads((root / 'src/dv/builder/targets.json').read_text(encoding='utf-8'))
        ordinary = next(name for name in targets if name not in MILESTONE_TARGETS)
        declared = {**targets[ordinary], 'wall_allowance': {'seconds': 600, 'reason': 'measured 289s of work'},
                    'timeout_seconds': 600}
        with patch('n2m.simulation.json.loads', return_value={ordinary: declared}):
            self.assertEqual(load_target(root, ordinary)[0]['timeout_seconds'], 600)
        with patch('n2m.simulation.json.loads', return_value={ordinary: {**declared, 'timeout_seconds': 601}}):
            with self.assertRaisesRegex(ValueError, '1..600'):
                load_target(root, ordinary)
        with patch('n2m.simulation.json.loads',
                   return_value={ordinary: {**targets[ordinary],
                                            'wall_allowance': {'seconds': 901, 'reason': 'why'}}}):
            with self.assertRaisesRegex(ValueError, '301..900'):
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
