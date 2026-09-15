"""Programming refuses ambiguous identity and unsafe .sof paths; no hardware needed."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.cli import main
from n2m.fpga_program import attempt_record, program
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


if __name__ == "__main__":
    unittest.main()
