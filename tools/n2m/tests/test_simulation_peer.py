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
        # Publish like the product peers: the parent polls exists() then reads,
        # so a bare write_text can expose an empty file under host load.
        return ("(p/'peer-ready.tmp').write_text(json.dumps({'host':'127.0.0.1','port':12345}))\n"
                "(p/'peer-ready.tmp').replace(p/'peer-ready.json')\n")

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
        # The reaped peer may not have published before the process was torn
        # down: no file is acceptable. A file that exists must be a complete,
        # parseable record; a partial or empty one is the atomicity defect.
        records = list(self.attempt.rglob('peer-result.json'))
        self.assertLessEqual(len(records), 1)
        if records:
            self.assertIsNotNone(json.loads(records[0].read_text())['exit_code'])


class DriverDeadlineTests(unittest.TestCase):
    def test_long_transaction_then_next_request(self):
        # Execute the actual Tcl control flow with only public mailbox operations
        # stubbed. No simulator, serial endpoint or product behavior is modeled.
        try:
            import tkinter
        except ImportError:
            self.skipTest('Tcl runtime unavailable; exercised in local Windows check')
        tcl = tkinter.Tcl()
        tcl.eval(r"""
            set smoke_peer_port 1
            set wall 0
            set incoming 0
            set replies 0
            set advances 0
            array set signals {simulation_ns 0 tx_count 0 tx_busy 0 rx_count 0 rx_done 0 finish_request 0}
            rename clock real_clock
            proc clock {arg} { global wall; return $wall }
            proc socket {args} { return smoke }
            proc fconfigure {args} {}
            proc close {args} {}
            proc flush {args} {}
            proc eof {args} { return 0 }
            proc after {args} { global wall; incr wall }
            proc puts {args} {
                global replies
                if {[llength $args]==2 && [lindex $args 0] eq "smoke"} { incr replies }
            }
            proc gets {channel variable} {
                global incoming
                upvar 1 $variable line
                incr incoming
                switch $incoming {
                    1 - 3 { set line "TX 00"; return 5 }
                    2 { return -1 }
                    4 { set line "DONE"; return 4 }
                    default { error "unexpected extra input read" }
                }
            }
            proc examine {args} {
                global signals
                set name [lindex [split [lindex $args end] /] end]
                if {[string match "rx_bytes*" $name]} { return 0 }
                return $signals($name)
            }
            proc force {mode path value} {
                global signals
                set name [lindex [split $path /] end]
                set signals($name) [string range $value 3 end]
            }
            proc run {amount units} {
                global wall signals advances
                if {$signals(finish_request)} { error TEST_COMPLETED }
                if {$amount==100} {
                    incr advances
                    incr wall [expr {$advances==1 ? 60000 : 1}]
                    incr signals(simulation_ns) 100000
                    set signals(rx_done) 1
                    set signals(rx_count) 1
                }
            }
        """)
        driver = (ROOT / 'src/dv/integration/driver.do').read_text()
        with self.assertRaisesRegex(tkinter.TclError, 'TEST_COMPLETED'):
            tcl.eval(driver)
        self.assertEqual(int(tcl.getvar('replies')), 2)
        self.assertEqual(int(tcl.getvar('advances')), 2)
