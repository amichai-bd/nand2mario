"""Questa compile gate contracts with controlled tool doubles; not RTL evidence."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import lint
from n2m.cli import LINT_HOST, main, parser
from n2m.doctor import doctor, questa_lint
from n2m.records import read_json
from n2m.simulator import ToolError

ROOT = Path(__file__).resolve().parents[3]
CLEAN = "Errors: 0, Warnings: 0\n"
TOOLS = {name: f"/tools/{name}" for name in ("vlib", "vmap", "vlog", "vopt")}
INFO = {"backend": "questa", "tools": {name: {"path": path, "sha256": "0" * 64, "version": "Questa 2025.2"}
                                        for name, path in TOOLS.items()}}


class FakeTools:
    """Answers each gate command; vlog and vopt transcripts are scripted per label."""

    def __init__(self):
        self.calls = []
        self.vlog = CLEAN
        self.vopt = {}
        self.timeout = None

    def run(self, argv, cwd=None, timeout=60, env=None):
        self.calls.append((argv, cwd, timeout))
        name = Path(argv[0]).name
        if name == self.timeout:
            raise ToolError(f"command failed: {argv}: timed out", "partial transcript")
        if name == "vlib":
            (cwd / argv[1]).mkdir(exist_ok=True)
        if name == "vmap" and "-c" in argv:
            (cwd / "modelsim.ini").write_text("local mappings")
        if name == "vlog":
            output = self.vlog
        elif name == "vopt":
            output = self.vopt.get(argv[argv.index("-work") + 2], CLEAN)
        else:
            output = CLEAN
        code = 2 if "** Error" in output else 0
        return SimpleNamespace(returncode=code, stdout=output)


class LintPlanTests(unittest.TestCase):
    def test_plan_orders_packages_and_maps_every_registered_top(self):
        selected = lint.plan(ROOT)
        sources = selected["sources"]
        packages = [source for source in sources if source.endswith("_pkg.sv")]
        self.assertEqual(sources[:len(packages)], packages)
        self.assertLess(sources.index("src/rtl/interfaces/n2m_interfaces_pkg.sv"),
                        sources.index("src/rtl/memory/n2m_memory_pkg.sv"))
        self.assertEqual(len(set(sources)), len(sources))
        self.assertTrue(all(source.startswith(("src/rtl/", "src/fpga/", "src/dv/builder/")) for source in sources))
        self.assertIn(lint.STAND_INS, sources)
        self.assertNotIn(lint.FAULT, sources)
        registry = json.loads((ROOT / "src/fpga/de10_lite/targets.json").read_text())["targets"]
        self.assertEqual(set(selected["tops"]), {target["top"] for target in registry.values()})
        self.assertEqual(sorted(name for entry in selected["tops"].values() for name in entry["targets"]),
                         sorted(registry))
        for top, entry in selected["tops"].items():
            for name in entry["targets"]:
                self.assertTrue(set(registry[name]["sources"]) <= set(entry["sources"]))
        self.assertIn("src/rtl/common/macros.svh", selected["inputs"])
        self.assertTrue(all(len(digest) == 64 for digest in selected["inputs"].values()))
        faulted = lint.plan(ROOT, inject_fault=True)
        self.assertEqual(faulted["sources"][-1], lint.FAULT)
        self.assertTrue(faulted["tops"][lint.FAULT_TOP]["injected"])

    def test_package_cycle_and_stand_in_drift_fail_before_any_tool(self):
        with tempfile.TemporaryDirectory(prefix="lint plan ") as temporary:
            root = Path(temporary)
            (root / "src/rtl").mkdir(parents=True)
            (root / "src/rtl/a_pkg.sv").write_text("package a_pkg; localparam int X = b_pkg::Y; endpackage\n")
            (root / "src/rtl/b_pkg.sv").write_text("package b_pkg; localparam int Y = a_pkg::X; endpackage\n")
            with self.assertRaisesRegex(ValueError, "cyclic package"):
                lint.package_order(root, ["src/rtl/a_pkg.sv", "src/rtl/b_pkg.sv"])
            (root / "src/rtl/b_pkg.sv").write_text("package b_pkg; // a_pkg:: in a comment\nendpackage\n")
            self.assertEqual(lint.package_order(root, ["src/rtl/a_pkg.sv", "src/rtl/b_pkg.sv", "src/rtl/m.sv"][:2]),
                             ["src/rtl/b_pkg.sv", "src/rtl/a_pkg.sv"])
            shutil.copytree(ROOT / "src/dv/builder", root / "src/dv/builder")
            (root / "src/fpga/de10_lite").mkdir(parents=True)
            shutil.copy(ROOT / "src/fpga/de10_lite/targets.json", root / "src/fpga/de10_lite/targets.json")
            (root / lint.STAND_INS).write_text("module n2m_system_pll(); endmodule\n")
            with self.assertRaisesRegex(ValueError, "must declare exactly"):
                lint.plan(root)

    def test_named_errors_extract_files_and_design_units(self):
        transcript = ("** Error: C:\\clone\\src\\rtl\\common\\n2m_intel_ram.sv(102): Module 'altsyncram' is not defined.\n"
                      "** Error: (vopt-7061) /r/src/dv/builder/questa_lint_fault.sv(9): Variable 'q' driven in an "
                      "always_ff block, may not be driven by any other process.\n"
                      "** Warning: something\nErrors: 2, Warnings: 1\n")
        lines, names = lint.named_errors(transcript)
        self.assertEqual(len(lines), 2)
        self.assertEqual(names, ["altsyncram", "n2m_intel_ram.sv", "questa_lint_fault.sv"])
        self.assertEqual(lint.named_errors(CLEAN), ([], []))


class LintGateTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/lint-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="tools with spaces ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.build = Path(self.temp.name)
        self.tools = FakeTools()
        self.args = SimpleNamespace(questa_bin=None, inject_fault=False)

    def gate(self):
        with patch("n2m.lint.questa_tools", return_value=(TOOLS, INFO)) as discover, \
                patch("n2m.lint.run_tool", side_effect=self.tools.run):
            report = lint.lint_questa(ROOT, self.build, self.args, {"commit": "test"})
        self.assertEqual(discover.call_args.args, (self.args.questa_bin, ("vlib", "vmap", "vlog", "vopt")))
        return report

    def test_pass_records_tools_commands_sources_tops_and_no_vsim(self):
        report = self.gate()
        self.assertEqual(report["status"], "PASS", report.get("error"))
        self.assertEqual(set(report["tools"]), {"vlib", "vmap", "vlog", "vopt"})
        labels = [command["label"] for command in report["commands"]]
        self.assertEqual(labels[:4], ["vmap -c", "vlib", "vmap", "vlog"])
        self.assertEqual(labels[4:], [f"vopt {top}" for top in sorted(report["tops"])])
        self.assertTrue(all(command["exit_code"] == 0 for command in report["commands"]))
        self.assertFalse(any("vsim" in Path(argv[0]).name for argv, _, _ in self.tools.calls))
        vlog = next(command["argv"] for command in report["commands"] if command["label"] == "vlog")
        self.assertEqual(vlog[:4], ["/tools/vlog", "-sv", "-work", "work"])
        self.assertEqual(vlog[4], "+incdir+" + str(ROOT.resolve()))
        self.assertEqual(vlog[5:], [str((ROOT / source).resolve()) for source in report["sources"]])
        self.assertTrue(all(timeout == lint.TOOL_TIMEOUT for _, _, timeout in self.tools.calls))
        attempt = ROOT / report["attempt"]
        self.assertTrue(attempt.is_relative_to(self.build / "lint/questa"))
        self.assertEqual(read_json(ROOT / report["attempt_result"])["status"], "PASS")
        self.assertEqual(len((attempt / "commands.log").read_text().splitlines()), len(report["commands"]))
        for command in report["commands"]:
            self.assertIn(command["log"], report["artifacts"])
        self.assertNotIn("failure", report)
        self.assertNotIn("fault_detected", report)
        self.assertEqual(report["stand_ins"], list(lint.STAND_IN_UNITS))

    def test_vlog_error_fails_by_name_and_stops_before_elaboration(self):
        self.tools.vlog = ("-- Compiling module n2m_cpu\n** Error: (vlog-13069) "
                           + str(ROOT / "src/rtl/cpu/n2m_cpu.sv") + "(12): near \"end\": syntax error.\n"
                           "Errors: 1, Warnings: 0\n")
        report = self.gate()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("vlog: exit 2; names n2m_cpu.sv", report["error"])
        self.assertEqual(report["failure"]["names"], ["n2m_cpu.sv"])
        self.assertEqual(report["failure"]["label"], "vlog")
        self.assertEqual([command["label"] for command in report["commands"]][-1], "vlog")
        self.assertIn(report["failure"]["log"], report["artifacts"])
        self.assertIn("syntax error", (ROOT / report["failure"]["log"]).read_text())

    def test_elaboration_error_names_the_top_and_later_tops_do_not_run(self):
        tops = sorted(lint.fpga_tops(ROOT))
        self.tools.vopt[tops[1]] = ("** Error: (vopt-7061) " + str(ROOT / "src/dv/builder/questa_lint_fault.sv")
                                    + "(9): Variable 'q' driven in an always_ff block.\nErrors: 1, Warnings: 0\n")
        report = self.gate()
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(report["error"].startswith(f"vopt {tops[1]}: exit 2; names questa_lint_fault.sv"))
        self.assertEqual([command["label"] for command in report["commands"]][-1], f"vopt {tops[1]}")

    def test_unexplained_warning_and_timeout_fail(self):
        self.tools.vlog = "** Warning: (vlog-2583) implicit conversion\nErrors: 0, Warnings: 1\n"
        report = self.gate()
        self.assertEqual((report["status"], report["failure"]["problem"]), ("FAIL", "unexplained simulator warning"))
        self.tools.vlog = CLEAN
        self.tools.vopt[sorted(lint.fpga_tops(ROOT))[0]] = "** Note: fine\nErrors: 0, Warnings: 0\n"
        self.assertEqual(self.gate()["status"], "PASS")
        self.tools.vopt.clear()
        self.tools.timeout = "vopt"
        report = self.gate()
        self.assertEqual(report["status"], "FAIL")
        self.assertIsNone(report["commands"][-1]["exit_code"])
        self.assertIn("partial transcript", (ROOT / report["failure"]["log"]).read_text())

    def test_inject_fault_detected_fails_naming_the_fixture(self):
        self.args.inject_fault = True
        self.tools.vopt[lint.FAULT_TOP] = ("** Error (suppressible): " + str(ROOT / lint.FAULT)
                                           + "(10): (vopt-7061) Variable 'q' driven in an always_ff block.\n"
                                           "Errors: 1, Warnings: 0\n")
        report = self.gate()
        self.assertTrue(report["inject_fault"])
        self.assertEqual(report["sources"][-1], lint.FAULT)
        self.assertEqual((report["status"], report["fault_detected"]), ("FAIL", True))
        self.assertTrue(report["error"].startswith(f"vopt {lint.FAULT_TOP}: exit 2; names questa_lint_fault.sv"))
        self.assertEqual(report["commands"][-1]["label"], f"vopt {lint.FAULT_TOP}")

    def test_inject_fault_undetected_is_an_explicit_failure(self):
        self.args.inject_fault = True
        report = self.gate()
        self.assertEqual((report["status"], report["fault_detected"]), ("FAIL", False))
        self.assertEqual(report["error"], f"fault injection not detected: {lint.FAULT} compiled and elaborated clean")
        self.assertIn(f"vopt {lint.FAULT_TOP}", [command["label"] for command in report["commands"]])
        self.assertEqual(read_json(ROOT / report["attempt_result"])["status"], "FAIL")
        # A failure elsewhere is a real failure, not detection of the fixture.
        tops = sorted(lint.fpga_tops(ROOT))
        self.tools.vopt[tops[0]] = "** Error: (vopt-3008) Failed to find design unit 'n2m_missing'.\nErrors: 1, Warnings: 0\n"
        report = self.gate()
        self.assertEqual((report["status"], report["fault_detected"]), ("FAIL", False))
        self.assertTrue(report["error"].startswith(f"vopt {tops[0]}: exit 2; names n2m_missing"))

    def test_plan_is_validated_before_any_tool_probe(self):
        with patch("n2m.lint.plan", side_effect=ValueError("bad plan")), \
                patch("n2m.lint.questa_tools", side_effect=AssertionError("probed")):
            report = lint.lint_questa(ROOT, self.build, self.args, {})
        self.assertEqual((report["status"], report["error"], report["commands"]), ("FAIL", "bad plan", []))
        self.assertNotIn("tools", report)

    def test_discovery_failure_is_recorded(self):
        with patch("n2m.lint.questa_tools", side_effect=ToolError("missing vopt; select the Questa tool directory explicitly")):
            report = lint.lint_questa(ROOT, self.build, self.args, {})
        self.assertEqual((report["status"], report["commands"]), ("FAIL", []))
        self.assertIn("missing vopt", report["error"])
        self.assertEqual(read_json(ROOT / report["attempt_result"])["status"], "FAIL")


class LintCliTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/lint-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="cli root ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, system, *argv, **patches):
        with patch("n2m.cli.platform.system", return_value=system), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.ExitStack() as stack, contextlib.redirect_stdout(io.StringIO()) as output:
            for target, value in patches.items():
                stack.enter_context(patch(target, **value))
            code = main([*argv, "--json"], self.root)
        return code, json.loads(output.getvalue())

    def test_linux_refuses_before_any_workspace(self):
        code, report = self.run_cli("Linux", "lint", "questa", "--tag", "refused",
                                    **{"n2m.cli.lint_questa": {"side_effect": AssertionError("ran")}})
        self.assertEqual(code, 1)
        self.assertEqual((report["status"], report["error"], report["os"]), ("FAIL", LINT_HOST, "Linux"))
        self.assertFalse((self.root / "workdir/builds/refused").exists())

    def test_windows_runs_the_gate_in_its_tagged_workspace_and_exit_follows_status(self):
        for status, code in (("PASS", 0), ("FAIL", 1)):
            with self.subTest(status=status):
                result = {"status": status, "attempt_result": "workdir/builds/gate/lint/questa/x/result.json"}
                exit_code, report = self.run_cli("Windows", "lint", "questa", "--tag", "gate", "--questa-bin", "tools with spaces",
                                                 **{"n2m.cli.lint_questa": {"return_value": result}})
                self.assertEqual(exit_code, code)
                self.assertEqual((report["status"], report["os"], report["requested"]["questa_bin"]),
                                 (status, "Windows", "tools with spaces"))
                self.assertEqual(read_json(self.root / "workdir/builds/gate/manifest.json")["status"], status)
        self.assertEqual((self.root / "workdir/latest.txt").read_text().strip(), "gate")

    def test_parser_accepts_only_the_documented_options(self):
        args = parser().parse_args(["lint", "questa", "--inject-fault", "--questa-bin", "dir", "--tag", "t", "--json"])
        self.assertEqual((args.command, args.action, args.inject_fault, args.questa_bin), ("lint", "questa", True, "dir"))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser().parse_args(["lint", "questa", "--sim", "questa"])
            with self.assertRaises(SystemExit):
                parser().parse_args(["lint", "verilator"])


class LintDoctorTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/lint-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="doctor ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_availability_reports_tools_versions_and_the_command_without_running_it(self):
        def which(candidate):
            return candidate if Path(candidate).name.split(".")[0] in TOOLS else None

        with patch("n2m.simulator.shutil.which", side_effect=which), \
                patch("n2m.simulator.Path.read_bytes", return_value=b"tool"), \
                patch("n2m.doctor.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="Questa 2025.2 vopt\n")) as run:
            report = questa_lint(self.folder, None)
        self.assertEqual(set(report["tools"]), {"vlib", "vmap", "vlog", "vopt"})
        self.assertEqual(set(report["versions"]), {"vmap", "vlog", "vopt"})
        self.assertIn("lint questa", report["command"])
        self.assertEqual(len(run.call_args_list), 3)
        self.assertTrue(all(argv[-1] == "-version" for (argv, *_), _ in run.call_args_list))
        self.assertTrue((self.folder / "vopt-version.log").exists())
        with patch("n2m.simulator.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "missing vlib"):
                questa_lint(self.folder, None)

    def test_questa_doctor_adds_the_gate_availability_check(self):
        args = parser().parse_args(["doctor", "--sim", "questa"])
        with patch("n2m.doctor.questa", return_value={"tools": {"vsim": "fixture"}}), \
                patch("n2m.doctor.questa_lint", return_value={"command": "lint questa"}) as availability:
            report = doctor(ROOT, self.folder, args, {})
        availability.assert_called_once()
        self.assertEqual(set(report["checks"]), {"questa", "questa-lint"})
        self.assertEqual((report["status"], report["checks"]["questa-lint"]["status"]), ("PASS", "PASS"))
        with patch("n2m.doctor.questa", side_effect=RuntimeError("license checkout failed")), \
                patch("n2m.doctor.questa_lint", return_value={}):
            report = doctor(ROOT, self.folder, args, {})
        self.assertEqual((report["status"], report["checks"]["questa-lint"]["status"]), ("FAIL", "PASS"))
        args = parser().parse_args(["doctor", "--sim", "verilator"])
        with patch("n2m.doctor.verilator", return_value={}), patch("n2m.doctor.questa_lint") as availability:
            doctor(ROOT, self.folder, args, {})
        availability.assert_not_called()


if __name__ == "__main__":
    unittest.main()
