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
from n2m.doctor import (BY_ID_ABSENT, LICENSE_VARIABLES, SMOKE, SMOKE_FAULT, SMOKE_SIGNATURE, doctor,
                        execute, jtag, linux_ports, node_state, quartus, questa, select_uart, uart,
                        unreadable_inputs, verilator, warning)
from n2m import fpga_jtag
from n2m.simulator import QUESTA_LICENSE, QUESTA_LICENSE_PROBE
from n2m.fpga import ALLOCATOR_NOTICE, ALLOCATOR_OVERRIDE_NOTICE, quartus_environment
from n2m.cli import main, parser
import serial_fixture

ROOT = Path(__file__).resolve().parents[3]
# One cable reporting the DE10-Lite's MAX 10, as `jtagconfig` prints it.
LITE_CHAIN = "1) USB-Blaster\n  031050DD 10M50DA\n"


# Measured on this host from `vsim -c -nolog -lic_noqueue -do "quit -f"` with no
# license variable set. The classifier's own cases live in test_questa.py.
UNSET_VSIM = (
    "Unable to find the license file.  It appears that your license file environment "
    "variable (SALT_LICENSE_SERVER) is not set correctly.\n"
    "Unable to checkout a license.  Vsim is closing.\n"
    "** Error: Invalid license environment. Application closing.\n")


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

    def test_operator_tool_off_the_pin_is_noticed_and_the_pinned_tree_refused(self):
        """The doctor says the same thing a simulation says, on the same channel.

        An operator's own tool keeps precedence, so the check still passes with it;
        recording `pin_match` false and printing nothing would be exactly the
        silence the pin exists to prevent. The pinned tree claims to be the pin,
        so a mismatch there fails instead."""
        good = SMOKE_SIGNATURE + "\n- builder_smoke.sv:37: Verilog $finish\n"
        fault = ("[40000] %Fatal: builder_smoke.sv:31: Assertion failed in builder_smoke: " + SMOKE_FAULT
                 + "\n%Error: builder_smoke.sv:31: Verilog $stop\nAborting...\n")

        def stale(argv, **kwargs):
            if "--version" in argv:
                return SimpleNamespace(returncode=0, stdout="Verilator 5.020 2025-01-01 rev v5.020\n")
            return self.runner([], run_output=good, fault_output=fault)(argv, **kwargs)

        for discovery in ("explicit", "path"):
            with self.subTest(discovery=discovery), \
                    patch("n2m.doctor.verilator_executable",
                          side_effect=lambda d, r, s=discovery: (str(self.folder / "verilator"), s)), \
                    patch("n2m.doctor.subprocess.run", side_effect=stale):
                result = verilator(ROOT, self.folder, str(self.folder))
            self.assertEqual((result["pin"], result["pin_match"]), ("5.052", False))
            self.assertIn(f"Verilator 5.020 from {discovery} discovery is not the pinned 5.052",
                          result["notice"])
        with patch("n2m.doctor.verilator_executable",
                   side_effect=lambda d, r: (str(self.folder / "verilator"), "pinned")), \
                patch("n2m.doctor.subprocess.run", side_effect=stale):
            with self.assertRaisesRegex(RuntimeError, "from pinned discovery is not the pinned 5.052"):
                verilator(ROOT, self.folder, str(self.folder))
        # A tool that is the pin carries no notice at all.
        with patch("n2m.doctor.verilator_executable",
                   side_effect=lambda d, r: (str(self.folder / "verilator"), "pinned")), \
                patch("n2m.doctor.subprocess.run",
                      side_effect=self.runner([], run_output=good, fault_output=fault)):
            result = verilator(ROOT, self.folder, str(self.folder))
        self.assertEqual(result["pin_match"], True)
        self.assertNotIn("notice", result)

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
            with patch("n2m.doctor.verilator_executable",
                       side_effect=lambda d, r: (str(self.folder / "verilator"), "explicit")), \
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
                patch("n2m.doctor.verilator_executable",
                      side_effect=lambda d, r: (str(self.folder / "verilator"), "explicit")), \
                patch("n2m.doctor.subprocess.run",
                      side_effect=self.runner(calls, run_output=good, fault_output=fault)):
            result = verilator(ROOT, self.folder, str(self.folder))
        self.assertEqual(result["release"], "5.052")
        self.assertEqual(result["tools"], {"verilator": str(self.folder / "verilator")})
        self.assertEqual(result["discovery"], "explicit")
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
            if argv[0].endswith("vsim") and "-lic_noqueue" in argv:
                return SimpleNamespace(returncode=0, stdout="# quit -f\n")
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
        self.assertEqual(result["license_probe"]["argv"][1:], list(QUESTA_LICENSE_PROBE))
        simulations = [argv for argv, _ in calls if argv[0].endswith("vsim")]
        # version, license probe, positive, injected fault. The probe comes before
        # the smoke, so an absent license is named before a run depends on it.
        self.assertEqual(len(simulations), 4)
        self.assertEqual(simulations[1][1:], list(QUESTA_LICENSE_PROBE))
        self.assertNotIn("+inject_failure", simulations[2])
        self.assertIn("+inject_failure", simulations[3])
        self.assertTrue((self.folder / "waves/smoke.wlf").parent.is_dir())

    def test_an_unlicensed_questa_fails_the_doctor_by_license_not_by_host(self):
        """vsim is the only smoke tool that checks out a license. The doctor says
        so on any host, and the compile-gate tools still report present."""
        def run(argv, **kwargs):
            if "-version" in argv:
                return SimpleNamespace(returncode=0, stdout="Questa 2025.2\n")
            if argv[0].endswith("vsim"):
                return SimpleNamespace(returncode=4, stdout=UNSET_VSIM)
            return SimpleNamespace(returncode=0, stdout="Errors: 0, Warnings: 0\n")

        with patch("n2m.doctor.executable", side_effect=lambda d, n: str(self.folder / n)), \
                patch("n2m.doctor.subprocess.run", side_effect=run):
            with self.assertRaises(Exception) as raised:
                questa(ROOT, self.folder, str(self.folder))
        message = str(raised.exception)
        self.assertIn(QUESTA_LICENSE, message)
        self.assertIn("SALT_LICENSE_SERVER", message)
        for absent in ("Windows", "PowerShell", "Linux"):
            self.assertNotIn(absent, message)
        # The vendor's own words are kept beside the named reason.
        self.assertIn("Unable to find the license file", (self.folder / "license.log").read_text())

    def test_missing_tool_timeout_and_partial_logs(self):
        for error in (FileNotFoundError("absent"), subprocess.TimeoutExpired("vsim", 60, output=b"partial runtime")):
            with patch("n2m.doctor.subprocess.run", side_effect=error):
                with self.assertRaises(RuntimeError):
                    execute(["path with spaces/vsim"], self.folder, "failed.log")
            self.assertTrue((self.folder / "failed.log").read_text())
        self.assertIn("partial runtime", (self.folder / "failed.log").read_text())

    def test_jtag_identity_stays_with_cable_and_ambiguity(self):
        """The read-only check accepts one supported board on one cable and nothing else."""
        valid = "1) USB-Blaster [USB-0]\n  031050DD 10M50DA(.|ES)/10M50DC\n"
        args = SimpleNamespace(quartus_bin=None, jtag_cable=None, programmer="quartus",
                               openfpgaloader_bin=None, probe_firmware=None)

        def read(output, cable=None):
            with patch("n2m.fpga_jtag.locate", side_effect=lambda d, name: name), \
                    patch("n2m.doctor.execute", return_value=output):
                return jtag(ROOT, self.folder, SimpleNamespace(**{**vars(args), "jtag_cable": cable}))

        self.assertEqual(read(valid)["cable"], "1")
        self.assertEqual(read(valid)["board"], "DE10-Lite")
        self.assertEqual(read(valid)["backend"], "quartus")
        for invalid in ("1) USB-Blaster\n  00000000 UNKNOWN\n2) Other\n  031050DD 10M50DA\n",
                        valid + valid.replace("1)", "2)"), "No hardware",
                        valid.replace("10M50DA", "10M40DA")):
            with self.assertRaises(RuntimeError):
                read(invalid)
        self.assertEqual(read(valid + valid.replace("1)", "2)"), "2")["cable"], "2")
        # A second supported board on the same cable is ambiguous, not a preference.
        both = "1) USB-Blaster [USB-0]\n  031050DD 10M50DA(.|ES)/10M50DC\n  02D020DD 5CSEBA6(.|ES)/5CSEMA6\n"
        with self.assertRaises(RuntimeError):
            read(both)
        # Terasic names the SoC boards' built-in USB-Blaster II `DE-SoC`; other hardware is not a cable.
        nano = "1) DE-SoC [1-3.2]\n  4BA00477 SOCVHPS\n  02D020DD 5CSEBA6(.|ES)/5CSEMA6\n"
        self.assertEqual(read(nano)["board"], "DE10-Nano")
        self.assertEqual(read(nano)["chain_position"], 1)
        with self.assertRaises(RuntimeError):
            read(nano.replace("DE-SoC [1-3.2]", "Some Other Programmer"))

    def test_jtag_check_falls_through_to_openfpgaloader_and_names_it(self):
        """With the Quartus daemon unable to read a chain, the check uses openFPGALoader and says so."""
        unreadable = ("1) DE-SoC [1-3.2]\n  Unable to read device chain - Hardware not attached\n"
                      "2) USB-Blaster [1-2]\n  Unable to read device chain - JTAG chain broken\n")
        detect = ("index 0:\n\tidcode   0x4ba00477\n\ttype     Cortex A9\n\tirlength 4\n"
                  "index 1:\n\tidcode 0x2d020dd\n\tmanufacturer altera\n\tfamily cyclone V Soc\n"
                  "\tmodel  5CSE*A6/5CSX*6\n\tirlength 10\n")
        args = SimpleNamespace(quartus_bin=None, jtag_cable=None, programmer="auto",
                              openfpgaloader_bin=None, probe_firmware="firmware.hex")

        absent = "unable to open ftdi device: -3 (device not found)\nempty\n"

        def run(argv, cwd, log, timeout=60, env=None, expect_failure=False):
            if "jtagconfig" in argv[0]:
                output = unreadable
            else:
                # Only the USB-Blaster II has a board on it, as on this host.
                output = detect if argv[argv.index("-c") + 1] == "usb-blasterII" else absent
            (Path(cwd) / log).write_text(output)
            return output

        with patch("n2m.fpga_jtag.locate", side_effect=lambda d, name: name), \
                patch("n2m.doctor.execute", side_effect=run):
            report = jtag(ROOT, self.folder, args)
        self.assertEqual(report["backend"], "openfpgaloader")
        self.assertEqual((report["board"], report["device"]), ("DE10-Nano", "5CSEBA6U23I7"))
        self.assertEqual(report["chain_position"], 1, "the FPGA sits behind the ARM debug access port")
        self.assertEqual(report["command"][:2], ["openFPGALoader", "-c"])
        self.assertIn("--detect", report["command"])
        self.assertTrue(any("quartus" in reason for reason in report["rejected"]),
                        "the rejected Quartus attempt is recorded")
        self.assertIn("no wiring, voltage, or programming proof", report["scope"])

    def test_hardware_inspection_resolves_by_installed_tools_not_by_the_host(self):
        """The environment profile names the tool it lacks, never an operating system.

        `fpga program` decides by discovery, so the read-only inspection that
        must precede it decides the same way: the same absent tools produce the
        same named refusals whichever host runs them.
        """
        args = parser().parse_args(["doctor", "--profile", "environment", "--sim", "verilator"])
        with patch("n2m.fpga_jtag.locate", return_value=None), \
                patch("n2m.doctor.uart", return_value={"status": "WARNING"}), \
                patch("n2m.doctor.verilator", return_value={}):
            report = doctor(ROOT, self.folder, args, {})
        self.assertEqual((report["status"], report["readiness"]), ("FAIL", "partial"))
        gaps = "\n".join(report["unreadable"])
        self.assertIn("quartus: missing quartus_sh", gaps)
        self.assertIn("jtag: no JTAG programmer found: missing jtagconfig (Quartus) "
                      "and openFPGALoader", gaps)
        for absent in ("Windows", "PowerShell", "Linux", "operating system"):
            self.assertNotIn(absent, gaps)

    def test_a_passing_chain_names_the_programmer_and_the_cable_it_did_not_read(self):
        """One programmer and one cable answering is not the host read.

        This is the likely bench configuration: the board on `usb-blaster`, no
        `--quartus-bin`, so `jtagconfig` is not found and the other cable has no
        FX2 image. A PASS that said nothing about either would let the check
        stand for cables that never reported.
        """
        detect = ("index 0:\n\tidcode 0x031050dd\n\tmanufacturer altera\n\tfamily MAX 10\n"
                  "\tmodel  10M50DA\n\tirlength 10\n")
        absent = "JTAG init failed with: FX2: fail to open device\nempty\n"
        args = SimpleNamespace(quartus_bin=None, jtag_cable=None, programmer="auto",
                               openfpgaloader_bin=None, probe_firmware=None)

        def run(argv, cwd, log, timeout=60, env=None, expect_failure=False):
            output = detect if argv[argv.index("-c") + 1] == "usb-blaster" else absent
            (Path(cwd) / log).write_text(output)
            return output

        with patch("n2m.fpga_jtag.locate",
                   side_effect=lambda d, name: name if name == "openFPGALoader" else None), \
                patch("n2m.doctor.execute", side_effect=run):
            report = jtag(ROOT, self.folder, args)
        self.assertEqual((report["backend"], report["board"]), ("openfpgaloader", "DE10-Lite"))
        # `not found on this host` is what `locate` establishes; absence is not.
        self.assertEqual(report["unreadable"],
                         ["jtagconfig (Quartus): not found on this host, so its cables were not read",
                          "openfpgaloader usb-blasterII: JTAG init failed with: FX2: fail to open device"])
        self.assertEqual(unreadable_inputs({"jtag": {"status": "PASS", **report}}),
                         [f"jtag: {item}" for item in report["unreadable"]])

    def test_a_jtagconfig_cable_that_read_no_chain_is_named_without_a_borrowed_line(self):
        """One command covers every cable, so no line there belongs to one cable."""
        chain = ("1) USB-Blaster [1-2]\n  031050DD 10M50DA\n"
                 "2) DE-SoC [1-3.2]\n  Unable to read device chain - Hardware not attached\n")
        args = SimpleNamespace(quartus_bin=None, jtag_cable=None, programmer="quartus",
                               openfpgaloader_bin=None, probe_firmware=None)
        with patch("n2m.fpga_jtag.locate", side_effect=lambda d, name: name), \
                patch("n2m.doctor.execute", return_value=chain):
            report = jtag(ROOT, self.folder, args)
        self.assertEqual((report["backend"], report["cable"]), ("quartus", "1"))
        self.assertEqual(report["unreadable"], ["quartus 2: reported no device"])

    def test_a_failing_serial_check_keeps_the_gap_its_probe_found(self):
        """Naming the expected UART is the only way this check passes, so the
        failing path is exactly where the absent by-id directory must survive."""
        args = parser().parse_args(["doctor", "--profile", "environment", "--sim", "verilator",
                                   "--uart-port", "/dev/ttyUSB0"])
        missing = self.folder / "no-serial-by-id"
        with patch("n2m.doctor.os.name", "posix"), patch("n2m.doctor.sys.platform", "linux"), \
                patch("n2m.doctor.SERIAL_BY_ID", missing), \
                patch("n2m.doctor.quartus", return_value={}), \
                patch("n2m.fpga_jtag.locate", side_effect=lambda d, name: name), \
                patch("n2m.doctor.execute", return_value=LITE_CHAIN), \
                patch("n2m.doctor.verilator", return_value={}):
            report = doctor(ROOT, self.folder, args, {})
        self.assertEqual(report["checks"]["uart"]["status"], "FAIL")
        self.assertEqual(report["checks"]["uart"]["unreadable"], [BY_ID_ABSENT.format(path=missing)])
        gaps = report["unreadable"]
        self.assertIn("uart: UART selection must match exactly one enumerated port", gaps)
        self.assertIn(f"uart: {BY_ID_ABSENT.format(path=missing)}", gaps)
        # The same failure without the gap still reports only its own reason.
        with patch("n2m.doctor.os.name", "posix"), patch("n2m.doctor.sys.platform", "linux"), \
                patch("n2m.doctor.SERIAL_BY_ID", missing):
            with self.assertRaises(RuntimeError) as raised:
                uart(self.folder, args)
        self.assertEqual(raised.exception.unreadable, [BY_ID_ABSENT.format(path=missing)])

    def test_absent_udev_serial_names_are_named_and_not_an_empty_inventory(self):
        """A host udev has never named a serial device on is not a host with none attached."""
        args = parser().parse_args(["doctor", "--profile", "environment"])
        missing = self.folder / "no-serial-by-id"
        with patch("n2m.doctor.os.name", "posix"), patch("n2m.doctor.sys.platform", "linux"), \
                patch("n2m.doctor.SERIAL_BY_ID", missing):
            report = uart(self.folder, args)
        self.assertEqual((report["status"], report["ports"]), ("WARNING", []))
        self.assertEqual(report["unreadable"], [BY_ID_ABSENT.format(path=missing)])
        self.assertIs(json.loads((self.folder / "ports.log").read_text())["by_id_present"], False)
        self.linux_inventory()
        self.assertEqual(uart(self.folder, args)["unreadable"], [],
                         "a readable inventory claims nothing was skipped")

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

    def linux_inventory(self):
        """Point enumeration at the fixture inventory and return its records."""
        by_id, tty_class = serial_fixture.inventory(self.folder / "linux")
        patches = (patch("n2m.doctor.SERIAL_BY_ID", by_id), patch("n2m.doctor.TTY_CLASS", tty_class))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return by_id

    def test_linux_enumeration_uses_udev_names_and_sysfs_identity(self):
        self.linux_inventory()
        ports = linux_ports(self.folder)
        # The platform tty has no USB device behind it, so it carries no identity.
        self.assertEqual([port["PNPDeviceID"] for port in ports],
                         [serial_fixture.HEALTHY_IDENTITY, serial_fixture.UNHEALTHY_IDENTITY,
                          serial_fixture.OTHER_IDENTITY])
        healthy, unhealthy, other = ports
        self.assertEqual((healthy["DeviceID"], healthy["Status"], healthy["ConfigManagerErrorCode"]),
                         ("/dev/null", "OK", 0))
        self.assertEqual((healthy["Serial"], healthy["Manufacturer"], healthy["Product"]),
                         ("ABC123", "Example Systems", "Serial Bridge"))
        self.assertTrue(healthy["ByIdPath"].endswith("Serial_Bridge_ABC123-if00-port0"))
        self.assertEqual((other["DeviceID"], other["ConfigManagerErrorCode"]), ("/dev/zero", 0))
        self.assertEqual((unhealthy["Status"], unhealthy["ConfigManagerErrorCode"]), ("Error", 1))
        self.assertIn("device node unavailable", unhealthy["Detail"])
        retained = json.loads((self.folder / "ports.log").read_text())
        self.assertEqual(retained["ports"], ports)

    def test_linux_selection_matches_one_healthy_port_or_refuses(self):
        self.linux_inventory()
        def select(**selectors):
            return uart(self.folder, SimpleNamespace(**{"uart_port": None, "uart_vid": None,
                                                        "uart_pid": None, "uart_identity": None,
                                                        **selectors}))
        self.assertEqual(select()["status"], "WARNING")
        self.assertEqual(select(uart_vid="1234", uart_pid="5678")["selected"]["DeviceID"], "/dev/zero")
        self.assertEqual(select(uart_port="/dev/null")["selected"]["PNPDeviceID"],
                         serial_fixture.HEALTHY_IDENTITY)
        self.assertEqual(select(uart_identity=serial_fixture.HEALTHY_IDENTITY)["selected"]["DeviceID"],
                         "/dev/null")
        # Both FTDI-style names carry the same vendor and product: ambiguous.
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            select(uart_vid="0403", uart_pid="6001")
        with self.assertRaisesRegex(RuntimeError, "not healthy"):
            select(uart_identity=serial_fixture.UNHEALTHY_IDENTITY)
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            select(uart_port="/dev/ttyUSB404")
        self.assertNotIn("Windows", json.dumps([str(error) for error in self.refusals(select)]))

    def refusals(self, select):
        """Every Linux refusal this selection rule can raise, as raised."""
        errors = []
        for selectors in ({"uart_vid": "0403", "uart_pid": "6001"},
                          {"uart_identity": serial_fixture.UNHEALTHY_IDENTITY},
                          {"uart_port": "/dev/ttyUSB404"}):
            try:
                select(**selectors)
            except RuntimeError as error:
                errors.append(error)
        return errors

    def test_device_node_health_is_classified_without_opening(self):
        regular = self.folder / "not-a-node"
        regular.write_text("", encoding="utf-8")
        self.assertEqual(node_state("/dev/null"), ("OK", 0, ""))
        self.assertEqual(node_state(regular)[:2], ("Error", 2))
        self.assertEqual(node_state(self.folder / "absent")[:2], ("Error", 1))

    def test_unsupported_host_enumeration_names_both_supported_hosts(self):
        with patch("n2m.doctor.os.name", "posix"), patch("n2m.doctor.sys.platform", "darwin"):
            result = uart(self.folder, SimpleNamespace(uart_port=None, uart_vid=None,
                                                       uart_pid=None, uart_identity=None))
        self.assertEqual(result["status"], "WARNING")
        self.assertEqual(result["detail"], "UART enumeration supported on Windows and Linux only")

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
        with patch("n2m.doctor.quartus", return_value={}), patch("n2m.fpga_jtag.locate", side_effect=lambda d, name: name), \
                patch("n2m.doctor.execute", return_value=LITE_CHAIN), \
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
                patch("n2m.fpga_jtag.locate", side_effect=lambda d, name: name), \
                patch("n2m.doctor.execute", return_value=LITE_CHAIN), \
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
                patch("n2m.fpga_jtag.locate", side_effect=lambda d, name: name), \
                patch("n2m.doctor.execute", return_value=LITE_CHAIN), \
                patch("n2m.doctor.uart", return_value={"status": "WARNING"}), \
                patch("n2m.doctor.questa_lint", return_value={}), \
                patch("n2m.doctor.questa", return_value={}):
            self.assertEqual(doctor(ROOT, self.folder, args, {})["status"], "WARNING")
        with patch("n2m.doctor.quartus", side_effect=RuntimeError("missing quartus_sh")), \
                patch("n2m.fpga_jtag.locate", side_effect=lambda d, name: name), \
                patch("n2m.doctor.execute", return_value=LITE_CHAIN), \
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
