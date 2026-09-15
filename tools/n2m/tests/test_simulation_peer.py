"""Real child lifecycle checks without licensed tools or a fake product endpoint."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import test_builder
from n2m.records import read_json
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
        target = {'signature': 'PASS', 'sources': [], 'expected_exit': 'zero', 'simulators': ['verilator'],
                  'driver': {'script': '../outside.do', 'peer': 'child.py', 'inputs': []}}
        registry.write_text(json.dumps({'smoke': target}))
        with self.assertRaisesRegex(ValueError, 'out-of-tree driver'):
            load_target(self.root, 'smoke')

    def test_tcl_driver_has_no_silent_backend_fallback(self):
        self.script(self.ready() + 'time.sleep(60)\n')
        (self.root / 'driver.do').write_text('# driver\n')
        for name in ['tools/build.py', 'tools/n2m/dependencies.json']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}')
        registry = self.root / 'src/dv/builder/targets.json'
        registry.parent.mkdir(parents=True)
        row = {'signature': 'PASS', 'sources': [], 'args': [], 'expected_exit': 'zero', 'simulators': ['verilator'],
               'driver': {'script': 'driver.do', 'peer': 'child.py', 'inputs': []}}
        registry.write_text(json.dumps({'smoke': row}))
        with self.assertRaisesRegex(ValueError, 'Python peer driver supports only Verilator'):
            load_target(self.root, 'smoke')
        row['simulators'] = ['questa']
        registry.write_text(json.dumps({'smoke': row}))
        with self.assertRaisesRegex(ValueError, 'Python peer driver supports only Verilator'):
            load_target(self.root, 'smoke')
        self.assertEqual(list(self.attempt.rglob('peer-result.json')), [])


PEER_XML = ('<testsuites name="cocotb tests"><testsuite name="driver" errors="0" failures="{failures}" skipped="0" tests="1" time="0.2" timestamp="t" hostname="h">'
            '<testcase classname="driver" name="peer" time="0.2"><properties><property name="random_seed" value="1" />'
            '<property name="sim_time_duration" value="5502000" /></properties>{verdict}</testcase></testsuite></testsuites>')
PEER_STOP = ("  2080.00ns WARNING  cocotb.regression                  driver.peer failed\n"
             "    cocotb.regression.SimFailure: cocotb expected it would shut down the simulation, but the simulation ended prematurely. x\n")


class VerilatorDriverStageTests(unittest.TestCase):
    """The driver stage under Verilator with a simulator double: the peer is a
    real child, the cocotb run is faked through its transcript and results."""
    setUp_builder = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def setUp(self):
        self.setUp_builder()
        shutil.copytree(ROOT / 'src/dv/integration', self.root / 'src/dv/integration', ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('src/dv/python/requirements.txt', 'src/dv/python/THIRD_PARTY.md'):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)
        (self.root / 'child.py').write_text(
            "import pathlib,sys,json\np=pathlib.Path(sys.argv[sys.argv.index('--attempt')+1])\n"
            "(p/'peer-ready.tmp').write_text(json.dumps({'host':'127.0.0.1','port':12345}))\n"
            "(p/'peer-ready.tmp').replace(p/'peer-ready.json')\n(p/'client.json').write_text('{}')\nprint('PASS child peer')\n")
        registry = self.root / 'src/dv/builder/targets.json'
        targets = json.loads(registry.read_text())
        for name in ('verilator-peer', 'verilator-peer-fatal'):
            targets[name]['driver']['peer'] = 'child.py'
        registry.write_text(json.dumps(targets))
        self.args.target = 'verilator-peer'
        self.runtime = {'backend': 'verilator', 'executable': sys.executable, 'libpython': 'libpython.so', 'library': '/venv/libs/libcocotbvpi_verilator.so',
                        'library_dir': '/venv/libs', 'support': '/venv/share/lib/verilator/verilator.cpp',
                        'entry_point': '/venv/simulator.so,initialize', 'version': 'pinned'}
        patcher = patch('n2m.python_tb.discover', return_value=self.runtime)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.xml = PEER_XML.format(failures=0, verdict='')
        self.transcript = 'SMOKE_DRIVER phase=received ordinal=1\nPASS verilator-peer transactions=3\n'
        self.raw_exit = 0
        self.env = None
        original = self.sim.run

        def run(argv, cwd=None, timeout=60, env=None):
            result = original(argv, cwd)
            if argv[0] != self.sim.compiler:
                self.env = env
                self.argv = argv
                (cwd / 'results.xml').write_text(self.xml)
                return SimpleNamespace(returncode=self.raw_exit, stdout=self.transcript)
            return result
        self.sim.run = run

    def test_peer_runs_inside_the_verilator_stage_and_its_evidence_is_cached(self):
        record = self.run_stage()
        self.assertEqual(record['status'], 'PASS', record.get('error'))
        self.assertEqual(record['peer']['port'], 12345)
        self.assertEqual(self.env['N2M_PEER_PORT'], '12345')
        self.assertEqual(self.env['N2M_DRIVER_ACCESS'].split(',')[:2], ['tx_bytes', 'rx_bytes'])
        self.assertEqual(self.env['COCOTB_TEST_MODULES'], 'driver')
        self.assertTrue(self.env['PYTHONPATH'].startswith(str(self.root / 'src/dv/integration')))
        self.assertIn('--timing', self.sim.calls[-2])
        self.assertIn('--vpi', self.sim.calls[-2])
        self.assertEqual(self.argv[-1], '+smoke_root=' + str(self.root))
        self.assertEqual(record['python_results']['status'], 'PASS')
        for suffix in ('peer.log', 'peer-result.json', 'results.xml', 'client.json', 'waves/simulation.fst'):
            self.assertTrue(any(path.endswith(suffix) for path in record['artifacts']), suffix)
        peer_result = read_json(self.root / next(p for p in record['artifacts'] if p.endswith('peer-result.json')))
        self.assertTrue(peer_result['completed_normally'])
        self.assertEqual(peer_result['exit_code'], 0)
        self.assertEqual(self.run_stage()['cache'], 'CACHED')
        (self.root / 'src/dv/integration/peer_bridge.py').write_text(
            (self.root / 'src/dv/integration/peer_bridge.py').read_text() + '\n')
        self.assertEqual(self.run_stage()['cache'], 'BUILT')

    def test_peer_protocol_fault_fails_by_name_and_reaps_the_peer(self):
        self.xml = PEER_XML.format(failures=1, verdict='<failure message="SMOKE_DRIVER_WAIT_RANGE" type="RuntimeError" />')
        self.transcript = '  101000.00ns WARNING  cocotb.regression  driver.peer failed\nRuntimeError: SMOKE_DRIVER_WAIT_RANGE\n'
        record = self.run_stage()
        self.assertEqual(record['status'], 'FAIL')
        self.assertEqual(record['error'], 'Verilator peer failed: SMOKE_DRIVER_WAIT_RANGE')
        peer_result = read_json(self.root / next(p for p in record['artifacts'] if p.endswith('peer-result.json')))
        self.assertFalse(peer_result['completed_normally'])
        self.assertEqual(self.run_stage()['cache'], 'BUILT')

    def test_peer_exit_after_a_passing_run_keeps_the_transcript(self):
        (self.root / 'child.py').write_text((self.root / 'child.py').read_text() + "sys.exit(7)\n")
        record = self.run_stage()
        self.assertEqual(record['status'], 'FAIL')
        self.assertEqual(record['error'], 'simulation peer failed with exit 7')
        self.assertEqual(record['commands'][-1]['exit_code'], 0)
        sim_log = self.root / next(p for p in record['artifacts'] if p.endswith('/sim.log'))
        self.assertEqual(sim_log.read_text(), self.transcript)

    def test_expected_testbench_fatal_accepts_the_peer_stop_report_only(self):
        self.args.target = 'verilator-peer-fatal'
        self.raw_exit = 1
        self.xml = PEER_XML.format(failures=1, verdict='<failure message="cocotb expected it would shut down" type="SimFailure" />')
        fatal = '[2080000] %Fatal: tb.sv:36: Assertion failed in tb.endpoint: PEER_ECHO_FAULT seq=2\n%Error: /r/tb.sv:36: Verilog $stop\nAborting...\n'
        self.transcript = fatal + PEER_STOP
        record = self.run_stage()
        self.assertEqual(record['status'], 'PASS', record.get('error'))
        self.assertEqual(record['python_results']['status'], 'FAIL')
        self.assertEqual(self.run_stage()['cache'], 'CACHED')
        self.transcript = PEER_STOP + 'PEER_ECHO_FAULT seq=2\n'
        self.args.rebuild = True
        record = self.run_stage()
        self.assertEqual(record['status'], 'FAIL')
        self.assertIn('unexplained simulator warning', record['error'])


    def test_expected_peer_raised_failure_passes_by_its_signature_with_exit_zero(self):
        # The host_play driver raises the retired driver's FAIL <name>; cocotb
        # records it and ends through $finish, so the raw exit is zero.
        self.args.target = 'verilator-peer-fatal'
        registry = self.root / 'src/dv/builder/targets.json'
        targets = json.loads(registry.read_text())
        signature = targets['verilator-peer-fatal']['signature']
        self.raw_exit = 0
        self.xml = PEER_XML.format(failures=1, verdict=f'<failure message="{signature}" type="RuntimeError" />')
        self.transcript = f'  101000.00ns WARNING  cocotb.regression  driver.peer failed\nRuntimeError: {signature}\n'
        record = self.run_stage()
        self.assertEqual(record['status'], 'PASS', record.get('error'))
        self.assertEqual(record['python_results']['status'], 'FAIL')
        self.assertEqual(record['commands'][-1]['exit_code'], 0)
        # Another failure name, a passing peer, or a foreign warning all fail.
        self.args.rebuild = True
        self.xml = PEER_XML.format(failures=1, verdict='<failure message="PLAY_OTHER" type="RuntimeError" />')
        self.transcript = '  101000.00ns WARNING  cocotb.regression  driver.peer failed\nRuntimeError: PLAY_OTHER\n'
        self.assertEqual(self.run_stage()['status'], 'FAIL')
        self.xml = PEER_XML.format(failures=0, verdict='')
        self.transcript = f'{signature}\n'
        record = self.run_stage()
        self.assertEqual(record['status'], 'FAIL')
        self.assertIn('unexpected exit 0', record['error'])
        self.xml = PEER_XML.format(failures=1, verdict=f'<failure message="{signature}" type="RuntimeError" />')
        self.transcript = f'  101000.00ns WARNING  cocotb.regression  driver.peer failed\n  WARNING other\nRuntimeError: {signature}\n'
        record = self.run_stage()
        self.assertEqual(record['status'], 'FAIL')
        self.assertIn('unexplained simulator warning', record['error'])


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
