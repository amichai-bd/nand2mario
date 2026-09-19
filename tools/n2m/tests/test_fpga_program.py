"""Programming refuses ambiguous identity and unsafe .sof or .pof paths; no hardware needed.

Every programmer here is a fake: tool discovery is patched to name the
programmers a host is supposed to have, and execution is patched to return the
chain and programmer output a board would. No test opens a cable.
"""
import contextlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.cli import main
from n2m import fpga, fpga_jtag, fpga_program
from n2m.fpga_program import attempt_record, device_state_after, program, program_flash, repository_relative
from n2m.records import file_hash
from n2m.progress import Progress

ROOT = Path(__file__).resolve().parents[3]
VALID_CHAIN = "1) USB-Blaster [USB-0]\n  031050DD 10M50DA(.|ES)/10M50DC\n"
AMBIGUOUS_CHAIN = VALID_CHAIN + VALID_CHAIN.replace("1)", "2)")
SUCCESS = "Info: Quartus Prime Programmer was successful. 0 errors, 0 warnings\n"
FAILED = "Info: Quartus Prime Programmer failed. 1 error\n"
# The measured jtagconfig failure on the Linux host: both cables answer, neither
# chain is read, and the two cables fail differently.
UNREADABLE_CHAIN = ("1) DE-SoC [1-3.2]      Unable to read device chain - Hardware not attached\n"
                    "2) USB-Blaster [1-2]   Unable to read device chain - JTAG chain broken\n")
# `openFPGALoader --detect` on the DE10-Nano: the ARM debug access port of the
# Cyclone V SoC sits at chain position 0 and the FPGA at position 1.
NANO_DETECT = ("index 0:\n\tidcode   0x4ba00477\n\ttype     Cortex A9\n\tirlength 4\n"
               "index 1:\n\tidcode 0x2d020dd\n\tmanufacturer altera\n\tfamily cyclone V Soc\n"
               "\tmodel  5CSE*A6/5CSX*6\n\tirlength 10\n")
# The same probe with its FX2 firmware wedged: openFPGALoader exits successfully
# and reports thirty-two identical Lattice parts. Measured on the host, kept as
# the reason a successful exit proves nothing about the chain.
WEDGED_DETECT = "".join(f"index {i}:\n\tidcode 0x81111043\n\tmanufacturer lattice\n\tfamily ECP5\n"
                        "\tmodel  LFE5UM5G-25\n\tirlength 8\n" for i in range(32))
LOADED = ("Load SRAM: [==================================================] 100.00%\nDone\n")
LOAD_FAILED = ("Load SRAM: [=========                                         ] 18.00%\nFail\n")
CONVERTED = "Info: Quartus Prime Convert_programming_file was successful. 0 errors, 0 warnings\n"
# openFPGALoader on a cable that is not attached: it fails and says so.
ABSENT_CABLE = "unable to open ftdi device: -3 (device not found)\nempty\nJTAG init failed with: std::exception\n"


def stage_registry(root):
    """Copy the board registries and the specifications they link into a fake checkout root.

    `program` reads the expected device from the registry under its `root`, so a
    test that stands a temporary directory in for the repository stages the same
    files the repository has.
    """
    for name in fpga.REGISTRIES:
        source = ROOT / name
        staged = Path(root) / name
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, staged)
        specification = Path(root) / json.loads(source.read_text())["board"]["specification"]
        specification.parent.mkdir(parents=True, exist_ok=True)
        specification.write_text("staged board specification\n", encoding="utf-8")


def fake_programmers(*, quartus=True, openfpgaloader=False):
    """Tool discovery finding only the programmers a host is supposed to have."""
    present = {"jtagconfig": quartus, "quartus_pgm": quartus, "quartus_cpf": quartus,
               "openFPGALoader": openfpgaloader}
    return patch("n2m.fpga_jtag.locate", side_effect=lambda d, n: n if present.get(n) else None)
# The reported recreation: a Windows PowerShell session inside a WSL checkout reached over UNC.
UNC_ROOT = PureWindowsPath(r"\\wsl.localhost\Ubuntu\home\abendavid\github\nand2mario")
UNC_SOF = UNC_ROOT / r"workdir\builds\stackdrop-program-34ed4f\output\design.sof"


class FpgaProgramTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/fpga-program-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="program ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        stage_registry(self.folder)
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

        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            with self.assertRaises(RuntimeError):
                program(ROOT, self.folder, self.sof, quartus_bin="tools")
        self.assertEqual(len(calls), 1, "quartus_pgm must not run after a failed identity check")

    def test_successful_program_reports_cable_and_device(self):
        calls = []

        def run(argv, cwd, log, timeout=60):
            calls.append(argv)
            return VALID_CHAIN if "jtagconfig" in argv[0] else SUCCESS

        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            result = program(ROOT, self.folder, self.sof, quartus_bin="tools")
        self.assertEqual(result["cable"], "1")
        self.assertEqual(result["devices"], ["10M50DA(.|ES)/10M50DC"], "report the chain's own device name")
        self.assertEqual(calls[1][:5], ["quartus_pgm", "-c", "1", "-m", "jtag"])
        self.assertEqual(calls[1][-1], f"p;{self.sof.resolve()}")
        # The path `fpga build` prints is repository-relative; it is recorded resolved.
        relative = Path(os.path.relpath(self.sof, Path.cwd()))
        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
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

        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            result = program(ROOT, self.folder, self.sof, quartus_bin="tools",
                             progress=Progress(stream=output))
        self.assertEqual(result["wire_build_id"], "ffeeddccbbaa99887766554433221100")
        self.assertEqual(result["fpga_target"], "v05-board")
        text = output.getvalue()
        ordered = ["[....] Check FPGA build record", "[done] Check FPGA build record",
                   "[....] Discover JTAG chain", "[done] Discover JTAG chain",
                   "JTAG: backend quartus; cable 1; device", "[....] Program FPGA", "[done] Program FPGA",
                   "[....] Check programmer result", "[PASS] Check programmer result"]
        positions = [text.index(fragment) for fragment in ordered]
        self.assertEqual(positions, sorted(positions), text)

    def test_quartus_pgm_failure_output_is_refused(self):
        def run(argv, cwd, log, timeout=60):
            return VALID_CHAIN if "jtagconfig" in argv[0] else "Info: Quartus Prime Programmer failed. 1 error\n"

        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            with self.assertRaises(RuntimeError):
                program(ROOT, self.folder, self.sof, quartus_bin="tools")

    def test_cli_program_action_reports_its_retained_log(self):
        def fake(root, folder, sof, *, quartus_bin, cable, timeout, progress=None, **options):
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
        self.assertEqual(report["device_state"], "unchanged", "quartus_pgm never ran")
        text = output.getvalue()
        self.assertIn("[FAIL] Check FPGA build record", text)
        self.assertIn(f"diagnostic: {diagnostic}", text)
        self.assertIn(f"Diagnostic: {diagnostic}", text)

    def test_cli_text_offers_the_existing_launcher_with_a_uart_placeholder(self):
        target = ["v05-board"]

        def fake(root, folder, sof, *, quartus_bin, cable, timeout, progress=None, **options):
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


