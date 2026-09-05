"""Independent report fixtures and stage failure/cache checks; no Quartus needed."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import fpga


def reports(folder):
    output = folder / "output"
    output.mkdir(exist_ok=True)
    for name in ("design.map.rpt", "design.fit.rpt", "design.asm.rpt", "design.sta.rpt", "design.sof"):
        (output / name).write_text("retained evidence\n")
    (output / "design.fit.summary").write_text("Fitter Status : Successful\nDevice : 10M50DAF484C7G\nTiming Models : Final\nTotal registers : 8\n")
    (output / "design.sta.summary").write_text('\n'.join(
        f"Type : {corner} Model {kind} 'clk'\nSlack : 0.125\nTNS : 0.000\n"
        for corner in ("Slow 1200mV 85C", "Slow 1200mV 0C", "Fast 1200mV 0C")
        for kind in ("Setup", "Hold", "Minimum Pulse Width")))
    (output / "unconstrained.rpt").write_text('\n'.join(
        f"; {name} ; 0 ; 0 ;" for name in ("Illegal Clocks", "Unconstrained Clocks", "Unconstrained Input Ports",
        "Unconstrained Input Port Paths", "Unconstrained Output Ports", "Unconstrained Output Port Paths")))
    (output / "ignored.rpt").write_text("No constraints were ignored.\n")
    (output / "check_timing.rpt").write_text('\n'.join(f'; {name} ; 0 ;' for name in (
        "no_clock", "multiple_clock", "pos_neg_clock_domain", "generated_clock", "virtual_clock",
        "no_input_delay", "no_output_delay", "partial_input_delay", "partial_output_delay",
        "io_min_max_delay_consistency", "reference_pin", "generated_io_delay", "latency_override",
        "partial_multicycle", "multicycle_consistency", "loops", "latches", "pll_cross_check",
        "uncertainty", "partial_min_max_delay", "clock_assignments_on_output_ports", "input_delay_assigned_to_clock")))


class FpgaTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[3] / "workdir" / "fpga-unit-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="checkout with spaces ", dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = {"device": fpga.DEVICE, "top": "smoke", "sources": ["src/smoke.sv"],
                       "constraints": ["src/smoke.sdc"], "pins": {"clk": "PIN_P11"}, "virtual_pins": ["count[*]"]}
        for name in ("src/smoke.sv", "src/smoke.sdc", "tools/build.py", "tools/n2m/fpga.py"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("owned input\n")
        (self.root / "src/smoke.sdc").write_text('create_clock -name clk -period 20 [get_ports clk]\n')
        self.registry = self.root / fpga.REGISTRY
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.save_target()
        self.build = self.root / "workdir/builds/test"
        self.build.mkdir(parents=True)
        self.args = SimpleNamespace(target="smoke", quartus_bin="explicit tools", timeout=5, rebuild=False)
        self.info = {name: {"path": "explicit tools/" + name, "version": "fixture", "sha256": "tool hash"} for name in fpga.TOOLS}

    def save_target(self):
        self.registry.write_text(json.dumps({"schema_version": 1, "targets": {"smoke": self.target}}))

    def execute(self, argv, folder, log, timeout, record, build):
        record["commands"].append({"argv": argv, "cwd": str(folder), "exit_code": 0})
        log.write_text("Quartus fixture command\n")
        reports(folder)
        return ""

    def run_build(self, execute=None):
        with patch.object(fpga, "tools", return_value=self.info), patch.object(fpga, "execute", side_effect=execute or self.execute):
            return fpga.build_fpga(self.root, self.build, self.args)

    def test_headers_rebuild_and_preserve_external_dependency_rejection(self):
        source = self.root / "src/smoke.sv"
        source.write_text('`include "src/shared.svh"\n')
        header = self.root / "src/shared.svh"
        header.write_text('// first\n')
        self.assertEqual(self.run_build()["cache"], "BUILT")
        self.assertEqual(self.run_build()["cache"], "CACHED")
        header.write_text('// changed\n')
        result = self.run_build()
        self.assertEqual(result["cache"], "BUILT")
        self.assertIn("src/shared.svh", result["inputs"])
        qsf = next(self.build.rglob("design.qsf")).read_text()
        self.assertIn("SEARCH_PATH", qsf)
        self.assertIn('set_global_assignment -name VERILOG_MACRO "SYNTHESIS=1"', qsf)
        for bad in ('$readmemh("memory.hex", storage);', '`include DYNAMIC', '`include "src/missing.svh"'):
            header.write_text(bad)
            self.assertEqual(self.run_build()["status"], "FAIL")

    def test_cache_input_tool_artifact_and_failed_rebuild(self):
        result = self.run_build()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(self.run_build()["cache"], "CACHED")
        for source in ("src/smoke.sv", "src/smoke.sdc", "tools/n2m/fpga.py"):
            with (self.root / source).open("a") as stream:
                stream.write("# changed\n" if source.endswith('.sdc') else "changed\n")
            self.assertEqual(self.run_build()["cache"], "BUILT")
        self.info["quartus_fit"]["sha256"] = "new tool identity"
        result = self.run_build()
        self.assertEqual(result["cache"], "BUILT")
        image = next(name for name in result["artifacts"] if name.endswith(".sof"))
        (self.root / image).write_text("corrupt")
        self.assertEqual(self.run_build()["cache"], "BUILT")
        self.args.rebuild = True
        def failed(*args):
            raise RuntimeError("injected tool failure")
        result = self.run_build(failed)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("injected tool failure", result["error"])
        self.assertEqual(json.loads((self.build / "fpga/smoke/result.json").read_text())["status"], "FAIL")
        self.args.rebuild = False
        self.assertEqual(self.run_build()["cache"], "BUILT")

    def test_missing_tools_and_definition_invalidate_previous_success(self):
        self.run_build()
        with patch.object(fpga, "tools", side_effect=ValueError("missing explicit Quartus tool")):
            result = fpga.build_fpga(self.root, self.build, self.args)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(name.endswith("failure.log") for name in result["artifacts"]))
        self.target["sources"] = ["../escape.sv"]
        self.save_target()
        self.assertEqual(self.run_build()["status"], "FAIL")

    def test_truncated_cache_manifest_cannot_hide_missing_image(self):
        result = self.run_build()
        current = self.build / "fpga/smoke/result.json"
        log = next(name for name in result["artifacts"] if name.endswith("compile.log"))
        truncated = {**result, "artifacts": {log: result["artifacts"][log]}}
        current.write_text(json.dumps(truncated))
        for image in self.build.rglob('*.sof'):
            image.unlink()
        rebuilt = self.run_build()
        self.assertEqual((rebuilt['status'], rebuilt['cache']), ('PASS', 'BUILT'))
        self.assertTrue(any(name.endswith('.sof') for name in rebuilt['artifacts']))
        # Even a corrupt immutable record cannot remove the required inventory.
        truncated = {**rebuilt, "artifacts": {name: value for name, value in rebuilt['artifacts'].items() if not name.endswith('.sof')}}
        current.write_text(json.dumps(truncated))
        (self.root / truncated['attempt_result']).write_text(json.dumps(truncated))
        self.assertEqual(self.run_build()['cache'], 'BUILT')

    def test_nested_namespaced_and_indirect_sdc_loads_are_rejected(self):
        for text in ('if {1} { source extra.sdc }', '::source extra.sdc',
                     'set command source\n$command extra.sdc', 'create_clock -period [exec helper] clk'):
            with self.subTest(text=text):
                (self.root / 'src/smoke.sdc').write_text(text)
                with self.assertRaisesRegex(ValueError, 'unsupported'):
                    fpga.target_definition(self.root, 'smoke')

    def test_report_failures_are_not_success(self):
        mutations = {
            "design.sta.summary": [("Slack : 0.125", "Slack : -0.001"), ("TNS : 0.000", "TNS : -1.000"),
                                   ("Slack : 0.125", "Slack : nan"), ("Slow 1200mV 85C", "Missing corner")],
            "unconstrained.rpt": [("Output Ports ; 0 ;", "Output Ports ; 1 ;")],
            "check_timing.rpt": [("loops ; 0 ;", "loops ; 1 ;"), ("; uncertainty ; 0 ;", "")],
            "ignored.rpt": [("No constraints were ignored.", "Ignored create_clock")],
            "design.fit.summary": [("10M50DAF484C7G", "OTHER_DEVICE"), ("Final", "Preliminary")],
        }
        for name, changes in mutations.items():
            for before, after in changes:
                with self.subTest(name=name, after=after):
                    reports(self.build)
                    file = self.build / "output" / name
                    file.write_text(file.read_text().replace(before, after))
                    with self.assertRaises(ValueError):
                        fpga.timing_evidence(self.build, self.target)
        reports(self.build)
        (self.build / "output/design.sof").unlink()
        with self.assertRaisesRegex(ValueError, "missing FPGA evidence"):
            fpga.timing_evidence(self.build, self.target)

    def test_exact_classification_and_unexplained_diagnostics(self):
        self.assertEqual(fpga.diagnostics(fpga.ALLOCATOR_NOTICE)[0]["code"], "TBBmalloc")
        classified = "Warning (292013): Feature LogicLock is only available with a valid subscription license. You can purchase a software subscription to gain full access to this feature."
        self.assertEqual(fpga.diagnostics(classified)[0]["code"], "292013")
        for text in ("Warning (292013): unexpected license problem", "Critical Warning (332012): ignored clock", "Error (1): failed", "Warning (999): unknown"):
            with self.assertRaises(ValueError):
                fpga.diagnostics(text)

    def test_timeout_retains_partial_output(self):
        record = {"commands": [], "classified_diagnostics": []}
        log = self.build / "timeout.log"
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            fpga.execute([sys.executable, "-u", "-c", "import time; print('before timeout'); time.sleep(30)"],
                         self.build, log, 0.5, record, self.build)
        self.assertIn("before timeout", log.read_text())
        self.assertTrue(record["commands"][0]["timed_out"])

    def test_configuration_quotes_spaces_and_array_pins(self):
        fpga.prepare(self.root, self.build, self.target)
        qsf = (self.build / "design.qsf").read_text()
        self.assertIn('count\\[*\\]', qsf)
        self.assertIn(str(self.root).replace('\\', '/'), qsf)
        self.assertNotIn('quartus_pgm', qsf)


if __name__ == "__main__":
    unittest.main()
