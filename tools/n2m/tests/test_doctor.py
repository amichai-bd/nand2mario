"""Readiness failures and safety boundaries; doubles are not board evidence."""
import json
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.doctor import (LICENSE_VARIABLES, SMOKE, SMOKE_FAULT, SMOKE_SIGNATURE, doctor, execute,
                        parse_jtag, quartus, questa, select_uart, uart, verilator, warning)
from n2m.fpga import ALLOCATOR_NOTICE, ALLOCATOR_OVERRIDE_NOTICE, quartus_environment
from n2m.cli import main, parser

ROOT = Path(__file__).resolve().parents[3]


class DoctorTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/doctor-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="tools with spaces ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    @staticmethod
    def runner(calls, compile_output="", compile_code=0, run_output="", run_code=0,
               fault_output="", fault_code=1):
        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            if "--version" in argv:
                return SimpleNamespace(returncode=0, stdout="Verilator 5.052 2026-09-05 rev v5.052\n")
            if "--binary" in argv:
                return SimpleNamespace(returncode=compile_code, stdout=compile_output)
            if "+inject_failure" in argv:
                return SimpleNamespace(returncode=fault_code, stdout=fault_output)
            return SimpleNamespace(returncode=run_code, stdout=run_output)
        return run

    def test_verilator_elaboration_runtime_and_signature_failure(self):
        good = SMOKE_SIGNATURE + "\n- builder_smoke.sv:37: Verilog $finish\n"
        fault = ("[40000] %Fatal: builder_smoke.sv:31: Assertion failed in builder_smoke: " + SMOKE_FAULT
                 + "\n%Error: builder_smoke.sv:31: Verilog $stop\nAborting...\n")
        cases = (dict(compile_output="%Error: builder_smoke.sv:3: syntax error", compile_code=1),
                 dict(compile_output="%Warning-WIDTHEXPAND: builder_smoke.sv:27: Operator ASSIGN"),
                 dict(run_output="runtime failed", run_code=1),
                 dict(run_output=""),
                 dict(run_output=good, run_code=1),
                 dict(run_output="%Error: builder_smoke.sv:25: mismatch\n" + good),
                 dict(run_output="[40000] %Fatal: builder_smoke.sv:31: watchdog\n" + good),
                 dict(run_output=good, fault_output=fault, fault_code=0),
                 dict(run_output=good, fault_output="Aborting...", fault_code=1),
                 dict(run_output=good, fault_output=good, fault_code=1))
        for case in cases:
            calls = []
            with patch("n2m.doctor.executable", side_effect=lambda d, n: str(self.folder / n)), \
                    patch("n2m.doctor.subprocess.run", side_effect=self.runner(calls, **case)):
                with self.assertRaises(RuntimeError):
                    verilator(ROOT, self.folder, str(self.folder))
            self.assertLessEqual(len(calls), 4)
            self.assertEqual(calls[1][0][-1], str(ROOT / SMOKE))
            self.assertTrue((self.folder / ("compile.log" if len(calls) == 2 else "sim.log")).exists())
            self.assertEqual(len(calls) == 4, "fault_output" in case)

    def test_verilator_checked_smoke_reads_no_license(self):
        calls = []
        good = SMOKE_SIGNATURE + "\n- builder_smoke.sv:37: Verilog $finish\n"
        fault = ("[40000] %Fatal: builder_smoke.sv:31: Assertion failed in builder_smoke: " + SMOKE_FAULT
                 + "\n%Error: builder_smoke.sv:31: Verilog $stop\nAborting...\n")
        licensed = {name: "27000@example" for name in LICENSE_VARIABLES}
        with patch.dict("n2m.doctor.os.environ", {**licensed, "N2M_KEEP": "1"}), \
                patch("n2m.doctor.executable", side_effect=lambda d, n: str(self.folder / n)), \
                patch("n2m.doctor.subprocess.run",
                      side_effect=self.runner(calls, run_output=good, fault_output=fault)):
            result = verilator(ROOT, self.folder, str(self.folder))
        self.assertEqual(result["release"], "5.052")
        self.assertEqual(result["tools"], {"verilator": str(self.folder / "verilator")})
        self.assertTrue(result["fault"]["detected"])
        self.assertIn("none consulted", result["license"])
        self.assertEqual(len(calls), 4)
        for argv, kwargs in calls:
            self.assertEqual(kwargs["cwd"], self.folder)
            for name in LICENSE_VARIABLES:
                self.assertNotIn(name, kwargs["env"])
            self.assertEqual(kwargs["env"]["N2M_KEEP"], "1")
        compile_argv = calls[1][0]
        for flag in ("--binary", "--timing", "--trace-vcd", "--x-initial", "unique", "--Mdir", "obj_dir"):
            self.assertIn(flag, compile_argv)
        self.assertNotIn("-Wno-fatal", compile_argv)
        self.assertEqual(calls[2][0], [str(self.folder / "obj_dir/smoke"), "+seed=1", "+verilator+rand+reset+2"])
        self.assertEqual(calls[3][0][-1], "+inject_failure")
        self.assertTrue((self.folder / "fault.log").exists())

    def test_questa_checked_smoke_proves_positive_and_injected_failure(self):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            if "-version" in argv:
                return SimpleNamespace(returncode=0, stdout="Questa 2025.2\n")
            if argv[0].endswith("vsim") and "+inject_failure" in argv:
                return SimpleNamespace(
                    returncode=1,
                    stdout=f"** Fatal: {SMOKE_FAULT}\nErrors: 1, Warnings: 0\n")
            if argv[0].endswith("vsim"):
                return SimpleNamespace(
                    returncode=0,
                    stdout=f"{SMOKE_SIGNATURE}\nErrors: 0, Warnings: 0\n")
            return SimpleNamespace(returncode=0, stdout="Errors: 0, Warnings: 0\n")

        with patch("n2m.doctor.executable", side_effect=lambda d, n: str(self.folder / n)), \
                patch("n2m.doctor.subprocess.run", side_effect=run):
            result = questa(ROOT, self.folder, str(self.folder))
        self.assertTrue(result["fault"]["detected"])
        self.assertIn("checkout succeeded", result["license"])
        simulations = [argv for argv, _ in calls if argv[0].endswith("vsim")]
        self.assertEqual(len(simulations), 3)  # version, positive, injected fault
        self.assertNotIn("+inject_failure", simulations[1])
        self.assertIn("+inject_failure", simulations[2])
        self.assertTrue((self.folder / "waves/smoke.wlf").parent.is_dir())

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
        args = parser().parse_args(["doctor", "--profile", "environment", "--sim", "verilator"])
        with patch("n2m.doctor.quartus", return_value={}), patch("n2m.doctor.executable", return_value="jtagconfig"), \
                patch("n2m.doctor.execute", return_value="1) USB-Blaster\n  031050DD 10M50DA\n"), \
                patch("n2m.doctor.uart", return_value={"status": "WARNING"}), \
                patch("n2m.doctor.verilator", return_value={}):
            self.assertEqual(doctor(ROOT, self.folder, args, {})["status"], "WARNING")
            with patch("n2m.doctor.verilator", side_effect=RuntimeError("bad elaboration")):
                self.assertEqual(doctor(ROOT, self.folder, args, {})["status"], "FAIL")
            self.assertEqual(len(list((self.folder / "doctor").iterdir())), 2)

    def test_default_profile_runs_only_verilator_and_broken_elaboration_fails(self):
        args = parser().parse_args(["doctor", "--sim", "verilator"])
        self.assertEqual((args.profile, args.sim, args.verilator_bin), ("simulation", "verilator", None))
        with patch("n2m.doctor.verilator", return_value={"tools": {"verilator": "fixture"}}) as run, \
             patch("n2m.doctor.quartus") as quartus_probe, patch("n2m.doctor.uart") as uart_probe:
            report = doctor(ROOT, self.folder, args, {})
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(set(report["checks"]), {"verilator"})
            self.assertEqual(report["simulator"], "verilator")
            self.assertEqual(report["tools"], {"verilator": "fixture"})
            self.assertEqual(report["untested"], ["Quartus", "JTAG", "UART"])
            self.assertIn(SMOKE, report["inputs"])
            run.assert_called_once()
            quartus_probe.assert_not_called()
            uart_probe.assert_not_called()
        with patch("n2m.doctor.verilator", side_effect=RuntimeError("exit 1; see compile.log")):
            report = doctor(ROOT, self.folder, args, {})
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["readiness"], "partial")
            self.assertIn("compile.log", report["checks"]["verilator"]["error"])

    def test_selected_questa_is_checked_and_environment_adds_fpga_probes(self):
        args = parser().parse_args(["doctor", "--sim", "questa"])
        with patch("n2m.doctor.questa", return_value={"tools": {"vsim": "fixture"}}) as smoke, \
                patch("n2m.doctor.questa_lint", return_value={}), \
                patch("n2m.doctor.verilator") as verilator_probe:
            report = doctor(ROOT, self.folder, args, {})
        self.assertEqual((report["status"], report["simulator"], report["readiness"]),
                         ("PASS", "questa", "complete"))
        self.assertEqual(report["tools"], {"vsim": "fixture"})
        smoke.assert_called_once()
        verilator_probe.assert_not_called()

        args = parser().parse_args(["doctor", "--profile", "environment", "--sim", "questa"])
        with patch("n2m.doctor.quartus", return_value={}) as quartus_probe, \
                patch("n2m.doctor.executable", return_value="jtagconfig"), \
                patch("n2m.doctor.execute", return_value="1) USB-Blaster\n  031050DD 10M50DA\n"), \
                patch("n2m.doctor.uart", return_value={"selected": "COM5"}) as uart_probe, \
                patch("n2m.doctor.questa_lint", return_value={}), \
                patch("n2m.doctor.questa", return_value={}):
            report = doctor(ROOT, self.folder, args, {})
        quartus_probe.assert_called_once()
        uart_probe.assert_called_once()
        self.assertEqual({name: c["status"] for name, c in report["checks"].items()},
                         {"questa": "PASS", "questa-lint": "PASS", "quartus": "PASS", "jtag": "PASS", "uart": "PASS"})
        self.assertEqual((report["status"], report["readiness"]), ("PASS", "complete"))
        with patch("n2m.doctor.quartus", return_value={}), \
                patch("n2m.doctor.executable", return_value="jtagconfig"), \
                patch("n2m.doctor.execute", return_value="1) USB-Blaster\n  031050DD 10M50DA\n"), \
                patch("n2m.doctor.uart", return_value={"status": "WARNING"}), \
                patch("n2m.doctor.questa_lint", return_value={}), \
                patch("n2m.doctor.questa", return_value={}):
            self.assertEqual(doctor(ROOT, self.folder, args, {})["status"], "WARNING")
        with patch("n2m.doctor.quartus", side_effect=RuntimeError("missing quartus_sh")), \
                patch("n2m.doctor.executable", return_value="jtagconfig"), \
                patch("n2m.doctor.execute", return_value="1) USB-Blaster\n  031050DD 10M50DA\n"), \
                patch("n2m.doctor.uart", return_value={}), \
                patch("n2m.doctor.questa_lint", return_value={}), \
                patch("n2m.doctor.questa", return_value={}):
            self.assertEqual(doctor(ROOT, self.folder, args, {})["status"], "FAIL")

    def test_quartus_license_scope_and_diagnostics(self):
        for edition, status in (("Lite Edition", "PASS"), ("Standard Edition", "WARNING")):
            with patch("n2m.doctor.executable", return_value="quartus_sh"), \
                    patch("n2m.doctor.execute", return_value=f"Quartus Prime Shell\nVersion 25.1 {edition}\n"):
                self.assertEqual(quartus(self.folder, None)["status"], status)
        with patch("n2m.doctor.executable", return_value="quartus_sh"), \
                patch("n2m.doctor.execute", return_value="TBBmalloc: unknown prologue\nQuartus Prime Shell\nVersion 25.1 Lite Edition"):
            with self.assertRaisesRegex(RuntimeError, "diagnostic"):
                quartus(self.folder, None)

    def test_quartus_check_launches_with_the_build_flow_allocator_override(self):
        banner = "Quartus Prime Shell\nVersion 25.1 Lite Edition"
        with patch("n2m.doctor.executable", return_value="quartus_sh"), \
                patch("n2m.doctor.execute", return_value=banner) as run:
            report = quartus(self.folder, None)
        self.assertEqual(run.call_args.kwargs["env"]["TBB_MALLOC_DISABLE_REPLACEMENT"], "1")
        self.assertEqual(report["environment"], {"TBB_MALLOC_DISABLE_REPLACEMENT": "1"})
        self.assertEqual(report["notice"], ALLOCATOR_OVERRIDE_NOTICE)

    def test_execute_passes_only_an_explicit_environment(self):
        code = "import os; print(os.environ.get('TBB_MALLOC_DISABLE_REPLACEMENT'))"
        plain = execute([sys.executable, "-c", code], self.folder, "plain.log")
        self.assertEqual(plain.strip(), str(os.environ.get("TBB_MALLOC_DISABLE_REPLACEMENT")))
        forced = execute([sys.executable, "-c", code], self.folder, "forced.log", env=quartus_environment())
        self.assertEqual(forced.strip(), "1")

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
