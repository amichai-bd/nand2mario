"""Independent report fixtures and stage failure/cache checks; no Quartus needed."""
import contextlib
import io
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import fpga
from n2m.cli import main
from n2m.progress import Progress


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

    def test_build_id_override_is_comparison_only(self):
        self.args.build_id = "ab" * 16
        result = self.run_build()
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("identity macro", result["error"])
        del self.args.build_id
        with patch.object(fpga.fpga_v05, "board_target", return_value=True), \
                patch.object(fpga, "prepare") as prepare, patch.object(fpga, "timing_evidence", return_value={"ok": 1}):
            plain = self.run_build()
            self.assertEqual((plain["status"], plain["build_id"]), ("PASS", plain["fingerprint"][:32]))
            self.assertNotIn("build_id_override", plain)
            self.args.build_id = "ab" * 16
            pinned = self.run_build()
            self.assertEqual((pinned["status"], pinned["cache"], pinned["build_id"]), ("PASS", "BUILT", "ab" * 16))
            self.assertTrue(pinned["build_id_override"])
            self.assertIn(fpga.BUILD_ID_OVERRIDE_NOTICE, pinned["notices"])
            self.assertNotEqual(pinned["fingerprint"], plain["fingerprint"])
            self.assertEqual(prepare.call_args.kwargs["build_id"], "ab" * 16)
            for bad in ("AB" * 16, "0" * 32, "ab" * 15):
                self.args.build_id = bad
                self.assertEqual(self.run_build()["status"], "FAIL")
            del self.args.build_id
            again = self.run_build()
            self.assertEqual((again["status"], again["build_id"]), ("PASS", plain["fingerprint"][:32]))
            self.assertNotIn("build_id_override", again)

    def test_struct_member_ports_are_bounded_names(self):
        self.target["virtual_pins"] = ["request.read", "request.pair[*]", "response.data[0]"]
        self.save_target()
        self.assertEqual(fpga.target_definition(self.root,"smoke")["virtual_pins"],self.target["virtual_pins"])
        for port in ("request..read", "request.*", "request.read;source bad", "request.read\nsource bad"):
            self.target["virtual_pins"] = [port]
            self.save_target()
            with self.subTest(port=port),self.assertRaises(ValueError):
                fpga.target_definition(self.root,"smoke")

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

    def test_non_pll_memory_consumer_pins_model_and_requires_netlist(self):
        source = "src/rtl/common/n2m_intel_ram.sv"
        path = self.root / source
        path.parent.mkdir(parents=True)
        path.write_text("// explicit shared memory consumer\n")
        self.target["sources"].append(source)
        self.save_target()
        def execute(argv, folder, log, timeout, record, build):
            self.execute(argv, folder, log, timeout, record, build)
            if "--simulation" in argv:
                netlist = folder / "simulation/questa/design.vo"
                netlist.parent.mkdir(parents=True, exist_ok=True)
                netlist.write_text("module design; endmodule\n")
        with patch.object(fpga.fpga_intel_memory, "identity", return_value={"primitive": {"sha256": "pinned"}}) as identity:
            result = self.run_build(execute)
            self.assertEqual(result["status"], "PASS", result)
            identity.assert_called_once_with(self.args.quartus_bin)
            self.assertEqual(result["tools"]["altsyncram"]["primitive"]["sha256"], "pinned")
            self.assertTrue(any("--simulation" in c["argv"] for c in result["commands"]))
            self.assertEqual(self.run_build(execute)["cache"], "CACHED")
            # A truncated inventory in both records cannot authorize a hit.
            current = self.build / "fpga/smoke/result.json"
            record = json.loads(current.read_text())
            netlist = next(p for p in record["artifacts"] if p.endswith("design.vo"))
            (self.root / netlist).unlink()
            del record["artifacts"][netlist]
            current.write_text(json.dumps(record))
            (self.root / record["attempt_result"]).write_text(json.dumps(record))
            self.assertEqual(self.run_build(execute)["cache"], "BUILT")
        with patch.object(fpga.fpga_intel_memory, "identity", side_effect=ValueError("model identity mismatch")):
            result = self.run_build(execute)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("model identity mismatch", result["error"])

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

    def test_v05_generated_design_diagnostics_are_exact_and_retained(self):
        database = self.build / "db"
        database.mkdir()
        suffix = (", which is not specified as a design file for the current project, "
                  "but contains definitions for 1 design units and 1 entities in project")
        lines = []
        for name in fpga.GENERATED_DESIGN_FILES:
            (database / name).write_text("generated\n")
            lines.append(f"Warning (12125): Using design file db/{name}{suffix}")
        output = "\n".join(reversed(lines))
        explained = fpga.generated_design_diagnostics(output, self.build)
        self.assertEqual([item["text"] for item in explained], list(reversed(lines)))
        self.assertEqual([item["code"] for item in fpga.diagnostics(output, explained)],
                         ["12125"] * len(lines))
        self.assertEqual(fpga.generated_design_diagnostics("", self.build), [])

        mutations = (
            output.replace("db/n2m_system_pll_altpll.v", "other/n2m_system_pll_altpll.v", 1),
            output.replace("db/n2m_system_pll_altpll.v", "db/other_altpll.v", 1),
            output.replace("1 design units", "2 design units", 1),
            output.replace("1 entities", "2 entities", 1),
            output + "\n" + lines[0],
            "\n".join(output.splitlines()[1:]),
        )
        for changed in mutations:
            with self.subTest(changed=changed[:100]), self.assertRaisesRegex(
                    ValueError, "path, count, or text differs"):
                fpga.generated_design_diagnostics(changed, self.build)

        linked = self.build / "linked-attempt"
        linked.mkdir()
        (linked / "db").symlink_to(database, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "owned attempt directory"):
            fpga.generated_design_diagnostics(output, linked)

        (database / fpga.GENERATED_DESIGN_FILES[0]).unlink()
        with self.assertRaisesRegex(ValueError, "owned database output"):
            fpga.generated_design_diagnostics(output, self.build)

    def test_12125_remains_unclassified_outside_v05_compile(self):
        warning = ("Warning (12125): Using design file db/n2m_system_pll_altpll.v, which is not "
                   "specified as a design file for the current project, but contains definitions "
                   "for 1 design units and 1 entities in project")
        with self.assertRaisesRegex(ValueError, "unexplained Quartus diagnostic"):
            fpga.diagnostics(warning)

    def test_timeout_retains_partial_output(self):
        record = {"commands": [], "classified_diagnostics": []}
        log = self.build / "timeout.log"
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            fpga.execute([sys.executable, "-u", "-c", "import time; print('before timeout'); time.sleep(30)"],
                         self.build, log, 0.5, record, self.build)
        self.assertIn("before timeout", log.read_text())
        self.assertTrue(record["commands"][0]["timed_out"])
        self.assertTrue(record['commands'][0]['cleanup_complete'])

    def test_execute_retains_merged_raw_output_and_exit(self):
        record = {'commands': [], 'classified_diagnostics': []}
        log = self.build / 'raw.log'
        code = ("import os,stat; assert stat.S_ISREG(os.fstat(1).st_mode); "
                "os.write(1,b'out\\r\\n'); os.write(2,b'err\\xff\\n')")
        text = fpga.execute([sys.executable, '-c', code], self.build, log, 5, record, self.build)
        self.assertEqual(log.read_bytes(), b'out\r\nerr\xff\n')
        self.assertEqual(text, 'out\r\nerr\ufffd\n')
        self.assertEqual(record['commands'][-1]['exit_code'], 0)
        with self.assertRaisesRegex(RuntimeError, 'Quartus exit 7'):
            fpga.execute([sys.executable, '-c', "print('failed'); raise SystemExit(7)"],
                         self.build, log, 5, record, self.build)
        self.assertEqual(record['commands'][-1]['exit_code'], 7)
        self.assertIn('failed', log.read_text())

    def test_generator_execute_retries_only_the_silent_exit_three(self):
        counter = self.build / 'attempts.txt'
        script = ("import sys, pathlib; p = pathlib.Path(sys.argv[1]); n = int(p.read_text()) + 1 if p.exists() else 1; "
                  "p.write_text(str(n)); sys.exit(3 if n < int(sys.argv[2]) else 0)")
        record = {'commands': [], 'classified_diagnostics': []}
        log = self.build / 'generate-pll.log'
        fpga.generator_execute([sys.executable, '-c', script, str(counter), '3'], self.build, log, 5, record, self.build)
        self.assertEqual([c['exit_code'] for c in record['commands']], [3, 3, 0])
        self.assertEqual([c.get('retried') for c in record['commands']], [True, True, None])
        self.assertEqual([(r['attempt'], r['exit_code'], r['log']) for r in record['generator_retries']],
                         [(1, 3, 'generate-pll.log'), (2, 3, 'generate-pll.log')])
        counter.unlink()
        record = {'commands': [], 'classified_diagnostics': []}
        with self.assertRaisesRegex(RuntimeError, 'Quartus exit 3'):
            fpga.generator_execute([sys.executable, '-c', script, str(counter), '9'], self.build, log, 5, record, self.build)
        self.assertEqual([c['exit_code'] for c in record['commands']], [3] * fpga.GENERATOR_ATTEMPTS)
        self.assertEqual(len(record['generator_retries']), fpga.GENERATOR_ATTEMPTS - 1)
        for code in ("print('generator diagnostic'); raise SystemExit(3)", "raise SystemExit(7)"):
            record = {'commands': [], 'classified_diagnostics': []}
            with self.assertRaises(RuntimeError):
                fpga.generator_execute([sys.executable, '-c', code], self.build, log, 5, record, self.build)
            self.assertEqual(len(record['commands']), 1, 'a reported or different failure is not retried')
            self.assertNotIn('generator_retries', record)

    def test_execute_sets_the_allocator_override_for_the_child_only(self):
        record = {'commands': [], 'classified_diagnostics': []}
        log = self.build / 'environment.log'
        before = os.environ.get('TBB_MALLOC_DISABLE_REPLACEMENT')
        code = "import os; print('child=' + repr(os.environ.get('TBB_MALLOC_DISABLE_REPLACEMENT')))"
        with patch.dict(os.environ, {'N2M_PARENT_MARKER': 'kept'}):
            text = fpga.execute([sys.executable, '-c', code], self.build, log, 5, record, self.build)
            self.assertIn("child='1'", text, 'the launched process must see the documented override')
        self.assertEqual(os.environ.get('TBB_MALLOC_DISABLE_REPLACEMENT'), before, 'the host environment is unchanged')
        self.assertEqual(record['commands'][-1]['environment'], {'TBB_MALLOC_DISABLE_REPLACEMENT': '1'})
        self.assertEqual(fpga.quartus_environment({'PATH': 'kept'}),
                         {'PATH': 'kept', 'TBB_MALLOC_DISABLE_REPLACEMENT': '1'})

    def test_build_reports_the_allocator_override_in_its_record(self):
        result = self.run_build()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['environment'], {'TBB_MALLOC_DISABLE_REPLACEMENT': '1'})
        self.assertEqual(result['notices'], [fpga.ALLOCATOR_OVERRIDE_NOTICE])
        self.assertIn('TBB_MALLOC_DISABLE_REPLACEMENT=1', fpga.ALLOCATOR_OVERRIDE_NOTICE)
        attempt = json.loads((self.root / result['attempt_result']).read_text())
        self.assertEqual(attempt['notices'], result['notices'])

    def test_build_progress_names_real_and_cached_stages(self):
        output = io.StringIO()
        with patch.object(fpga, "tools", return_value=self.info), \
                patch.object(fpga, "execute", side_effect=self.execute):
            result = fpga.build_fpga(self.root, self.build, self.args,
                                     progress=Progress(stream=output))
        self.assertEqual(result["status"], "PASS")
        text = output.getvalue()
        ordered = ["[....] Discover Quartus tools", "[done] Discover Quartus tools",
                   "[....] Check FPGA cache", "[done] Check FPGA cache",
                   "[....] Compile, fit, assemble, and time",
                   "[done] Compile, fit, assemble, and time",
                   "[....] Audit timing and constraints", "[done] Audit timing and constraints",
                   "[....] Check FPGA result", "[PASS] Check FPGA result"]
        positions = [text.index(fragment) for fragment in ordered]
        self.assertEqual(positions, sorted(positions), text)
        output = io.StringIO()
        with patch.object(fpga, "tools", return_value=self.info), \
                patch.object(fpga, "execute", side_effect=self.execute):
            cached = fpga.build_fpga(self.root, self.build, self.args,
                                     progress=Progress(stream=output))
        self.assertEqual(cached["cache"], "CACHED")
        self.assertIn("[CACHED] Compile, fit, assemble, and time — reused checked result",
                      output.getvalue())

    def test_auxiliary_identity_failure_fails_quartus_discovery_stage(self):
        source = self.root / "src/rtl/common/n2m_intel_ram.sv"
        source.parent.mkdir(parents=True)
        source.write_text("module n2m_intel_ram; endmodule\n")
        self.target["sources"].append("src/rtl/common/n2m_intel_ram.sv")
        self.save_target()
        output = io.StringIO()
        with patch.object(fpga, "tools", return_value=self.info), \
                patch.object(fpga.fpga_intel_memory, "identity",
                             side_effect=RuntimeError("missing altsyncram identity")):
            result = fpga.build_fpga(self.root, self.build, self.args,
                                     progress=Progress(stream=output))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("altsyncram identity", result["error"])
        text = output.getvalue()
        self.assertIn("[FAIL] Discover Quartus tools", text)
        self.assertNotIn("[done] Discover Quartus tools", text)

    def test_cli_text_output_prints_the_override_notice(self):
        comparison = [False]
        status = ["PASS"]

        def fake(root, build, args, provenance=None, progress=None):
            bitstream = "workdir/builds/notice/fpga/smoke/attempts/path with spaces/output/design.sof"
            return {"status": status[0], "cache": "BUILT", "attempt_result": "result.json",
                    "artifacts": {bitstream: "hash"},
                    "build_id_override": comparison[0],
                    "notices": [fpga.ALLOCATOR_OVERRIDE_NOTICE]}

        with patch("n2m.cli.build_fpga", side_effect=fake), patch("n2m.cli.git_state", return_value={}), \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["fpga", "build", "smoke", "--quartus-bin", "tools with spaces",
                         "--tag", "notice"], self.root)
        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn(fpga.ALLOCATOR_OVERRIDE_NOTICE, text.splitlines())
        self.assertIn("Checked bitstream: workdir/builds/notice/fpga/smoke/attempts/path with spaces/output/design.sof", text)
        self.assertIn("--sof 'workdir/builds/notice/fpga/smoke/attempts/path with spaces/output/design.sof'", text)
        self.assertIn("--quartus-bin 'tools with spaces'", text)

        comparison[0] = True
        with patch("n2m.cli.build_fpga", side_effect=fake), patch("n2m.cli.git_state", return_value={}), \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["fpga", "build", "smoke", "--quartus-bin", "tools",
                                   "--tag", "notice-comparison"], self.root), 0)
        self.assertNotIn("Next (Windows PowerShell):", output.getvalue())

        comparison[0] = False
        status[0] = "FAIL"
        with patch("n2m.cli.build_fpga", side_effect=fake), patch("n2m.cli.git_state", return_value={}), \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["fpga", "build", "smoke", "--quartus-bin", "tools",
                                   "--tag", "notice-failed"], self.root), 1)
        text = output.getvalue()
        self.assertIn("Unverified bitstream artifact:", text)
        self.assertNotIn("Checked bitstream:", text)
        self.assertNotIn("Next (Windows PowerShell):", text)

    def test_execute_keeps_unexplained_warning_failure(self):
        record = {'commands': [], 'classified_diagnostics': []}
        log = self.build / 'warning.log'
        with self.assertRaises(ValueError):
            fpga.execute([sys.executable, '-c', "print('Warning (999): unexpected')"],
                         self.build, log, 5, record, self.build)
        self.assertIn('Warning (999)', log.read_text())
        self.assertEqual(record['commands'][-1]['exit_code'], 0)

    @unittest.skipUnless(os.name == 'nt', 'Windows owned-tree cleanup')
    def test_timeout_reaps_descendant(self):
        # One prompt descendant, then a parent that keeps spawning every 5 ms
        # so some spawns land while cleanup starts. taskkill /T walks a process
        # snapshot and left 19-23 of those alive per run; the job reaps them all.
        spawn = "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])"
        for name, code in (("prompt", f"import subprocess,sys,time; p={spawn}; print(p.pid,flush=True); time.sleep(30)"),
                           ("continuous", "import subprocess,sys,time\nwhile True:\n"
                                          f"    print({spawn}.pid,flush=True); time.sleep(0.005)")):
            with self.subTest(name):
                self.assert_descendants_reaped(code)

    def assert_descendants_reaped(self, code):
        import ctypes
        record = {'commands': [], 'classified_diagnostics': []}
        log = self.build / 'descendant.log'
        with self.assertRaisesRegex(RuntimeError, 'timeout'):
            fpga.execute([sys.executable, '-u', '-c', code], self.build, log, 1, record, self.build)
        self.assertTrue(record['commands'][-1]['cleanup_complete'])
        pids = [int(line) for line in log.read_text().split()]
        self.assertTrue(pids, 'the parent must report at least one child')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        alive = []
        for pid in pids:
            handle = kernel.OpenProcess(0x100000, False, pid)
            if not handle:
                continue  # the pid is gone or reused; nothing of ours to wait on
            try:
                # Cleanup already waited for the job to report no active process;
                # a bounded wait tolerates the kernel finishing the exited object
                # under host load while still proving the pid is dead, not merely
                # that a timer expired (258 would be WAIT_TIMEOUT, a live pid).
                if kernel.WaitForSingleObject(handle, 5000) != 0:
                    alive.append(pid)
            finally:
                kernel.CloseHandle(handle)
        self.assertEqual(alive, [], f'{len(alive)} of {len(pids)} descendants survived cleanup')

    @unittest.skipUnless(os.name == 'nt', 'Windows cleanup failure branch')
    def test_cleanup_failure_is_bounded_and_not_success(self):
        record = {'commands': [], 'classified_diagnostics': []}
        log = self.build / 'cleanup.log'
        with patch.object(fpga.process_tree, 'Tree') as launch:
            tree = launch.return_value.__enter__.return_value
            process = tree.process
            process.wait.side_effect = [subprocess.TimeoutExpired('tool', 1), None]
            process.returncode = 1
            tree.terminate.side_effect = subprocess.TimeoutExpired('tool', 5)
            with self.assertRaisesRegex(RuntimeError, 'cleanup incomplete'):
                fpga.execute(['tool'], self.build, log, 1, record, self.build)
            self.assertEqual(tree.terminate.call_args.kwargs['timeout'], 5)
            self.assertEqual(process.wait.call_args.kwargs['timeout'], 2)
            process.kill.assert_called_once()
            self.assertFalse(record['commands'][-1]['cleanup_complete'])
        self.assertTrue(log.exists())

    def test_configuration_quotes_spaces_and_array_pins(self):
        fpga.prepare(self.root, self.build, self.target)
        qsf = (self.build / "design.qsf").read_text()
        self.assertIn('count\\[*\\]', qsf)
        self.assertIn(str(self.root).replace('\\', '/'), qsf)
        self.assertNotIn('quartus_pgm', qsf)


if __name__ == "__main__":
    unittest.main()
