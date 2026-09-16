"""Programming refuses ambiguous identity and unsafe .sof or .pof paths; no hardware needed."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.cli import main
from n2m.fpga_program import attempt_record, program, program_flash
from n2m.records import file_hash
from n2m.progress import Progress

ROOT = Path(__file__).resolve().parents[3]
VALID_CHAIN = "1) USB-Blaster [USB-0]\n  031050DD 10M50DA(.|ES)/10M50DC\n"
AMBIGUOUS_CHAIN = VALID_CHAIN + VALID_CHAIN.replace("1)", "2)")
SUCCESS = "Info: Quartus Prime Programmer was successful. 0 errors, 0 warnings\n"


class FpgaProgramTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/fpga-program-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="program ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.sof = self.write_attempt(self.folder)

    def write_attempt(self, attempt, record=None):
        """A built attempt: output/design.sof listed by hash in result.json beside it."""
        (attempt / "output").mkdir(exist_ok=True)
        sof = attempt / "output/design.sof"
        sof.write_text("not a real bitstream\n")
        if record is None:
            record = {"status": "PASS", "target": "v05-board",
                      "artifacts": {sof.resolve().relative_to(ROOT.resolve()).as_posix(): file_hash(sof)}}
        (attempt / "result.json").write_text(json.dumps(record))
        return sof

    def test_missing_wrong_suffix_or_outside_sof_is_refused(self):
        with self.assertRaises(ValueError):
            program(ROOT, self.folder, self.folder / "missing.sof", quartus_bin="tools")
        wrong_suffix = self.folder / "design.txt"
        wrong_suffix.write_text("x")
        with self.assertRaises(ValueError):
            program(ROOT, self.folder, wrong_suffix, quartus_bin="tools")
        with tempfile.TemporaryDirectory() as outside:
            escaping = Path(outside) / "design.sof"
            escaping.write_text("x")
            with self.assertRaises(ValueError):
                program(ROOT, self.folder, escaping, quartus_bin="tools")

    def test_ambiguous_or_missing_chain_refuses_to_program(self):
        calls = []

        def run(argv, cwd, log, timeout=60):
            calls.append(argv)
            return AMBIGUOUS_CHAIN if "jtagconfig" in argv[0] else SUCCESS

        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            with self.assertRaises(RuntimeError):
                program(ROOT, self.folder, self.sof, quartus_bin="tools")
        self.assertEqual(len(calls), 1, "quartus_pgm must not run after a failed identity check")

    def test_successful_program_reports_cable_and_device(self):
        calls = []

        def run(argv, cwd, log, timeout=60):
            calls.append(argv)
            return VALID_CHAIN if "jtagconfig" in argv[0] else SUCCESS

        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            result = program(ROOT, self.folder, self.sof, quartus_bin="tools")
        self.assertEqual(result["cable"], "1")
        self.assertEqual(result["devices"], ["10M50DA(.|ES)/10M50DC"], "report the chain's own device name")
        self.assertEqual(calls[1][:5], ["quartus_pgm", "-c", "1", "-m", "jtag"])
        self.assertEqual(calls[1][-1], f"p;{self.sof.resolve()}")
        # The path `fpga build` prints is repository-relative; it is recorded resolved.
        relative = Path(os.path.relpath(self.sof, Path.cwd()))
        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            result = program(ROOT, self.folder, relative, quartus_bin="tools")
        self.assertEqual(result["sof"], self.sof.resolve().relative_to(ROOT.resolve()).as_posix())
        self.assertEqual(calls[-1][-1], f"p;{self.sof.resolve()}")

    def test_program_progress_and_launcher_handoff_use_checked_wire_id(self):
        record = json.loads((self.folder / "result.json").read_text())
        record["build_id"] = "00112233445566778899aabbccddeeff"
        (self.folder / "result.json").write_text(json.dumps(record))
        output = io.StringIO()

        def run(argv, cwd, log, timeout=60):
            return VALID_CHAIN if "jtagconfig" in argv[0] else SUCCESS

        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            result = program(ROOT, self.folder, self.sof, quartus_bin="tools",
                             progress=Progress(stream=output))
        self.assertEqual(result["wire_build_id"], "ffeeddccbbaa99887766554433221100")
        self.assertEqual(result["fpga_target"], "v05-board")
        text = output.getvalue()
        ordered = ["[....] Check FPGA build record", "[done] Check FPGA build record",
                   "[....] Discover JTAG chain", "[done] Discover JTAG chain",
                   "JTAG: cable 1; device", "[....] Program FPGA", "[done] Program FPGA",
                   "[....] Check programmer result", "[PASS] Check programmer result"]
        positions = [text.index(fragment) for fragment in ordered]
        self.assertEqual(positions, sorted(positions), text)

    def test_quartus_pgm_failure_output_is_refused(self):
        def run(argv, cwd, log, timeout=60):
            return VALID_CHAIN if "jtagconfig" in argv[0] else "Info: Quartus Prime Programmer failed. 1 error\n"

        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            with self.assertRaises(RuntimeError):
                program(ROOT, self.folder, self.sof, quartus_bin="tools")

    def test_cli_program_action_reports_its_retained_log(self):
        def fake(root, folder, sof, *, quartus_bin, cable, timeout, progress=None):
            (folder / "program.log").write_text("retained\n")
            return {"cable": cable or "1", "sof": str(sof), "scope": "double"}

        with patch("n2m.cli.program_fpga", side_effect=fake) as called, \
                patch("n2m.cli.platform.system", return_value="Windows"):
            code = main(["fpga", "program", "--sof", str(self.sof), "--quartus-bin", "tools",
                         "--tag", "program-cli", "--json"], self.folder)
        self.assertEqual(code, 0)
        self.assertEqual(called.call_args.kwargs["quartus_bin"], "tools")
        self.assertEqual(called.call_args.kwargs["timeout"], 60)
        report = json.loads((self.folder / "workdir/builds/program-cli/manifest.json").read_text())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["scope"], "double")
        self.assertTrue(any(name.endswith("program.log") for name in report["artifacts"]))

    def test_cli_program_action_reports_a_refusal(self):
        with patch("n2m.cli.program_fpga", side_effect=RuntimeError("expected one selected USB-Blaster chain")), \
                patch("n2m.cli.platform.system", return_value="Windows"):
            code = main(["fpga", "program", "--sof", str(self.sof), "--quartus-bin", "tools",
                         "--tag", "program-cli-fail", "--json"], self.folder)
        self.assertEqual(code, 1)
        report = json.loads((self.folder / "workdir/builds/program-cli-fail/manifest.json").read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("USB-Blaster", report["error"])

    def test_early_attempt_refusal_retains_and_surfaces_a_diagnostic(self):
        (self.folder / "result.json").unlink()
        with patch("n2m.fpga_program.execute") as run, \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["fpga", "program", "--sof", str(self.sof),
                         "--quartus-bin", "tools", "--tag", "program-attempt-refusal"],
                        self.folder)
        self.assertEqual(code, 1)
        run.assert_not_called()
        report = json.loads((self.folder / "workdir/builds/program-attempt-refusal/manifest.json").read_text())
        diagnostic = next(name for name in report["artifacts"] if name.endswith("/failure.log"))
        self.assertIn("no readable attempt record", (self.folder / diagnostic).read_text())
        text = output.getvalue()
        self.assertIn("[FAIL] Check FPGA build record", text)
        self.assertIn(f"diagnostic: {diagnostic}", text)
        self.assertIn(f"Diagnostic: {diagnostic}", text)

    def test_cli_text_offers_the_existing_launcher_with_a_uart_placeholder(self):
        target = ["v05-board"]

        def fake(root, folder, sof, *, quartus_bin, cable, timeout, progress=None):
            (folder / "program.log").write_text("retained\n")
            return {"cable": "1", "devices": ["10M50DA(.|ES)/10M50DC"],
                    "sof": str(sof), "program_log": (folder / "program.log").relative_to(root).as_posix(),
                    "wire_build_id": "ffeeddccbbaa99887766554433221100",
                    "fpga_target": target[0], "scope": "double"}

        with patch("n2m.cli.program_fpga", side_effect=fake), \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["fpga", "program", "--sof", str(self.sof),
                         "--quartus-bin", "tools with spaces", "--tag", "program-human"], self.folder)
        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn("On-wire build ID: ffeeddccbbaa99887766554433221100", text)
        self.assertIn("python tools/gb_launcher.py --expected-build-id ffeeddccbbaa99887766554433221100 ", text)
        self.assertIn("--uart-port '<UART-port>'", text)

        target[0] = "controls-board"
        with patch("n2m.cli.program_fpga", side_effect=fake), \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["fpga", "program", "--sof", str(self.sof),
                                   "--quartus-bin", "tools", "--tag", "program-controls"],
                                  self.folder), 0)
        self.assertIn("On-wire build ID:", output.getvalue())
        self.assertNotIn("Next (Windows PowerShell):", output.getvalue())




class AttemptRecordRefusalTests(FpgaProgramTests):
    def refused(self, sof, fragment):
        with patch("n2m.fpga_program.execute") as run:
            with self.assertRaises(ValueError) as caught:
                program(ROOT, self.folder, sof, quartus_bin="tools")
            run.assert_not_called()
        self.assertIn(fragment, str(caught.exception))

    def test_pinned_build_id_sof_is_refused(self):
        listed = json.loads((self.folder / "result.json").read_text())
        (self.folder / "result.json").write_text(json.dumps({**listed, "build_id_override": True}))
        self.refused(self.sof, "comparison-only")

    def test_malformed_producing_target_is_refused(self):
        listed = json.loads((self.folder / "result.json").read_text())
        (self.folder / "result.json").write_text(json.dumps({**listed, "target": "../v05-board"}))
        self.refused(self.sof, "invalid FPGA target")

    def test_missing_or_corrupt_record_is_refused(self):
        (self.folder / "result.json").unlink()
        self.refused(self.sof, "no readable attempt record")
        (self.folder / "result.json").write_text("{not json")
        self.refused(self.sof, "no readable attempt record")
        (self.folder / "result.json").write_text(json.dumps({"status": "PASS"}))
        self.refused(self.sof, "not the artifact")

    def test_copied_or_altered_sof_is_refused(self):
        copied = self.folder / "design.sof"
        copied.write_bytes(self.sof.read_bytes())
        self.refused(copied, "no readable attempt record")
        other = self.folder / "other"
        other.mkdir()
        self.write_attempt(other)
        moved = other / "output/design.sof"
        moved.write_bytes(self.sof.read_bytes() + b"x")
        self.refused(moved, "not the artifact")
        self.assertEqual(attempt_record(ROOT, self.sof)["status"], "PASS")


class FlashProgramTests(unittest.TestCase):
    """The .pof path: the .sof refusals plus the flash evidence rules, dry run and the pvb command."""

    def setUp(self):
        base = ROOT / "workdir/builds/fpga-program-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="flash ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.pof = self.write_attempt(self.folder)

    def write_attempt(self, attempt, edit=None, root=ROOT):
        """A passing flash-proof attempt: output/design.pof listed by hash with its pof evidence."""
        (attempt / "output").mkdir(exist_ok=True)
        pof = attempt / "output/design.pof"
        pof.write_bytes(b"not a real flash image\n")
        record = {"status": "PASS", "target": "flash-proof",
                  "artifacts": {pof.resolve().relative_to(root.resolve()).as_posix(): file_hash(pof)},
                  "evidence": {"onchip_flash": {"configuration_mode": "Single Comp Image",
                                                "pof": {"sha256": file_hash(pof), "user_range_match": True,
                                                        "cfm0_used_bytes": 263216}}}}
        if edit:
            edit(record)
        (attempt / "result.json").write_text(json.dumps(record))
        return pof

    def refused(self, pof, fragment, **kwargs):
        with patch("n2m.fpga_program.execute") as run:
            with self.assertRaises(ValueError) as caught:
                program_flash(ROOT, self.folder, pof, quartus_bin="tools", **kwargs)
            run.assert_not_called()
        self.assertIn(fragment, str(caught.exception))
        self.assertIn(fragment, (self.folder / "failure.log").read_text())

    def rewrite(self, edit):
        record = json.loads((self.folder / "result.json").read_text())
        edit(record)
        (self.folder / "result.json").write_text(json.dumps(record))

    def test_missing_wrong_suffix_symlink_or_outside_pof_is_refused(self):
        self.refused(self.folder / "missing.pof", "missing or unsafe .pof path")
        sof = self.folder / "output/design.sof"
        sof.write_text("x")
        self.refused(sof, "missing or unsafe .pof path")
        link = self.folder / "output/link.pof"
        try:
            link.symlink_to(self.pof)
        except OSError:
            pass  # Windows without the symlink privilege; the link refusal is covered where links exist.
        else:
            self.refused(link, "missing or unsafe .pof path")
        with tempfile.TemporaryDirectory() as outside:
            escaping = Path(outside) / "design.pof"
            escaping.write_text("x")
            self.refused(escaping, "missing or unsafe .pof path")

    def test_missing_record_copied_or_altered_pof_is_refused(self):
        copied = self.folder / "design.pof"
        copied.write_bytes(self.pof.read_bytes())
        self.refused(copied, "no readable attempt record")
        self.pof.write_bytes(self.pof.read_bytes() + b"x")
        self.refused(self.pof, "not the artifact")

    def test_comparison_build_failed_build_and_missing_flash_evidence_are_refused(self):
        self.rewrite(lambda r: r.update(build_id_override=True))
        self.refused(self.pof, "comparison-only")
        self.rewrite(lambda r: r.update(build_id_override=False, status="FAIL"))
        self.refused(self.pof, "did not pass")
        self.rewrite(lambda r: r.update(status="PASS", evidence={}))
        self.refused(self.pof, "no on-chip flash evidence")

    def test_wrong_configuration_mode_or_failed_pof_check_is_refused(self):
        self.rewrite(lambda r: r["evidence"]["onchip_flash"].update(configuration_mode="Single Image"))
        self.refused(self.pof, "configuration mode")
        self.rewrite(lambda r: r["evidence"]["onchip_flash"].update(configuration_mode="Single Comp Image",
                                                                     pof={"sha256": file_hash(self.pof),
                                                                          "user_range_match": False}))
        self.refused(self.pof, "passing .pof check")
        self.rewrite(lambda r: r["evidence"]["onchip_flash"]["pof"].update(user_range_match=True,
                                                                            sha256="0" * 64))
        self.refused(self.pof, "passing .pof check")

    def test_dry_run_writes_the_command_and_touches_no_tool(self):
        with patch("n2m.fpga_program.execute") as run, patch("n2m.fpga_program.executable") as find:
            result = program_flash(ROOT, self.folder, self.pof, quartus_bin="tools", dry_run=True)
            run.assert_not_called()
            find.assert_not_called()
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["command"], ["quartus_pgm", "-c", "<cable>", "-m", "jtag",
                                             "-o", f"pvb;{self.pof.resolve()}"])
        self.assertEqual(result["pof_sha256"], file_hash(self.pof))
        self.assertEqual(result["operation"], "pvb")
        self.assertNotIn("isp_seconds", result)
        self.assertIn(f"pvb;{self.pof.resolve()}", (self.folder / "dry-run.log").read_text())
        with patch("n2m.fpga_program.execute") as run:
            result = program_flash(ROOT, self.folder, self.pof, quartus_bin="tools", cable="2", dry_run=True)
            run.assert_not_called()
        self.assertEqual(result["command"][2], "2")
        # The path `fpga build` prints is relative to the repository; it is recorded resolved.
        relative = Path(os.path.relpath(self.pof, Path.cwd()))
        with patch("n2m.fpga_program.execute") as run:
            result = program_flash(ROOT, self.folder, relative, quartus_bin="tools", dry_run=True)
            run.assert_not_called()
        self.assertEqual(result["pof"], self.pof.resolve().relative_to(ROOT.resolve()).as_posix())
        self.assertEqual(result["attempt_result"], (self.folder / "result.json").resolve().relative_to(ROOT.resolve()).as_posix())

    def test_program_runs_pvb_after_a_single_chain_and_measures_the_time(self):
        calls = []

        def run(argv, cwd, log, timeout=60):
            calls.append((argv, log, timeout))
            return VALID_CHAIN if "jtagconfig" in argv[0] else SUCCESS

        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            result = program_flash(ROOT, self.folder, self.pof, quartus_bin="tools")
        self.assertEqual([call[0][0] for call in calls], ["jtagconfig", "quartus_pgm"])
        self.assertEqual(calls[1][0], ["quartus_pgm", "-c", "1", "-m", "jtag", "-o", f"pvb;{self.pof.resolve()}"])
        self.assertEqual(calls[1][1:], ("program.log", 600))
        self.assertEqual(result["cable"], "1")
        self.assertEqual(result["devices"], ["10M50DA(.|ES)/10M50DC"])
        self.assertEqual(result["chain"]["selected"]["index"], "1")
        self.assertEqual(result["pof_sha256"], file_hash(self.pof))
        self.assertIsInstance(result["isp_seconds"], float)
        self.assertGreaterEqual(result["isp_seconds"], 0)
        self.assertNotIn("build_id", result, "flash-proof carries no identity macro")
        self.assertIn("Power-cycle", result["next_step"])

    def test_ambiguous_chain_or_failed_programmer_refuses(self):
        calls = []

        def ambiguous(argv, cwd, log, timeout=60):
            calls.append(argv)
            return AMBIGUOUS_CHAIN if "jtagconfig" in argv[0] else SUCCESS

        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=ambiguous):
            with self.assertRaises(RuntimeError):
                program_flash(ROOT, self.folder, self.pof, quartus_bin="tools")
        self.assertEqual(len(calls), 1, "quartus_pgm must not run after a failed identity check")

        def failed(argv, cwd, log, timeout=60):
            return VALID_CHAIN if "jtagconfig" in argv[0] else "Info: Quartus Prime Programmer failed. 1 error\n"

        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=failed):
            with self.assertRaises(RuntimeError):
                program_flash(ROOT, self.folder, self.pof, quartus_bin="tools")

    def test_cli_dry_run_records_the_command_without_hardware(self):
        # The CLI treats its root argument as the repository, so the record lists the image relative to it.
        self.write_attempt(self.folder, root=self.folder)
        with patch("n2m.fpga_program.execute") as run, \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["fpga", "program", "--pof", str(self.pof), "--dry-run",
                         "--quartus-bin", "tools", "--tag", "flash-dry-run"], self.folder)
        self.assertEqual(code, 0)
        run.assert_not_called()
        report = json.loads((self.folder / "workdir/builds/flash-dry-run/manifest.json").read_text())
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["command"][-1], f"pvb;{self.pof.resolve()}")
        retained = [name for name in report["artifacts"] if "/fpga-program/" in name]
        self.assertTrue(any(name.endswith("/dry-run.log") for name in retained))
        record = next(name for name in retained if name.endswith("/result.json"))
        self.assertEqual(json.loads((self.folder / record).read_text())["pof_sha256"], file_hash(self.pof))
        text = output.getvalue()
        self.assertIn("FPGA flash program (dry run)", text)
        self.assertIn("[done] Check flash image record", text)
        self.assertIn("Dry run: flash unchanged", text)
        self.assertNotIn("Next:", text)

    def test_cli_refuses_dry_run_with_sof_and_requires_exactly_one_image(self):
        sof = self.folder / "output/design.sof"
        sof.write_text("x")
        with patch("n2m.fpga_program.execute") as run, \
                patch("n2m.cli.platform.system", return_value="Windows"):
            code = main(["fpga", "program", "--sof", str(sof), "--dry-run",
                         "--quartus-bin", "tools", "--tag", "flash-sof-dry", "--json"], self.folder)
        self.assertEqual(code, 1)
        run.assert_not_called()
        report = json.loads((self.folder / "workdir/builds/flash-sof-dry/manifest.json").read_text())
        self.assertIn("--dry-run applies only to --pof", report["error"])
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["fpga", "program", "--sof", str(sof), "--pof", str(self.pof), "--quartus-bin", "tools"],
                     self.folder)
            with self.assertRaises(SystemExit):
                main(["fpga", "program", "--quartus-bin", "tools"], self.folder)

    def test_cli_flash_success_reports_time_hash_and_the_power_cycle_step(self):
        def fake(root, folder, pof, *, quartus_bin, cable, timeout, dry_run, progress=None):
            (folder / "program.log").write_text(SUCCESS)
            return {"cable": "1", "devices": ["10M50DA(.|ES)/10M50DC"], "pof": str(pof),
                    "pof_sha256": "ab" * 32, "isp_seconds": 123.456, "operation": "pvb",
                    "program_log": (folder / "program.log").relative_to(root).as_posix(),
                    "next_step": "Power-cycle the DE10-Lite.", "scope": "double"}

        with patch("n2m.cli.program_flash", side_effect=fake) as called, \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["fpga", "program", "--pof", str(self.pof), "--quartus-bin", "tools",
                         "--tag", "flash-human"], self.folder)
        self.assertEqual(code, 0)
        self.assertEqual(called.call_args.kwargs["timeout"], 600)
        self.assertFalse(called.call_args.kwargs["dry_run"])
        text = output.getvalue()
        self.assertIn("JTAG: cable 1; device 10M50DA", text)
        self.assertIn("Flash programmed, verified and blank-checked in 123.456 s; .pof sha256 " + "ab" * 32, text)
        self.assertIn("Next: Power-cycle the DE10-Lite.", text)
        self.assertNotIn("gb_launcher", text)


if __name__ == "__main__":
    unittest.main()
