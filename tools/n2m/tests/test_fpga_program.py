"""Programming refuses ambiguous identity and unsafe .sof paths; no hardware needed."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.cli import main
from n2m.fpga_program import program

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
        self.sof = self.folder / "design.sof"
        self.sof.write_text("not a real bitstream\n")

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

    def test_quartus_pgm_failure_output_is_refused(self):
        def run(argv, cwd, log, timeout=60):
            return VALID_CHAIN if "jtagconfig" in argv[0] else "Info: Quartus Prime Programmer failed. 1 error\n"

        with patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            with self.assertRaises(RuntimeError):
                program(ROOT, self.folder, self.sof, quartus_bin="tools")

    def test_cli_program_action_reports_its_retained_log(self):
        def fake(root, folder, sof, *, quartus_bin, cable, timeout):
            (folder / "program.log").write_text("retained\n")
            return {"cable": cable or "1", "sof": str(sof), "scope": "double"}

        with patch("n2m.cli.program_fpga", side_effect=fake) as called:
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
        with patch("n2m.cli.program_fpga", side_effect=RuntimeError("expected one selected USB-Blaster chain")):
            code = main(["fpga", "program", "--sof", str(self.sof), "--quartus-bin", "tools",
                         "--tag", "program-cli-fail", "--json"], self.folder)
        self.assertEqual(code, 1)
        report = json.loads((self.folder / "workdir/builds/program-cli-fail/manifest.json").read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("USB-Blaster", report["error"])


if __name__ == "__main__":
    unittest.main()
