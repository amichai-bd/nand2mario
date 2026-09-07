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
from n2m.questa import commands, diagnostic
from n2m.records import atomic_json, read_json


XML = '<testsuites name="results"><testsuite name="all" package="all"><testcase name="joypad_contract" classname="test_joypad" time="0.2" sim_time_ns="100" /></testsuite></testsuites>'
WARNING = '# ** Warning: (vopt-10908) Some optimizations are turned off because the +acc switch is in effect.'


class PythonTests(unittest.TestCase):
    run_stage = test_builder.BuilderTests.run_stage

    def setUp(self):
        test_builder.BuilderTests.setUp(self)
        for owner in ("src/dv/python", "src/rtl/joypad", "src/rtl/interfaces", "src/rtl/common"):
            shutil.copytree(test_builder.ROOT / owner, self.root / owner, ignore=shutil.ignore_patterns("__pycache__"))
        self.args.target = "python-joypad"
        self.runtime = {"executable": sys.executable, "libpython": "libpython.dll", "library": "cocotbvpi.dll", "version": "pinned"}
        self.discovery = patch("n2m.python_tb.discover", return_value=self.runtime)
        self.discovery.start()
        self.addCleanup(self.discovery.stop)
        original = self.sim.run
        self.xml = XML
        self.raw_exit = 0
        self.env = None

        def run(argv, cwd=None, timeout=60, env=None):
            result = original(argv, cwd)
            if argv[0] == "vsim":
                self.env = env
                if self.xml is not None:
                    (cwd / "results.xml").write_text(self.xml)
                for path in ("transactions.jsonl", "waves/simulation.wlf", "waves/simulation.vcd"):
                    (cwd / path).write_text("retained evidence")
                return SimpleNamespace(returncode=self.raw_exit, stdout="PASS python-joypad")
            return result
        self.sim.run = run

    def test_python_runtime_remains_bounded(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = json.loads(registry.read_text())
        for timeout in (1000, 43200):
            targets["python-joypad"]["timeout_seconds"] = timeout
            registry.write_text(json.dumps(targets))
            self.assertEqual(load_target(self.root, "python-joypad")[0]["timeout_seconds"], timeout)
        for timeout in (0, 43201, True):
            targets["python-joypad"]["timeout_seconds"] = timeout
            registry.write_text(json.dumps(targets))
            with self.assertRaisesRegex(ValueError, "timeout_seconds"):
                load_target(self.root, "python-joypad")

    def test_dispatch_identity_and_artifact_cache(self):
        result = self.run_stage()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["commands"][-1]["exit_code"], 0)
        self.assertEqual(result["python_results"]["status"], "PASS")
        self.assertIn("-pli", self.sim.calls[-1])
        self.assertIn("-no_autoacc", self.sim.calls[-1])
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        for suffix in ("results.xml", "transactions.jsonl", "simulation.vcd", "simulation.wlf"):
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
        mutations = [None, "", "<broken", XML.replace('time="0.2"', 'time="nan"'),
                     XML.replace('sim_time_ns="100"', ''), XML.replace('joypad_contract', 'other'),
                     XML.replace('/></testsuite>', '><failure error_msg="JOYP_MISMATCH" /></testcase></testsuite>'),
                     XML.replace('/></testsuite>', '><error /></testcase></testsuite>'),
                     XML.replace('/></testsuite>', '><skipped /></testcase></testsuite>'),
                     XML.replace('</testsuite>', '<testcase /></testsuite>'),
                     XML.replace('package="all"', 'package="all" errors="1"')]
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

    def test_missing_inventory_not_reusable(self):
        self.run_stage()
        current = self.build / "sim/test/python-joypad/result.json"
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
        self.assertEqual(self.env["LIBPYTHON_LOC"], "libpython.dll")
        self.assertEqual(self.env["PYTHONOPTIMIZE"], "0")

    def test_invalid_configuration_has_no_silent_fallback(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        original = targets["python-joypad"]
        for changes in ({"testbench": "unknown"}, {"testbench": "systemverilog"},
                        {"python": {}}, {"expected_exit": "nonzero"}, {"top": "bad top"},
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
        argv = commands(self.sim, self.root, target, 1, self.build, self.build,
                        prepare=False, vendor_model=vendor, python_runtime=self.runtime)
        runtime = argv[-1][0]
        self.assertIn("-pli", runtime)
        self.assertEqual(runtime[runtime.index("-L") + 1], "n2m_altera_mf")
        self.assertTrue(any("installed model.v" in command for command, *_ in argv))
        for invalid in ({"vendor_model": "intel-adc"}, {"preload": "unknown"},
                        {"preload": "integration"}, {"driver": {}}):
            with self.assertRaises(ValueError):
                python_tb.validate(self.root, {**target, **invalid})

    def test_wave_scope_excludes_recursive_memory_arrays(self):
        python_tb.prepare({}, self.build)
        macro = (self.build / "run.do").read_text()
        self.assertIn("log /*", macro)
        self.assertIn("vcd add /*", macro)
        self.assertNotIn("-r", macro)

    def test_discovery_unavailable_is_explicit(self):
        self.discovery.stop()
        with patch.object(sys, "version_info", (3, 14, 5)):
            with self.assertRaisesRegex(ValueError, "Python 3.12.14"):
                python_tb.discover()
        with patch.object(sys, "version_info", (3, 12, 14)), patch.dict(sys.modules, {"cocotb_tools.config": None}):
            with self.assertRaisesRegex(ValueError, "dependencies unavailable"):
                python_tb.discover()

    def test_warning_classification_is_narrow(self):
        output = WARNING + '\n# ** Note: (vsim-12126) Error and warning message counts have been restored: Errors=0, Warnings=1.\n# Errors: 0, Warnings: 1'
        checked, explained = python_tb.classify(output)
        self.assertEqual(len(explained), 3)
        self.assertIsNone(diagnostic(checked))
        for bad in (output + '\n# ** Warning: another issue', output.replace('Warnings: 1', 'Warnings: 2'), WARNING + '\n' + WARNING, output.replace('switch is', 'switch was')):
            self.assertIsNotNone(diagnostic(python_tb.classify(bad)[0]))


if __name__ == "__main__":
    unittest.main()
