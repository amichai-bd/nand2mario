"""Readiness failures and safety boundaries; doubles are not board evidence."""
import json
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.doctor import doctor, execute, parse_jtag, questa, quartus, select_uart, uart, warning
from n2m.fpga import ALLOCATOR_NOTICE
from n2m.cli import main, parser

ROOT = Path(__file__).resolve().parents[3]


class DoctorTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/doctor-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="tools with spaces ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_questa_elaboration_runtime_and_signature_failure(self):
        for output, code in (("elaboration failed", 1), ("runtime failed", 1), ("", 0),
                             ("PASS builder-smoke seed=1 checks=22", 1),
                             ("** Error: mismatch\nPASS builder-smoke seed=1 checks=22", 0),
                             ("Errors: 1, Warnings: 0\nPASS builder-smoke seed=1 checks=22", 0),
                             ("Warning: unsafe\nPASS builder-smoke seed=1 checks=22", 0)):
            calls = []
            def run(argv, **kwargs):
                calls.append(argv)
                is_sim = "-c" in argv
                return SimpleNamespace(returncode=code if is_sim else 0,
                                       stdout=output if is_sim else ("Questa 2025.2" if "-version" in argv else "Errors: 0, Warnings: 0"))
            with patch("n2m.doctor.executable", side_effect=lambda d, n: str(self.folder / n)), \
                    patch("n2m.doctor.subprocess.run", side_effect=run):
                with self.assertRaises(RuntimeError):
                    questa(ROOT, self.folder, str(self.folder))
            self.assertEqual(len(calls), 4)
            self.assertEqual(calls[2][-1], str(ROOT / "src/dv/builder/builder_smoke.sv"))
            self.assertTrue((self.folder / "sim.log").exists())

    def test_questa_checked_smoke_uses_macro_handlers(self):
        def run(argv, **kwargs):
            output = "Questa 2025.2" if "-version" in argv else "Errors: 0, Warnings: 0"
            if "-c" in argv:
                self.assertEqual(argv[-2:], ["-do", "do run.do"])
                self.assertEqual(argv[argv.index("-onfinish") + 1], "stop")
                macro = (kwargs["cwd"] / "run.do").read_text()
                self.assertEqual(macro.splitlines(), [
                    "onbreak {if {[lindex [runStatus -full] 2] eq {$finish}} "
                    "{quit -code 0} else {quit -code 1}}",
                    "onerror {quit -code 1}", "run -all", "quit -code 1"])
                output = "PASS builder-smoke seed=1 checks=22"
            return SimpleNamespace(returncode=0, stdout=output)
        with patch("n2m.doctor.executable", side_effect=lambda d, n: str(self.folder / n)), \
                patch("n2m.doctor.subprocess.run", side_effect=run):
            result = questa(ROOT, self.folder, str(self.folder))
        self.assertIn("runtime checkout succeeded", result["license"])

    def test_missing_tool_timeout_and_partial_logs(self):
        for error in (FileNotFoundError("absent"), subprocess.TimeoutExpired("vsim", 60, output=b"partial runtime")):
            with patch("n2m.doctor.subprocess.run", side_effect=error):
                with self.assertRaises(RuntimeError):
                    execute(["path with spaces/vsim"], self.folder, "failed.log")
            self.assertTrue((self.folder / "failed.log").read_text())
        self.assertIn("partial runtime", (self.folder / "failed.log").read_text())

    def test_jtag_identity_stays_with_cable_and_ambiguity(self):
        valid = "1) USB-Blaster [USB-0]\n  031050DD 10M50DA(.|ES)/10M50DC\n"
        self.assertEqual(parse_jtag(valid)["selected"]["index"], "1")
        for invalid in ("1) USB-Blaster\n  00000000 UNKNOWN\n2) Other\n  031050DD 10M50DA\n",
                        valid + valid.replace("1)", "2)"), "No hardware", valid.replace("10M50DA", "10M40DA")):
            with self.assertRaises(RuntimeError):
                parse_jtag(invalid)
        self.assertEqual(parse_jtag(valid + valid.replace("1)", "2)"), "2")["selected"]["index"], "2")

    def test_uart_selection_is_read_only_and_exact(self):
        ports = [{"DeviceID": "COM5", "Name": "USB Serial Port (COM5)",
                  "PNPDeviceID": "FTDIBUS\\VID_0403+PID_6001+SYNTHETIC_A\\0000",
                  "Status": "OK", "ConfigManagerErrorCode": 0}]
        args = SimpleNamespace(uart_port=None, uart_vid=None, uart_pid=None, uart_identity=None)
        self.assertEqual(select_uart(ports, args)["status"], "WARNING")
        args.uart_identity = ports[0]["PNPDeviceID"]
        self.assertEqual(select_uart(ports, args)["selected"], ports[0])
        args.uart_port = "COM6"
        with self.assertRaises(RuntimeError):
            select_uart(ports, args)
        args.uart_port = "COM5"
        with patch("n2m.doctor.os.name", "nt"), patch("n2m.doctor.execute", return_value=json.dumps(ports)) as run:
            self.assertEqual(uart(self.folder, args)["selected"], ports[0])
        argv = run.call_args.args[0]
        self.assertIn("Get-CimInstance Win32_PnPEntity", argv[-1])
        self.assertNotIn("Win32_SerialPort", argv[-1])
        self.assertNotIn("SerialPort]", argv[-1])
        self.assertNotIn("Open", argv[-1])

    def test_pnp_serial_inventory_filters_and_health(self):
        serial = {"Name": "USB Serial Port (COM8)",
                  "PNPDeviceID": "FTDIBUS\\VID_0403+PID_6001+EXAMPLE_B\\0000",
                  "Status": "OK", "ConfigManagerErrorCode": 0}
        args = parser().parse_args(["doctor", "--uart-port", "COM8", "--uart-vid", "0403",
                                   "--uart-pid", "6001", "--uart-identity", serial["PNPDeviceID"]])
        inventory = [serial, *[{**serial, "Name": name} for name in
                              ("Printer Port (LPT1)", "USB Serial Port COM8", "USB (COM0)",
                               "USB (COM8) extra", "USB (COM8x)", None)]]
        def probe(devices):
            # Only PnP is queried; absence from Win32_SerialPort has no effect.
            def query(argv, *unused):
                return json.dumps(devices) if "Win32_PnPEntity" in argv[-1] else "[]"
            with patch("n2m.doctor.os.name", "nt"), patch("n2m.doctor.execute", side_effect=query):
                return uart(self.folder, args)
        self.assertEqual(len(probe(inventory)["ports"]), 1)
        for fields in ({"Status": "Error"}, {"ConfigManagerErrorCode": 22},
                       {"Status": None}, {"ConfigManagerErrorCode": None}):
            with self.assertRaisesRegex(RuntimeError, "healthy"):
                probe([{**serial, **fields}])
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            probe([serial, serial])
        args.uart_identity = "wrong identity"
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            probe([serial])

    def test_zero_warning_summary_only(self):
        self.assertFalse(warning("Errors: 0, Warnings: 0"))
        self.assertTrue(warning("Warnings: 1"))
        self.assertTrue(warning("# ** Warning: diagnostic"))

    def test_status_priority_exit_and_latest_pointer(self):
        for status, code in (("PASS", 0), ("WARNING", 2), ("FAIL", 1)):
            with patch("n2m.cli.doctor", return_value={"status": status}), \
                    patch("n2m.cli.git_state", return_value={}), contextlib.redirect_stdout(io.StringIO()):
                latest = self.folder / "workdir/latest.txt"
                latest.parent.mkdir(exist_ok=True)
                latest.write_text("previous\n")
                self.assertEqual(main(["doctor", "--tag", "status", "--json"], self.folder), code)
                self.assertEqual(latest.read_text(), "status\n" if status == "PASS" else "previous\n")

    def test_profile_failure_priority_and_fresh_attempts(self):
        args = parser().parse_args(["doctor", "--profile", "environment"])
        with patch("n2m.doctor.quartus", return_value={}), patch("n2m.doctor.executable", return_value="jtagconfig"), \
                patch("n2m.doctor.execute", return_value="1) USB-Blaster\n  031050DD 10M50DA\n"), \
                patch("n2m.doctor.uart", return_value={"status": "WARNING"}), \
                patch("n2m.doctor.questa", return_value={}):
            self.assertEqual(doctor(ROOT, self.folder, args, {})["status"], "WARNING")
            with patch("n2m.doctor.questa", side_effect=RuntimeError("bad elaboration")):
                self.assertEqual(doctor(ROOT, self.folder, args, {})["status"], "FAIL")
            self.assertEqual(len(list((self.folder / "doctor").iterdir())), 2)

    def test_default_profile_runs_only_questa_and_missing_license_fails(self):
        args = parser().parse_args(["doctor"])
        self.assertEqual((args.profile, args.sim), ("simulation", "questa"))
        with patch("n2m.doctor.questa", return_value={"tools": {"vsim": "fixture"}}) as run, \
             patch("n2m.doctor.quartus") as quartus_probe, patch("n2m.doctor.uart") as uart_probe:
            report = doctor(ROOT, self.folder, args, {})
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(set(report["checks"]), {"questa"})
            self.assertEqual(report["untested"], ["Quartus", "JTAG", "UART"])
            run.assert_called_once()
            quartus_probe.assert_not_called()
            uart_probe.assert_not_called()
        with patch("n2m.doctor.questa", side_effect=RuntimeError("runtime license unavailable")):
            report = doctor(ROOT, self.folder, args, {})
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("license", report["checks"]["questa"]["error"])

    def test_quartus_license_scope_and_diagnostics(self):
        for edition, status in (("Lite Edition", "PASS"), ("Standard Edition", "WARNING")):
            with patch("n2m.doctor.executable", return_value="quartus_sh"), \
                    patch("n2m.doctor.execute", return_value=f"Quartus Prime Shell\nVersion 25.1 {edition}\n"):
                self.assertEqual(quartus(self.folder, None)["status"], status)
        with patch("n2m.doctor.executable", return_value="quartus_sh"), \
                patch("n2m.doctor.execute", return_value="TBBmalloc: unknown prologue\nQuartus Prime Shell\nVersion 25.1 Lite Edition"):
            with self.assertRaisesRegex(RuntimeError, "diagnostic"):
                quartus(self.folder, None)

    def test_quartus_explains_only_the_pinned_allocator_notice(self):
        banner = "Quartus Prime Shell\nVersion 25.1 Lite Edition"
        with patch("n2m.doctor.executable", return_value="quartus_sh"), \
                patch("n2m.doctor.execute", return_value=f"{ALLOCATOR_NOTICE}\n{banner}"):
            report = quartus(self.folder, None)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["explained_diagnostics"],
                         [{"code": "TBBmalloc", "text": ALLOCATOR_NOTICE}])
        self.assertIn(ALLOCATOR_NOTICE, report["version"])
        with patch("n2m.doctor.executable", return_value="quartus_sh"), \
                patch("n2m.doctor.execute", return_value=banner):
            self.assertEqual(quartus(self.folder, None)["explained_diagnostics"], [])
        for unexpected in (f"{ALLOCATOR_NOTICE} extra", ALLOCATOR_NOTICE.replace("_msize", "_expand"),
                           "Error (1): unrelated"):
            with patch("n2m.doctor.executable", return_value="quartus_sh"), \
                    patch("n2m.doctor.execute", return_value=f"{unexpected}\n{banner}"):
                with self.assertRaisesRegex(RuntimeError, "diagnostic"):
                    quartus(self.folder, None)


if __name__ == "__main__":
    unittest.main()