class PortableRecordPathTests(unittest.TestCase):
    """Record paths stay repository-relative for the UNC recreation; pure paths, so no Windows host is needed."""

    def test_unc_root_with_windows_separators_records_a_posix_relative_path(self):
        self.assertEqual(repository_relative(UNC_ROOT, UNC_SOF),
                         "workdir/builds/stackdrop-program-34ed4f/output/design.sof")
        self.assertEqual(repository_relative(UNC_ROOT, UNC_ROOT / "workdir/builds/t/output/design.pof"),
                         "workdir/builds/t/output/design.pof")
        # Windows resolves both sides through the same share; a differently cased share is the same anchor.
        upper = PureWindowsPath(r"\\WSL.LOCALHOST\Ubuntu\home\abendavid\github\nand2mario\workdir\builds\t\output\design.sof")
        self.assertEqual(repository_relative(UNC_ROOT, upper), "workdir/builds/t/output/design.sof")

    def test_components_with_spaces_and_drive_roots_are_recorded_the_same_way(self):
        root = PureWindowsPath(r"\\wsl.localhost\Ubuntu\home\a b\nand2mario")
        self.assertEqual(repository_relative(root, root / r"workdir\builds\program x\output\design.pof"),
                         "workdir/builds/program x/output/design.pof")
        drive = PureWindowsPath(r"C:\Users\abendavid\n2m 673")
        self.assertEqual(repository_relative(drive, PureWindowsPath("C:/Users/abendavid/n2m 673/workdir/builds/t/output/design.sof")),
                         "workdir/builds/t/output/design.sof")
        posix = Path("/home/abendavid/github/nand2mario")
        self.assertEqual(repository_relative(posix, posix / "workdir/builds/program x/output/design.sof"),
                         "workdir/builds/program x/output/design.sof")

    def test_unlocated_or_foreign_paths_are_refused_not_guessed(self):
        # The reported failure: the Windows-relative input string measured against the UNC root.
        with self.assertRaises(ValueError):
            repository_relative(UNC_ROOT, PureWindowsPath(r"workdir\builds\stackdrop-program-34ed4f\output\design.sof"))
        with self.assertRaises(ValueError):
            repository_relative(UNC_ROOT, PureWindowsPath(r"\\wsl.localhost\Debian\home\abendavid\github\nand2mario\workdir\x.sof"))
        with self.assertRaises(ValueError):  # a sibling checkout that merely shares the name prefix
            repository_relative(UNC_ROOT, PureWindowsPath(r"\\wsl.localhost\Ubuntu\home\abendavid\github\nand2mario-old\workdir\x.sof"))
        with self.assertRaises(TypeError):  # strings would be re-flavoured by the host; only path objects are accepted
            repository_relative(str(UNC_ROOT), str(UNC_SOF))

    def test_device_state_reads_the_retained_program_log(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(device_state_after(folder), "unchanged")
            (Path(folder) / "program.log").write_text(FAILED)
            self.assertEqual(device_state_after(folder), "unconfirmed")
            (Path(folder) / "program.log").write_text(SUCCESS)
            self.assertEqual(device_state_after(folder), "changed")


class PostProgramRecordTests(FpgaProgramTests):
    """After one affirmative quartus_pgm the record finishes from precomputed paths; failures name the device state."""

    def ordered_calls(self, run_program):
        """Names of the path derivations and tool runs in the order the program function makes them."""
        order = []
        relative = fpga_program.repository_relative

        def traced(root, path):
            order.append("relative")
            return relative(root, path)

        def run(argv, cwd, log, timeout=60):
            order.append(argv[0])
            return VALID_CHAIN if "jtagconfig" in argv[0] else SUCCESS

        with fake_programmers(), patch("n2m.fpga_program.repository_relative", side_effect=traced), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            result = run_program()
        return order, result

    def test_sof_record_paths_are_derived_before_quartus_pgm_runs(self):
        relative = Path(os.path.relpath(self.sof, Path.cwd()))
        order, result = self.ordered_calls(lambda: program(ROOT, self.folder, relative, quartus_bin="tools"))
        self.assertEqual(order[-2:], ["jtagconfig", "quartus_pgm"], order)
        self.assertNotIn("relative", order[order.index("jtagconfig"):], "no path arithmetic after JTAG")
        self.assertEqual(result["sof"], self.sof.resolve().relative_to(ROOT.resolve()).as_posix())
        self.assertEqual(result["device_state"], "changed")

    def test_pof_record_paths_are_derived_before_quartus_pgm_runs(self):
        attempt = FlashProgramTests.write_attempt(self, self.folder)
        relative = Path(os.path.relpath(attempt, Path.cwd()))
        order, result = self.ordered_calls(lambda: program_flash(ROOT, self.folder, relative, quartus_bin="tools"))
        self.assertEqual(order[-2:], ["jtagconfig", "quartus_pgm"], order)
        self.assertNotIn("relative", order[order.index("jtagconfig"):], "no path arithmetic after JTAG")
        self.assertEqual(result["pof"], attempt.resolve().relative_to(ROOT.resolve()).as_posix())
        self.assertEqual(result["attempt_result"], (self.folder / "result.json").resolve().relative_to(ROOT.resolve()).as_posix())
        self.assertEqual(result["device_state"], "changed")

    def test_post_program_host_failure_records_that_the_device_changed_without_replay(self):
        def fake(root, folder, sof, *, quartus_bin, cable, timeout, progress=None, **options):
            (folder / "chain.log").write_text(VALID_CHAIN)
            (folder / "program.log").write_text(SUCCESS)
            raise ValueError(r"'workdir\builds\x\output\design.sof' is not in the subpath of "
                             r"'\\wsl.localhost\Ubuntu\home\abendavid\github\nand2mario'")

        with patch("n2m.cli.program_fpga", side_effect=fake) as called, \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["fpga", "program", "--sof", str(self.sof), "--quartus-bin", "tools",
                         "--tag", "program-post-failure"], self.folder)
        self.assertEqual(code, 1)
        self.assertEqual(called.call_count, 1, "a failed record never replays the programmer")
        report = json.loads((self.folder / "workdir/builds/program-post-failure/manifest.json").read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["device_state"], "changed")
        self.assertTrue(any(name.endswith("/program.log") for name in report["artifacts"]))
        text = output.getvalue()
        self.assertIn("Result: FAIL", text)
        self.assertIn("Device state: changed; no automatic replay", text)

    def test_programmer_failure_records_an_unconfirmed_device_and_runs_once(self):
        # The CLI treats its root argument as the repository; list the image relative to it.
        (self.folder / "result.json").write_text(json.dumps(
            {"status": "PASS", "target": "v05-board",
             "artifacts": {"output/design.sof": file_hash(self.sof)}}))
        calls = []

        def run(argv, cwd, log, timeout=60):
            calls.append(argv[0])
            (Path(cwd) / log).write_text(VALID_CHAIN if "jtagconfig" in argv[0] else FAILED)
            return VALID_CHAIN if "jtagconfig" in argv[0] else FAILED

        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run), \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["fpga", "program", "--sof", str(self.sof), "--quartus-bin", "tools",
                         "--tag", "program-pgm-failure"], self.folder)
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["jtagconfig", "quartus_pgm"])
        report = json.loads((self.folder / "workdir/builds/program-pgm-failure/manifest.json").read_text())
        self.assertEqual(report["device_state"], "unconfirmed")
        self.assertIn("did not report a successful configuration", report["error"])
        self.assertIn("Device state: unconfirmed; no automatic replay", output.getvalue())

    def test_pass_records_carry_no_failure_device_line(self):
        def fake(root, folder, sof, *, quartus_bin, cable, timeout, progress=None, **options):
            (folder / "program.log").write_text(SUCCESS)
            return {"cable": "1", "devices": ["10M50DA(.|ES)/10M50DC"], "sof": "workdir/x/design.sof",
                    "device_state": "changed", "scope": "double"}

        with patch("n2m.cli.program_fpga", side_effect=fake), \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["fpga", "program", "--sof", str(self.sof), "--quartus-bin", "tools",
                         "--tag", "program-pass-state"], self.folder)
        self.assertEqual(code, 0)
        report = json.loads((self.folder / "workdir/builds/program-pass-state/manifest.json").read_text())
        self.assertEqual(report["device_state"], "changed")
        self.assertNotIn("Device state:", output.getvalue())


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
        stage_registry(self.folder)
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
        self.assertEqual(result["device_state"], "unchanged")
        self.assertNotIn("isp_seconds", result)
        self.assertNotIn("program_log", result, "a dry run retains no programmer log")
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

        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=run):
            result = program_flash(ROOT, self.folder, self.pof, quartus_bin="tools")
        self.assertEqual([call[0][0] for call in calls], ["jtagconfig", "quartus_pgm"])
        self.assertEqual(calls[1][0], ["quartus_pgm", "-c", "1", "-m", "jtag", "-o", f"pvb;{self.pof.resolve()}"])
        self.assertEqual(calls[1][1:], ("program.log", 600))
        self.assertEqual(result["cable"], "1")
        self.assertEqual(result["devices"], ["10M50DA(.|ES)/10M50DC"])
        self.assertEqual(result["chain"]["index"], "1")
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

        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=ambiguous):
            with self.assertRaises(RuntimeError):
                program_flash(ROOT, self.folder, self.pof, quartus_bin="tools")
        self.assertEqual(len(calls), 1, "quartus_pgm must not run after a failed identity check")

        def failed(argv, cwd, log, timeout=60):
            return VALID_CHAIN if "jtagconfig" in argv[0] else "Info: Quartus Prime Programmer failed. 1 error\n"

        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
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
        def fake(root, folder, pof, *, quartus_bin, cable, timeout, dry_run, progress=None, **options):
            (folder / "program.log").write_text(SUCCESS)
            return {"cable": "1", "devices": ["10M50DA(.|ES)/10M50DC"], "pof": str(pof),
                    "backend": "quartus", "pof_sha256": "ab" * 32, "isp_seconds": 123.456, "operation": "pvb",
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
        self.assertIn("JTAG: backend quartus; cable 1; device 10M50DA", text)
        self.assertIn("Flash programmed, verified and blank-checked in 123.456 s; .pof sha256 " + "ab" * 32, text)
        self.assertIn("Next: Power-cycle the DE10-Lite.", text)
        self.assertNotIn("gb_launcher", text)


class DeviceIdentityTests(unittest.TestCase):
    """One matching rule for every supported board, against what each tool actually prints."""

    # Ordering code, the `jtagconfig` chain name and the `openFPGALoader --list-fpga`
    # model for the same IDCODE. Taken from the tools, not from a datasheet.
    BOARDS = (("10M50DAF484C7G", "10M50DA(.|ES)/10M50DC", "10M50D"),
              ("5CSEBA6U23I7", "5CSEBA6(.|ES)/5CSEMA6", "5CSE*A6/5CSX*6"),
              ("EP4CE115F29C7", "EP4CE115", "EP3C120/EP4CE115/10CL120"))

    def test_each_board_device_matches_its_own_chain_names_only(self):
        for device, jtagconfig_name, openfpgaloader_model in self.BOARDS:
            with self.subTest(device=device):
                self.assertTrue(fpga_jtag.device_matches(device, jtagconfig_name))
                self.assertTrue(fpga_jtag.device_matches(device, openfpgaloader_model))
            for other, other_jtagconfig, other_model in self.BOARDS:
                if other == device:
                    continue
                with self.subTest(device=device, against=other):
                    self.assertFalse(fpga_jtag.device_matches(device, other_jtagconfig))
                    self.assertFalse(fpga_jtag.device_matches(device, other_model))

    def test_every_registered_board_is_covered_by_this_case_list(self):
        """A board added to the registry without a case here fails this test, not a board session."""
        registered = set(fpga_jtag.registered_boards(ROOT))
        covered = {device for device, _, _ in self.BOARDS}
        self.assertTrue(registered <= covered, f"registered but unchecked: {sorted(registered - covered)}")

    def test_a_garbled_or_neighbouring_device_never_matches(self):
        # The wedged probe's reading, a neighbouring density, and a truncated name.
        for reported in ("LFE5UM5G-25", "10M40DA", "10M50S", "5CSE*A4", "EP4CE11", "10M5", "", "0x0"):
            with self.subTest(reported=reported):
                self.assertFalse(fpga_jtag.device_matches("10M50DAF484C7G", reported))
        with self.assertRaises(ValueError):
            fpga_jtag.device_matches(None, "10M50DA")

    def test_detect_output_keeps_unknown_positions_in_place(self):
        chains = fpga_jtag.parse_detect(NANO_DETECT, "usb-blasterII")
        self.assertEqual(len(chains), 1)
        self.assertEqual([d["idcode"] for d in chains[0]["devices"]], ["4BA00477", "02D020DD"])
        self.assertEqual(chains[0]["devices"][1]["name"], "5CSE*A6/5CSX*6")
        # A position openFPGALoader knows nothing about still occupies its index.
        unknown = fpga_jtag.parse_detect("index 0:\nindex 1:\n\tidcode 0x2d020dd\n\tmodel  5CSE*A6\n",
                                        "usb-blasterII")
        self.assertEqual(len(unknown[0]["devices"]), 2)
        self.assertEqual(unknown[0]["devices"][0], {"idcode": "", "name": ""})

    def test_an_unreadable_jtagconfig_chain_is_parsed_and_holds_no_device(self):
        chains = fpga_jtag.parse_jtagconfig(UNREADABLE_CHAIN)
        self.assertEqual([chain["devices"] for chain in chains], [[], []])
        # Both are programming cables of supported boards; neither read a chain.
        self.assertEqual([chain["probe"] for chain in chains], [True, True])
        self.assertEqual([chain["name"] for chain in chains][0][:6], "DE-SoC")


class ProgrammerBackendTests(FpgaProgramTests):
    """The backend is chosen by what each available tool reads, and every refusal survives it."""

    def nano_attempt(self):
        """A DE10-Nano attempt: the same record rules, a Cyclone V target."""
        attempt = self.folder / "nano"
        attempt.mkdir()
        sof = attempt / "output/design.sof"
        sof.parent.mkdir()
        sof.write_text("not a real bitstream\n")
        (attempt / "result.json").write_text(json.dumps(
            {"status": "PASS", "target": "nano-smoke", "device": "5CSEBA6U23I7",
             "artifacts": {sof.resolve().relative_to(ROOT.resolve()).as_posix(): file_hash(sof)}}))
        return sof

    def responder(self, calls, *, jtagconfig=UNREADABLE_CHAIN, detect=NANO_DETECT,
                  cable="usb-blasterII", convert=CONVERTED, load=LOADED):
        """A fake programmer: each tool answers with the output a board would produce.

        Only `cable` has a board on it, as on a host with one attached probe, so
        an enumeration with no cable named still has exactly one answer to find.
        """
        def run(argv, cwd, log, timeout=60):
            calls.append(argv)
            name = Path(argv[0]).name
            if name == "jtagconfig":
                output = jtagconfig
            elif name == "quartus_pgm":
                output = SUCCESS
            elif name == "quartus_cpf":
                Path(argv[-1]).write_bytes(b"raw volatile image\n")
                output = convert
            elif "--detect" in argv:
                output = detect if argv[argv.index("-c") + 1] == cable else ABSENT_CABLE
            else:
                output = load
            (Path(cwd) / log).write_text(output)
            return output
        return run

    def test_openfpgaloader_configures_a_cyclone_v_from_the_checked_sof(self):
        sof = self.nano_attempt()
        calls = []
        with fake_programmers(openfpgaloader=True), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=self.responder(calls)):
            result = program(ROOT, self.folder, sof, quartus_bin="tools", probe_firmware="blaster_6810.hex")
        names = [Path(call[0]).name for call in calls]
        self.assertEqual(names, ["jtagconfig", "openFPGALoader", "openFPGALoader",
                                 "quartus_cpf", "openFPGALoader"],
                         "the unreadable Quartus chain falls through, both cables are read, "
                         "then the image is converted and loaded")
        self.assertNotIn("--detect", calls[-1], "the last command is the load, not an enumeration")
        self.assertEqual(result["backend"], "openfpgaloader")
        self.assertEqual((result["board"], result["expected_device"], result["family"]),
                         ("DE10-Nano", "5CSEBA6U23I7", "Cyclone V"))
        self.assertEqual(result["cable"], "usb-blasterII")
        self.assertEqual(result["chain_position"], 1, "the FPGA sits behind the ARM debug access port")
        rbf = self.folder / "design.rbf"
        self.assertEqual(result["command"],
                         ["openFPGALoader", "-c", "usb-blasterII", "--probe-firmware", "blaster_6810.hex",
                          "--index-chain", "1", "--file-type", "rbf", "--write-sram",
                          "--bitstream", str(rbf.resolve())])
        self.assertEqual(result["volatile_image_sha256"], file_hash(rbf))
        self.assertEqual(result["device_state"], "changed")
        self.assertIn("CONF_DONE", result["scope"])
        self.assertIn("5CSE*A6/5CSX*6", (self.folder / "chain.log").read_text(),
                      "chain.log is the enumeration the programmer acted on")
        self.assertTrue((self.folder / "chain-quartus.log").is_file(),
                        "the rejected Quartus attempt keeps its own log")

    def test_quartus_is_used_whenever_its_own_chain_reads(self):
        calls = []
        with fake_programmers(openfpgaloader=True), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=self.responder(calls, jtagconfig=VALID_CHAIN)):
            result = program(ROOT, self.folder, self.sof, quartus_bin="tools")
        self.assertEqual([Path(call[0]).name for call in calls], ["jtagconfig", "quartus_pgm"])
        self.assertEqual(result["backend"], "quartus")
        self.assertEqual(result["command"], ["quartus_pgm", "-c", "1", "-m", "jtag",
                                             "-o", f"p;{self.sof.resolve()}"])
        self.assertNotIn("volatile_image", result, "no conversion on the Quartus path")

    def test_a_successful_exit_on_a_garbled_chain_refuses_before_any_write(self):
        """The wedged FX2 probe measured on the host: exit 0, thirty-two Lattice parts."""
        sof = self.nano_attempt()
        calls = []
        with fake_programmers(openfpgaloader=True), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=self.responder(calls, detect=WEDGED_DETECT)):
            with self.assertRaises(RuntimeError) as caught:
                program(ROOT, self.folder, sof, quartus_bin="tools")
        self.assertIn("5CSEBA6U23I7", str(caught.exception))
        names = [Path(call[0]).name for call in calls]
        self.assertNotIn("quartus_cpf", names, "nothing is converted after a failed identity check")
        self.assertTrue(all("--detect" in call for call in calls if Path(call[0]).name == "openFPGALoader"),
                        "every openFPGALoader command was an enumeration")
        self.assertEqual(device_state_after(self.folder), "unchanged")

    def test_a_de10_lite_image_cannot_reach_a_cyclone_v_or_the_reverse(self):
        calls = []
        with fake_programmers(openfpgaloader=True), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=self.responder(calls)):
            with self.assertRaises(RuntimeError) as caught:
                program(ROOT, self.folder, self.sof, quartus_bin="tools")
        self.assertIn("10M50DAF484C7G (DE10-Lite)", str(caught.exception))
        self.assertEqual(device_state_after(self.folder), "unchanged")

        nano = self.nano_attempt()
        calls = []
        with fake_programmers(), patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=self.responder(calls, jtagconfig=VALID_CHAIN)):
            with self.assertRaises(RuntimeError) as caught:
                program(ROOT, self.folder, nano, quartus_bin="tools")
        self.assertIn("5CSEBA6U23I7 (DE10-Nano)", str(caught.exception))
        self.assertEqual([Path(call[0]).name for call in calls], ["jtagconfig"])

    def test_openfpgaloader_refuses_a_max_10_because_its_only_path_writes_flash(self):
        lite_detect = ("index 0:\n\tidcode 0x31050dd\n\tmanufacturer altera\n\tfamily MAX 10\n"
                       "\tmodel  10M50D\n\tirlength 10\n")
        calls = []
        with fake_programmers(quartus=False, openfpgaloader=True), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute",
                      side_effect=self.responder(calls, detect=lite_detect, cable="usb-blaster")):
            with self.assertRaises(RuntimeError) as caught:
                program(ROOT, self.folder, self.sof, quartus_bin="tools")
        self.assertIn("no volatile configuration for the MAX 10", str(caught.exception))
        self.assertIn("quartus_pgm", str(caught.exception))
        self.assertTrue(all("--detect" in call for call in calls),
                        "the identity matched, and still nothing was converted or written")
        self.assertEqual(device_state_after(self.folder), "unchanged")

    def test_no_programmer_at_all_names_the_tools_not_the_operating_system(self):
        with fake_programmers(quartus=False), patch("n2m.fpga_program.execute") as run:
            with self.assertRaises(RuntimeError) as caught:
                program(ROOT, self.folder, self.sof, quartus_bin="tools")
            run.assert_not_called()
        message = str(caught.exception)
        self.assertIn("jtagconfig", message)
        self.assertIn("openFPGALoader", message)
        for absent in ("Windows", "PowerShell", "Linux", "operating system"):
            self.assertNotIn(absent, message)

    def test_an_explicit_openfpgaloader_cable_selects_that_backend_alone(self):
        sof = self.nano_attempt()
        calls = []
        with fake_programmers(openfpgaloader=True), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=self.responder(calls)):
            result = program(ROOT, self.folder, sof, quartus_bin="tools", cable="usb-blasterII")
        self.assertEqual([Path(call[0]).name for call in calls],
                         ["openFPGALoader", "quartus_cpf", "openFPGALoader"],
                         "a named openFPGALoader cable never enumerates through Quartus")
        self.assertEqual(result["cable"], "usb-blasterII")

    def test_a_record_without_a_registered_target_has_no_expected_device(self):
        listed = json.loads((self.folder / "result.json").read_text())
        for edit, fragment in (({"target": None}, "names no FPGA target"),
                               ({"target": "not-a-target"}, "unregistered FPGA target"),
                               ({"device": "5CSEBA6U23I7"}, "is not the DE10-Lite device")):
            with self.subTest(edit=edit):
                (self.folder / "result.json").write_text(json.dumps({**listed, **edit}))
                with fake_programmers(), patch("n2m.fpga_program.execute") as run:
                    with self.assertRaises(ValueError) as caught:
                        program(ROOT, self.folder, self.sof, quartus_bin="tools")
                    run.assert_not_called()
                self.assertIn(fragment, str(caught.exception))
                self.assertIn(fragment, (self.folder / "failure.log").read_text())

    def test_the_record_refusals_still_fire_on_the_openfpgaloader_backend(self):
        sof = self.nano_attempt()
        record = json.loads((sof.parent.parent / "result.json").read_text())
        for edit, fragment in (({"build_id_override": True}, "comparison-only"),
                               ({"artifacts": {}}, "not the artifact")):
            with self.subTest(edit=edit):
                (sof.parent.parent / "result.json").write_text(json.dumps({**record, **edit}))
                with fake_programmers(quartus=False, openfpgaloader=True), \
                        patch("n2m.fpga_program.execute") as run:
                    with self.assertRaises(ValueError) as caught:
                        program(ROOT, self.folder, sof, quartus_bin="tools")
                    run.assert_not_called()
                self.assertIn(fragment, str(caught.exception))

    def test_a_failed_conversion_refuses_before_the_load(self):
        sof = self.nano_attempt()
        calls = []
        with fake_programmers(openfpgaloader=True), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute",
                      side_effect=self.responder(calls, convert="Error: no license\n")):
            with self.assertRaises(RuntimeError) as caught:
                program(ROOT, self.folder, sof, quartus_bin="tools")
        self.assertIn("raw volatile image", str(caught.exception))
        self.assertEqual([Path(call[0]).name for call in calls][-1], "quartus_cpf")
        self.assertTrue(all("--detect" in call for call in calls if Path(call[0]).name == "openFPGALoader"))
        self.assertEqual(device_state_after(self.folder), "unchanged")

    def test_an_openfpgaloader_load_without_done_is_unconfirmed(self):
        sof = self.nano_attempt()
        calls = []
        with fake_programmers(openfpgaloader=True), \
                patch("n2m.fpga_program.executable", side_effect=lambda d, n: n), \
                patch("n2m.fpga_program.execute", side_effect=self.responder(calls, load=LOAD_FAILED)):
            with self.assertRaises(RuntimeError) as caught:
                program(ROOT, self.folder, sof, quartus_bin="tools")
        self.assertIn("did not report a successful configuration", str(caught.exception))
        self.assertEqual(device_state_after(self.folder), "unconfirmed")

    def test_device_state_reads_either_backend_success_signature(self):
        log = self.folder / "program.log"
        self.assertEqual(device_state_after(self.folder), "unchanged")
        for text, state in ((LOAD_FAILED, "unconfirmed"), (LOADED, "changed"),
                            (FAILED, "unconfirmed"), (SUCCESS, "changed")):
            with self.subTest(state=state):
                log.write_text(text)
                self.assertEqual(device_state_after(self.folder), state)


if __name__ == "__main__":
    unittest.main()
