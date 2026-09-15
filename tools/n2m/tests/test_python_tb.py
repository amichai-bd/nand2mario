"""Host-only Python dispatch/evidence tests; these do not execute RTL."""
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_builder
from n2m import python_tb
from n2m.simulation import load_target
from n2m.questa import commands
from n2m.records import atomic_json, read_json


XML = ('<testsuites name="cocotb tests"><testsuite name="test_joypad" errors="0" failures="0" skipped="0" tests="1" time="0.2" timestamp="t" hostname="h">'
       '<testcase classname="test_joypad" name="joypad_contract" time="0.2"><properties><property name="random_seed" value="1" />'
       '<property name="sim_time_duration" value="100" /></properties></testcase></testsuite></testsuites>')


class PythonTests(unittest.TestCase):
    run_stage = test_builder.BuilderTests.run_stage

    def setUp(self):
        test_builder.BuilderTests.setUp(self)
        for owner in ("src/dv/python", "src/rtl/joypad", "src/rtl/interfaces", "src/rtl/common"):
            shutil.copytree(test_builder.ROOT / owner, self.root / owner, ignore=shutil.ignore_patterns("__pycache__"))
        self.args.target = "python-joypad"
        self.runtime = {"backend": "verilator", "executable": sys.executable, "libpython": "libpython.so", "library": "/venv/libs/libcocotbvpi_verilator.so",
                        "library_dir": "/venv/libs", "support": "/venv/share/lib/verilator/verilator.cpp",
                        "entry_point": "/venv/simulator.so,initialize", "version": "pinned"}
        self.discovery = patch("n2m.python_tb.discover", return_value=self.runtime)
        self.discovery.start()
        self.addCleanup(self.discovery.stop)
        original = self.sim.run
        self.xml = XML
        self.raw_exit = 0
        self.stdout = "PASS python-joypad"
        self.env = None

        def run(argv, cwd=None, timeout=60, env=None):
            result = original(argv, cwd)
            if argv[0] != self.sim.compiler:
                self.env = env
                if self.xml is not None:
                    (cwd / "results.xml").write_text(self.xml)
                (cwd / "transactions.jsonl").write_text("retained evidence")
                return SimpleNamespace(returncode=self.raw_exit, stdout=self.stdout)
            return result
        self.sim.run = run

    def test_python_runtime_remains_bounded(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = json.loads(registry.read_text())
        for timeout in (1, 300):
            targets["python-joypad"]["timeout_seconds"] = timeout
            registry.write_text(json.dumps(targets))
            self.assertEqual(load_target(self.root, "python-joypad")[0]["timeout_seconds"], timeout)
        for timeout in (0, 301, 1000, 1500, 43200, True):
            targets["python-joypad"]["timeout_seconds"] = timeout
            registry.write_text(json.dumps(targets))
            with self.assertRaisesRegex(ValueError, "timeout_seconds"):
                load_target(self.root, "python-joypad")

    def test_dispatch_identity_and_artifact_cache(self):
        result = self.run_stage()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["commands"][-1]["exit_code"], 0)
        self.assertEqual(result["python_results"]["status"], "PASS")
        self.assertIn("--vpi", self.sim.calls[-2])
        self.assertEqual(self.sim.calls[-2][-1], self.runtime["support"])
        self.assertIn("--trace-file", self.sim.calls[-1])
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        for suffix in ("results.xml", "transactions.jsonl", "simulation.fst"):
            artifact = next(p for p in result["artifacts"] if p.endswith(suffix))
            (self.root / artifact).write_text("damaged")
            result = self.run_stage()
            self.assertEqual(result["cache"], "BUILT")
            self.assertEqual(result["status"], "PASS")
        for source in ("src/dv/python/joypad/test_joypad.py", "src/dv/python/requirements.txt"):
            path = self.root / source
            path.write_text(path.read_text() + "\n")
            self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.runtime["version"] = "changed runtime identity"
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_failed_missing_malformed_incomplete_and_extra_tests(self):
        mutations = [None, "", "<broken", XML.replace('time="0.2"><properties>', 'time="nan"><properties>'),
                     XML.replace('<property name="sim_time_duration" value="100" />', ''),
                     XML.replace('<property name="sim_time_duration" value="100" />', '<property name="sim_time_duration" value="0" />'),
                     XML.replace('joypad_contract', 'other'),
                     XML.replace('</properties>', '</properties><failure message="JOYP_MISMATCH" type="AssertionError" />'),
                     XML.replace('</properties>', '</properties><error />'),
                     XML.replace('</properties>', '</properties><skipped />'),
                     XML.replace('</properties>', '</properties><unexpected />'),
                     XML.replace('</testsuite>', '<testcase /></testsuite>'),
                     XML.replace('tests="1"', 'tests="2"'),
                     XML.replace('failures="0"', 'failures="1"'),
                     XML.replace('hostname="h"', 'hostname="h" extra="1"')]
        for xml in mutations:
            self.xml = xml
            result = self.run_stage()
            self.assertEqual(result["status"], "FAIL", xml)
            self.assertEqual(result["commands"][-1]["exit_code"], 0)
            self.assertEqual(result["python_results"]["status"], "FAIL")
            self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_nonzero_raw_exit_cannot_pass_valid_xml(self):
        self.raw_exit = 1
        result = self.run_stage()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["python_results"]["status"], "PASS")
        self.assertEqual(result["commands"][-1]["exit_code"], 1)

    def test_expected_failure_needs_named_test_failure_with_signature(self):
        """A Python fault target passes by failing in the declared way, and only that way."""
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        targets["python-joypad"].update(expected_exit="nonzero", signature="JOYP_MISMATCH cycle=3")
        atomic_json(registry, targets)
        failed = XML.replace('failures="0"', 'failures="1"').replace(
            '</properties>', '</properties><failure message="JOYP_MISMATCH cycle=3 phase=post" type="AssertionError">trace</failure>')
        self.xml = failed
        # cocotb reports the failure as one WARNING line and ends through $finish.
        self.stdout = ("47.00ns WARNING  cocotb.regression  test_joypad.joypad_contract failed\n"
                       "AssertionError: JOYP_MISMATCH cycle=3 phase=post\n- :0: Verilog $finish")
        result = self.run_stage()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["commands"][-1]["exit_code"], 0)
        self.assertEqual(result["python_results"]["status"], "FAIL")
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        rejected = [
            (XML, self.stdout, "verdict does not match"),
            (failed.replace("JOYP_MISMATCH cycle=3 phase=post", "JOYP_UNKNOWN cycle=3"), self.stdout, "verdict does not match"),
            (failed.replace('message="JOYP_MISMATCH cycle=3 phase=post"', ''), self.stdout, "verdict does not match"),
            (XML.replace('failures="0"', 'failures="1"'), self.stdout, "verdict does not match"),
            (XML.replace('skipped="0"', 'skipped="1"').replace(
                '</properties>', '</properties><skipped message="JOYP_MISMATCH cycle=3 phase=post" />'),
             self.stdout, "verdict does not match"),
            ("<broken", self.stdout, "verdict does not match"),
            (failed, self.stdout + "\nWARNING  cocotb.regression  other failed", "unexplained simulator warning"),
            (failed, self.stdout.replace("test_joypad.joypad_contract failed", "test_joypad.other failed"),
             "unexplained simulator warning"),
            (failed, "47.00ns WARNING  cocotb.regression  test_joypad.joypad_contract failed\n- :0: Verilog $finish",
             "missing expected signature")]
        good = self.stdout
        self.args.rebuild = True
        for xml, stdout, error in rejected:
            self.xml, self.stdout = xml, stdout
            result = self.run_stage()
            self.assertEqual(result["status"], "FAIL", (xml, stdout))
            self.assertIn(error, result["error"])
        self.xml, self.stdout = failed, good
        self.raw_exit = 1
        result = self.run_stage()
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("unexpected exit 1", result["error"])

    def test_missing_inventory_not_reusable(self):
        self.run_stage()
        current = self.build / "sim/test/python-joypad/verilator/result.json"
        record = read_json(current)
        del record["artifacts"][record["python_results_file"]]
        atomic_json(current, record)
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_environment_owns_filters_seed_and_runtime(self):
        overrides = dict(COCOTB_TEST_FILTER="nothing", COCOTB_TESTCASE="other", COCOTB_RANDOM_SEED="42",
                         COCOTB_RESOLVE_X="ZEROS", PYTHONPATH="foreign", PYGPI_PYTHON_BIN="foreign",
                         LIBPYTHON_LOC="foreign", GPI_EXTRA="foreign", MGLS_LICENSE_FILE="license", PYTHONOPTIMIZE="1")
        with patch.dict(os.environ, overrides):
            result = self.run_stage()
        self.assertEqual(result["status"], "PASS")
        for name in ("COCOTB_TEST_FILTER", "COCOTB_TESTCASE", "COCOTB_RESOLVE_X", "GPI_EXTRA"):
            self.assertNotIn(name, self.env)
        self.assertNotIn("foreign", self.env["PYTHONPATH"])
        self.assertEqual(self.env["COCOTB_RANDOM_SEED"], "1")
        self.assertEqual(self.env["MGLS_LICENSE_FILE"], "license")
        self.assertEqual(self.env["LIBPYTHON_LOC"], "libpython.so")
        self.assertEqual(self.env["GPI_USERS"], "libpython.so;/venv/simulator.so,initialize")
        self.assertEqual(self.env["COCOTB_TOPLEVEL"], "n2m_joypad")
        self.assertEqual(self.env["PYTHONOPTIMIZE"], "0")

    def test_invalid_configuration_has_no_silent_fallback(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        original = targets["python-joypad"]
        for changes in ({"testbench": "unknown"}, {"testbench": "systemverilog"},
                        {"python": {}}, {"driver": {}}, {"top": "bad top"},
                        {"python": {"module": "test_joypad", "test": "joypad_contract", "inputs": ["../missing"]}}):
            targets["python-joypad"] = {**original, **changes}
            atomic_json(registry, targets)
            with self.assertRaises(ValueError):
                self.run_stage()
        self.assertFalse(self.sim.calls)

    def test_python_intel_binding_and_unsupported_preload(self):
        target = read_json(self.root / "src/dv/builder/targets.json")["python-joypad"]
        target["vendor_model"] = "intel-memory"
        python_tb.validate(self.root, target)
        vendor = {"selection": "intel-memory", "library": "n2m_altera_mf", "sources": [{"path": "installed model.v"}],
                  "compile_options": ["-work", "n2m_altera_mf"],
                  "binding_options": ["-L", "n2m_altera_mf"]}
        questa = SimpleNamespace(tools={name: name for name in ("vlib", "vmap", "vlog", "vsim")}, path=str)
        argv = commands(questa, self.root, target, 1, self.build, self.build,
                        prepare=False, vendor_model=vendor, python_runtime=self.runtime)
        runtime = argv[-1][0]
        self.assertIn("-pli", runtime)
        self.assertEqual(runtime[runtime.index("-L") + 1], "n2m_altera_mf")
        self.assertTrue(any("installed model.v" in command for command, *_ in argv))
        for invalid in ({"vendor_model": "intel-adc"}, {"preload": "unknown"},
                        {"preload": "integration"}, {"driver": {}}):
            with self.assertRaises(ValueError):
                python_tb.validate(self.root, {**target, **invalid})

    def test_prepare_writes_no_simulator_macro(self):
        python_tb.prepare({}, self.build)
        self.assertEqual(list(self.build.glob("*.do")), [])

    def test_discovery_unavailable_is_explicit(self):
        self.discovery.stop()
        with patch.object(sys, "version_info", (3, 14, 5)):
            with self.assertRaisesRegex(ValueError, "Python 3.12.14"):
                python_tb.discover()
        with patch.object(sys, "version_info", (3, 12, 14)), patch.dict(sys.modules, {"cocotb_tools.config": None}):
            with self.assertRaisesRegex(ValueError, "dependencies unavailable"):
                python_tb.discover()


if __name__ == "__main__":
    unittest.main()
