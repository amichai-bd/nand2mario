"""Real child lifecycle checks without licensed tools or a fake product endpoint."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.simulation_peer import Peer
from n2m.simulation import load_target
from n2m.simulation import simulate
from n2m.simulator import ToolError

ROOT = Path(__file__).resolve().parents[3]


class PeerTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'workdir/builds/peer-unit'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='peer space ', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.attempt = self.root / 'attempt'
        self.attempt.mkdir()

    def script(self, suffix):
        path = self.root / 'child.py'
        path.write_text("import pathlib,sys,time,json\n"
            "p=pathlib.Path(sys.argv[sys.argv.index('--attempt')+1])\n" + suffix)
        return Peer(self.root, self.attempt, 'child.py')

    def ready(self):
        return "(p/'peer-ready.json').write_text(json.dumps({'host':'127.0.0.1','port':12345}))\n"

    def test_success_in_path_with_spaces(self):
        peer = self.script(self.ready())
        self.assertEqual(peer.start(), 12345)
        peer.close(True)
        self.assertEqual(peer.process.returncode, 0)
        self.assertTrue(json.loads((self.attempt / 'peer-result.json').read_text())['completed_normally'])

    def test_early_failure_propagates_and_is_reaped(self):
        peer = self.script('sys.exit(3)\n')
        with self.assertRaisesRegex(RuntimeError, 'before readiness'):
            peer.start()
        self.assertEqual(peer.process.returncode, 3)

    def test_nonzero_completion_is_not_success(self):
        peer = self.script(self.ready() + 'sys.exit(7)\n')
        peer.start()
        with self.assertRaisesRegex(RuntimeError, 'exit 7'):
            peer.close(True)
        self.assertEqual(peer.process.returncode, 7)

    def test_runtime_failure_cancels_waiting_peer(self):
        peer = self.script(self.ready() + 'time.sleep(60)\n')
        peer.start()
        with self.assertRaisesRegex(RuntimeError, 'original runtime failure'):
            try:
                raise RuntimeError('original runtime failure')
            finally:
                peer.close(False)
        self.assertIsNotNone(peer.process.returncode)

    def test_unready_stall_times_out_and_is_reaped(self):
        peer = self.script('time.sleep(60)\n')
        with self.assertRaisesRegex(RuntimeError, 'readiness timeout'):
            peer.start()
        self.assertIsNotNone(peer.process.returncode)

    def test_declared_driver_inputs_cannot_escape_root(self):
        registry = self.root / 'src/dv/builder/targets.json'
        registry.parent.mkdir(parents=True)
        target = {'signature': 'PASS', 'sources': [], 'expected_exit': 'zero',
                  'driver': {'script': '../outside.do', 'peer': 'child.py', 'inputs': []}}
        registry.write_text(json.dumps({'smoke': target}))
        with self.assertRaisesRegex(ValueError, 'out-of-tree driver'):
            load_target(self.root, 'smoke')

    def test_builder_timeout_reaps_peer_and_retains_original_error(self):
        self.script(self.ready() + 'time.sleep(60)\n')
        (self.root / 'driver.do').write_text('# driver\n')
        for name in ['tools/build.py', 'tools/n2m/dependencies.json']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}')
        registry = self.root / 'src/dv/builder/targets.json'
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({'smoke': {'signature': 'PASS', 'sources': [],
            'args': [], 'expected_exit': 'zero', 'driver': {
                'script': 'driver.do', 'peer': 'child.py', 'inputs': []}}}))
        class Runtime:
            info = {}
            def command(self, argv): return argv
            def run(self, argv, **kwargs): raise ToolError('retained outer timeout', 'partial runtime')
        def commands(simulator, root, target, seed, compiler, attempt, **kwargs):
            (attempt / 'run.do').write_text('run -all\n')
            return [(['fake-runtime'], attempt, attempt / 'sim.log', 'zero')]
        args = SimpleNamespace(target='smoke', seed=1, rebuild=False)
        with patch('n2m.simulation.intel_memory.resolve', return_value=None), patch('n2m.simulation.questa_commands', commands):
            result = simulate(self.root, self.attempt, args, Runtime())
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('retained outer timeout', result['error'])
        records = list(self.attempt.rglob('peer-result.json'))
        self.assertEqual(len(records), 1)
        self.assertIsNotNone(json.loads(records[0].read_text())['exit_code'])
