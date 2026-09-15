"""Scripted build-menu checks; no simulator, FPGA, UART or GUI is opened."""
import contextlib
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import interface_codec, tui, tui_terminal


ROOT = Path(__file__).resolve().parents[3]


class ScriptedTerminal:
    def __init__(self, keys, interactive=True):
        self.keys = list(keys)
        self.frames = []
        self.is_interactive = interactive

    def interactive(self):
        return self.is_interactive

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def draw(self, lines):
        self.frames.append(list(lines))

    def key(self):
        if not self.keys:
            raise AssertionError("scripted terminal ran out of keys")
        return self.keys.pop(0)


class TuiTests(unittest.TestCase):
    def test_posix_and_windows_arrow_enter_escape_decoding(self):
        rest = iter("[A")
        self.assertEqual(tui.decode_posix("\x1b", lambda: next(rest, "")), "UP")
        self.assertEqual(tui.decode_posix("\x1b", lambda: ""), "ESC")
        self.assertEqual(tui.decode_posix("\n", lambda: ""), "ENTER")
        self.assertEqual(tui.decode_posix("\x7f", lambda: ""), "BACKSPACE")
        self.assertEqual(tui.decode_windows("\xe0", lambda: "P"), "DOWN")
        self.assertEqual(tui.decode_windows("\r", lambda: ""), "ENTER")
        self.assertEqual(tui.decode_windows("\x1b", lambda: ""), "ESC")

    def test_selector_filters_navigates_and_bounds_long_lists(self):
        terminal = ScriptedTerminal(["2", "5", "DOWN", "ENTER"])
        choices = [tui.Choice(number, f"target-{number:02}") for number in range(40)]
        selected = tui.Menu(terminal).choose("Targets", choices)
        self.assertEqual(selected, 25)
        # One selected detail may add a line, but no frame displays more than
        # the fixed viewport's choice labels.
        for frame in terminal.frames:
            self.assertLessEqual(sum(line.lstrip().startswith(("> target-", "target-"))
                                     for line in frame), tui.VIEW_ROWS)

    def test_escape_moves_back_one_decision_and_first_escape_cancels(self):
        terminal = ScriptedTerminal(["ENTER", "ESC", "DOWN", "ENTER", "ENTER"])
        menu = tui.Menu(terminal)
        result = tui._collect(menu, [
            ("first", lambda _: menu.choose("First", [tui.Choice("a", "A"), tui.Choice("b", "B")])),
            ("second", lambda _: menu.choose("Second", [tui.Choice("x", "X")]))])
        self.assertEqual(result, {"first": "b", "second": "x"})
        self.assertIs(tui.select_command(tui.Menu(ScriptedTerminal(["ESC"])), ROOT), tui.CANCEL)

    def test_live_argparse_families_all_have_an_intent(self):
        self.assertEqual(set(tui.top_families()), set(tui.INTENTS))

    def test_backend_target_choices_come_from_the_live_registry(self):
        with tempfile.TemporaryDirectory(prefix="tui registry ") as temporary:
            root = Path(temporary)
            registry = root / "src/dv/builder/targets.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(json.dumps({
                "v-only": {"simulators": ["verilator"]},
                "q-only": {"simulators": ["questa"]},
                "both": {"simulators": ["verilator", "questa"], "testbench": "python"},
                "preload-sv": {"simulators": ["verilator"], "preload": "fixture"},
            }))
            self.assertEqual(tui.simulation_targets(root, "verilator"), ["both", "preload-sv", "v-only"])
            self.assertEqual(tui.simulation_targets(root, "questa"), ["both", "q-only"])
            self.assertEqual(tui.simulation_targets(root, None, preflight=True), ["both"])

    def test_checked_sof_discovery_rejects_uninventoried_and_returns_wire_id(self):
        with tempfile.TemporaryDirectory(prefix="tui path with spaces ") as temporary:
            root = Path(temporary)
            output = root / "workdir/builds/play/fpga/v05-board/attempts/abc/output"
            output.mkdir(parents=True)
            sof = output / "design.sof"
            sof.write_bytes(b"checked")
            relative = sof.relative_to(root).as_posix()
            result = output.parent / "result.json"
            result.write_text(json.dumps({"status": "PASS", "target": "v05-board",
                                          "build_id": "00112233445566778899aabbccddeeff",
                                          "artifacts": {relative: hashlib.sha256(b"checked").hexdigest()}}))
            bad = root / "workdir/builds/bad/fpga/v05-board/attempts/nope/output"
            bad.mkdir(parents=True)
            (bad / "design.sof").write_bytes(b"not listed")
            failed = root / "workdir/builds/failed/fpga/v05-board/attempts/no/output"
            failed.mkdir(parents=True)
            failed_sof = failed / "design.sof"
            failed_sof.write_bytes(b"failed")
            failed_relative = failed_sof.relative_to(root).as_posix()
            (failed.parent / "result.json").write_text(json.dumps({
                "status": "FAIL", "target": "v05-board", "build_id": "11" * 16,
                "artifacts": {failed_relative: hashlib.sha256(b"failed").hexdigest()}}))
            linked = root / "workdir/builds/linked/fpga/v05-board/attempts/no/output"
            linked.mkdir(parents=True)
            (linked / "design.sof").symlink_to(sof)
            self.assertEqual(tui.checked_sofs(root),
                             [(relative, "v05-board", "ffeeddccbbaa99887766554433221100")])

    def test_powershell_review_quotes_paths_with_spaces(self):
        plan = tui.Plan(["fpga", "build", "v05-board", "--quartus-bin",
                         r"C:\Program Files\Intel FPGA\bin64"],
                        ("fpga", "build"), "Windows PowerShell", "build")
        text = tui.command_text(plan, ROOT, "Windows", executable=r"C:\Program Files\Python\python.exe")
        self.assertIn("'C:\\Program Files\\Intel FPGA\\bin64'", text)
        self.assertTrue(text.startswith("& 'C:\\Program Files\\Python\\python.exe' tools/build.py fpga build"))
        local = tui.Plan(["sw", "build", "path with spaces"], ("sw", "build"), "Current host", "build")
        self.assertIn("'path with spaces'", tui.command_text(
            local, ROOT, "Windows", executable=r"C:\Python Folder\python.exe"))
        posix = tui.command_text(local, ROOT, "Linux", executable="/opt/Python Three/python3")
        self.assertEqual(posix, "'/opt/Python Three/python3' tools/build.py sw build 'path with spaces'")

    def test_text_default_is_a_placeholder_not_an_edit_prefix(self):
        terminal = ScriptedTerminal(["x", "ENTER"])
        self.assertEqual(tui.Menu(terminal).text("Value", default="default"), "x")
        terminal = ScriptedTerminal(["ENTER"])
        self.assertEqual(tui.Menu(terminal).text("Value", default="default"), "default")

    def test_questa_test_run_offers_compatible_label_selection(self):
        terminal = ScriptedTerminal(["DOWN", "ENTER",  # label mode
                                     *list("agents"), "ENTER"])
        selector = tui._test_selection(tui.Menu(terminal), ROOT, "questa")
        self.assertEqual(selector, ["--label", "agents"])

    def test_append_advanced_option_produces_repeated_flags(self):
        plan = tui.Plan(["tests", "list", "--level", "0"], ("tests", "list"), "Current host", "list")
        action = next(action for action in tui._option_actions(plan) if action.dest == "label")
        plan.set_options[action.dest] = ["builder", "host"]
        argv = tui.final_argv(plan)
        self.assertEqual(argv[-4:], ["--label", "builder", "--label", "host"])

    def test_launcher_ids_only_come_from_playable_checked_builds(self):
        with tempfile.TemporaryDirectory(prefix="tui build ids ") as temporary:
            root = Path(temporary)
            for target, byte in (("v05-board", b"play"), ("controls-board", b"controls")):
                output = root / f"workdir/builds/{target}/fpga/{target}/attempts/abc/output"
                output.mkdir(parents=True)
                sof = output / "design.sof"
                sof.write_bytes(byte)
                relative = sof.relative_to(root).as_posix()
                (output.parent / "result.json").write_text(json.dumps({
                    "status": "PASS", "target": target,
                    "build_id": ("01" if target == "v05-board" else "02") * 16,
                    "artifacts": {relative: hashlib.sha256(byte).hexdigest()}}))
            terminal = ScriptedTerminal(["ENTER"])
            selected = tui._launcher_build_id(tui.Menu(terminal), root)
            self.assertEqual(selected, "01" * 16)
            frame = "\n".join(terminal.frames[-1])
            self.assertIn("v05-board — workdir/builds/v05-board/fpga/v05-board/attempts/abc/output/design.sof", frame)
            self.assertIn("on-wire ID " + "01" * 16, frame)
            self.assertNotIn("Type another", frame)

    def test_launcher_has_no_manual_or_non_playable_identity_fallback(self):
        with tempfile.TemporaryDirectory(prefix="tui no playable ") as temporary:
            terminal = ScriptedTerminal(["ESC"])
            self.assertIs(tui._launcher_build_id(tui.Menu(terminal), Path(temporary)), tui.BACK)
            self.assertNotIn("Type another", "\n".join(terminal.frames[-1]))

        with patch("n2m.tui.checked_sofs", return_value=[
                ("workdir/builds/zero/output/design.sof", "v05-board", "0" * 32)]):
            self.assertEqual(tui._checked_build_ids(ROOT, target="v05-board"), [])

    def test_reviewed_host_identity_keeps_explicit_manual_path(self):
        value = "12" * 16
        terminal = ScriptedTerminal(["ENTER", *value, "ENTER"])
        self.assertEqual(tui._reviewed_build_id(tui.Menu(terminal), Path("missing-root")), value)

    def test_manual_reviewed_host_identity_reprompts_and_normalizes(self):
        value = "AB" * 16
        terminal = ScriptedTerminal(["ENTER", *("0" * 32), "ENTER", *"wrong", "ENTER",
                                     *value, "ENTER"])
        self.assertEqual(tui._reviewed_build_id(tui.Menu(terminal), Path("missing-root")), value.lower())
        self.assertIn("Build ID must be 32 hexadecimal digits and nonzero",
                      "\n".join(terminal.frames[-1]))

    def test_manual_uart_reprompts_and_normalizes_a_positive_com_port(self):
        terminal = ScriptedTerminal(["ENTER", *"COM 7", "ENTER", *"com7", "ENTER"])
        with patch("n2m.tui.uart_candidates", return_value=[]):
            self.assertEqual(tui._uart(tui.Menu(terminal), ROOT), "COM7")
        self.assertIn("UART port must be COM followed by a positive number",
                      "\n".join(terminal.frames[-1]))

    def test_doctor_full_environment_is_questa_on_windows_only(self):
        terminal = ScriptedTerminal(["DOWN", "ENTER", "ENTER"])
        plan = tui._doctor_plan(tui.Menu(terminal), ROOT)
        self.assertEqual(plan.argv, ["doctor", "--profile", "environment", "--sim", "questa"])
        self.assertEqual(plan.host, "Windows PowerShell")
        backend_frame = "\n".join(terminal.frames[-1])
        self.assertIn("Questa", backend_frame)
        self.assertNotIn("Verilator", backend_frame)
        self.assertTrue(tui.compatible_host(plan, "Windows"))
        self.assertFalse(tui.compatible_host(plan, "Linux"))

    def test_current_uart_candidates_reuse_read_only_discovery(self):
        with tempfile.TemporaryDirectory(prefix="tui uart ") as temporary:
            root = Path(temporary)
            calls = []
            def discover(folder, args):
                calls.append((folder, args))
                return {"ports": [
                    {"DeviceID": "COM7", "Status": "OK", "ConfigManagerErrorCode": 0},
                    {"DeviceID": "COM8", "Status": "Error", "ConfigManagerErrorCode": 10}]}
            with patch("n2m.host.transport.open_serial") as opened:
                self.assertEqual(tui.uart_candidates(root, system="Windows", discover=discover), ["COM7"])
                opened.assert_not_called()
            self.assertEqual(len(calls), 1)
            self.assertFalse(calls[0][0].exists(), "temporary discovery logs were not removed")

    @unittest.skipIf(os.name == "nt", "POSIX PTY contract")
    def test_real_posix_pty_enters_raw_mode_and_restores_it(self):
        import termios
        master, slave = os.openpty()
        reader = os.fdopen(os.dup(slave), "r", encoding="utf-8")
        writer = os.fdopen(os.dup(slave), "w", encoding="utf-8")
        self.addCleanup(reader.close)
        self.addCleanup(writer.close)
        self.addCleanup(lambda: os.close(master))
        self.addCleanup(lambda: os.close(slave))
        before = termios.tcgetattr(slave)
        terminal = tui.Terminal(stdin=reader, stdout=writer, system="Linux")
        self.assertTrue(terminal.interactive())
        with terminal:
            during = termios.tcgetattr(slave)
            self.assertFalse(during[3] & termios.ICANON)
            self.assertFalse(during[3] & termios.ECHO)
            self.assertEqual(during[1] & termios.OPOST, before[1] & termios.OPOST)
        self.assertEqual(termios.tcgetattr(slave), before)
        self.assertIn(b"\x1b[?25l", os.read(master, 128))

    def test_every_current_subaction_has_an_argparse_valid_plan(self):
        samples = {
            ("doctor",): ["doctor", "--sim", "verilator"],
            ("check",): ["check"],
            ("regress",): ["regress", "pre-merge", "--sim", "verilator"],
            ("clean",): ["clean", "--tag", "old-build"],
            ("sim", "test"): ["sim", "test", "builder-smoke", "--sim", "verilator"],
            ("sim", "preflight"): ["sim", "preflight", "python-joypad"],
            ("fpga", "build"): ["fpga", "build", "v05-board", "--quartus-bin", "tools"],
            ("fpga", "program"): ["fpga", "program", "--sof", "checked.sof", "--quartus-bin", "tools"],
            ("tests", "validate"): ["tests", "validate"],
            ("tests", "list"): ["tests", "list", "--level", "0"],
            ("tests", "affected"): ["tests", "affected", "--base", "origin/main"],
            ("tests", "run"): ["tests", "run", "--label", "agents", "--sim", "verilator"],
            ("sw", "oracle"): ["sw", "oracle"],
            ("sw", "assemble"): ["sw", "assemble", "assembler-basic"],
            ("sw", "build"): ["sw", "build", "springtrail"],
            ("sw", "conformance"): ["sw", "conformance"],
            ("sw", "link-conformance"): ["sw", "link-conformance"],
            ("sw", "asset-conformance"): ["sw", "asset-conformance"],
        }
        host_base = ["host"]
        for action in tui.command_actions(("host",)):
            argv = [*host_base, action, "--uart-port", "COM7"]
            if action == "load":
                argv += ["--external", "libbet"]
            elif action in ("step", "run-dots"):
                argv += ["--dots", "1"]
            elif action == "input":
                argv += ["--mask", "0"]
            elif action == "write":
                argv += ["--address", "0", "--value", "0"]
            elif action == "peek":
                argv += ["--store", sorted(interface_codec.PEEK_STORES)[0]]
            elif action in ("crc-proof", "keyboard"):
                argv += ["--expected-build-id", "00" * 16]
            samples[("host", action)] = argv
        expected = {(family, action) for family in ("sim", "fpga", "tests", "sw", "host")
                    for action in tui.command_actions((family,))}
        expected |= {("doctor",), ("check",), ("regress",), ("clean",)}
        self.assertEqual(set(samples), expected)
        from n2m.cli import parser
        for path, argv in samples.items():
            with self.subTest(path=path):
                parsed = parser().parse_args(argv)
                self.assertEqual((parsed.command,) + ((parsed.action,) if hasattr(parsed, "action") else ()), path)
                plan = tui.Plan(argv, path, "Current host", "test")
                tui.validate_plan(plan)
        launcher = tui.Plan(["--expected-build-id", "00" * 16, "--uart-port", "COM7"],
                            ("launcher",), "Windows PowerShell", "GUI")
        tui.validate_plan(launcher)

    def test_launcher_uses_its_parser_and_contract_before_review(self):
        from gb_launcher import parse_args
        valid = ["--expected-build-id", "00" * 16, "--uart-port", "COM7"]
        parsed = parse_args(valid, root=ROOT)
        self.assertEqual(parsed.expected_build_id, "00" * 16)
        self.assertEqual(parsed.uart_port, "COM7")
        self.assertEqual(parsed.seconds, 900)
        for option, fragment in ((["--seconds", "0"], "seconds 1..3600"),
                                 (["--seconds", "not-a-number"], "invalid int value"),
                                 (["--tag", "not-valid"], "tag must be alphanumeric")):
            with self.subTest(option=option), self.assertRaisesRegex(ValueError, fragment):
                tui.validate_plan(tui.Plan([*valid, *option], ("launcher",),
                                           "Windows PowerShell", "GUI"), ROOT)
            with self.subTest(direct_option=option), self.assertRaises(SystemExit), \
                    contextlib.redirect_stderr(io.StringIO()):
                parse_args([*valid, *option], root=ROOT)
        actions = {action.dest for action in tui._option_actions(tui.Plan(
            valid, ("launcher",), "Windows PowerShell", "GUI"))}
        self.assertEqual(actions, {"uart_vid", "uart_pid", "uart_identity", "tag", "seconds"})

    def test_advanced_options_follow_backend_profile_and_mutex_contracts(self):
        def options(argv, path):
            return {action.dest for action in tui._option_actions(
                tui.Plan(argv, path, "Current host", "test"), ROOT)}
        verilator = options(["sim", "test", "builder-smoke", "--sim", "verilator"], ("sim", "test"))
        self.assertIn("verilator_bin", verilator)
        self.assertNotIn("questa_bin", verilator)
        self.assertNotIn("intel_sim_lib", verilator)
        questa = options(["sim", "test", "builder-smoke", "--sim", "questa"], ("sim", "test"))
        self.assertNotIn("verilator_bin", questa)
        self.assertIn("questa_bin", questa)
        self.assertNotIn("intel_sim_lib", questa)
        vendor = options(["sim", "test", "python-v05-continuous", "--sim", "questa"],
                         ("sim", "test"))
        self.assertIn("intel_sim_lib", vendor)

        self.assertNotIn("intel_sim_lib", options(
            ["regress", "pre-merge", "--sim", "questa"], ("regress",)))
        self.assertIn("intel_sim_lib", options(
            ["regress", "composed-smoke", "--sim", "questa"], ("regress",)))
        self.assertNotIn("intel_sim_lib", options(
            ["tests", "run", "--level", "0", "--sim", "questa"], ("tests", "run")))
        self.assertIn("intel_sim_lib", options(
            ["tests", "run", "--level", "1", "--sim", "questa"], ("tests", "run")))

        simulation = options(["doctor", "--profile", "simulation", "--sim", "verilator"], ("doctor",))
        self.assertNotIn("quartus_bin", simulation)
        self.assertNotIn("jtag_cable", simulation)
        self.assertNotIn("uart_port", simulation)
        environment = options(["doctor", "--profile", "environment", "--sim", "questa"], ("doctor",))
        self.assertIn("quartus_bin", environment)
        self.assertIn("jtag_cable", environment)
        self.assertIn("uart_port", environment)

        load = tui.Plan(["host", "load", "--uart-port", "COM7", "--package", "checked.json"],
                        ("host", "load"), "Windows PowerShell", "load")
        self.assertNotIn("external", options(load.argv, load.parser_path))
        load.set_options["tag"] = "load1"
        self.assertNotIn("--external", tui.final_argv(load))

        for target, expected in (("builder-smoke", False), ("controls-board", True),
                                 ("v05-board", True), ("v05-controls-board", True)):
            with self.subTest(fpga_target=target):
                build = options(["fpga", "build", target, "--quartus-bin", "tools"],
                                ("fpga", "build"))
                self.assertEqual("build_id" in build, expected)

    def test_keyboard_review_and_advanced_match_classic_console_contract(self):
        plan = tui.Plan(["host", "keyboard", "--uart-port", "COM7",
                         "--expected-build-id", "01" * 16],
                        ("host", "keyboard"), "Windows classic conhost.exe cmd.exe", "keys")
        options = {action.dest for action in tui._option_actions(plan, ROOT)}
        self.assertNotIn("endpoint_restarted", options)
        self.assertNotIn("json", options)
        command = tui.command_text(plan, ROOT, "Windows", executable=r"C:\Python Folder\python.exe")
        self.assertTrue(command.startswith(
            '"C:\\Python Folder\\python.exe" "tools/build.py" "host" "keyboard"'))
        self.assertIn('"--uart-port" "COM7"', command)
        self.assertTrue(tui.compatible_host(plan, "Windows", classic_console=lambda: True))
        self.assertFalse(tui.compatible_host(plan, "Windows", classic_console=lambda: False))
        self.assertFalse(tui.compatible_host(plan, "Linux"))
        terminal = ScriptedTerminal(["DOWN", "ENTER"])
        self.assertEqual(tui.choose_execution(tui.Menu(terminal), plan, ROOT, "Linux"), "cancel")
        self.assertIn("Native host: Windows classic conhost.exe cmd.exe", "\n".join(terminal.frames[-1]))

        with patch("n2m.host.transport.open_serial") as serial:
            valid = ScriptedTerminal(["ENTER"])
            self.assertEqual(tui.choose_execution(tui.Menu(valid), plan, ROOT, "Windows",
                                                  classic_console=lambda: True), "run")
            invalid = ScriptedTerminal(["DOWN", "ENTER"])
            self.assertEqual(tui.choose_execution(tui.Menu(invalid), plan, ROOT, "Windows",
                                                  classic_console=lambda: False), "cancel")
            self.assertNotIn("Run now", "\n".join(invalid.frames[-1]))
            serial.assert_not_called()

        crc = tui.Plan(["host", "crc-proof", "--uart-port", "COM7",
                        "--expected-build-id", "01" * 16],
                       ("host", "crc-proof"), "Windows PowerShell", "proof")
        self.assertNotIn("endpoint_restarted",
                         {action.dest for action in tui._option_actions(crc, ROOT)})

    def test_cmd_review_quotes_every_token_and_refuses_expansion_sensitive_values(self):
        identity = r"USB\VID_0403&PID_6001\SERIAL"
        plan = tui.Plan(["host", "keyboard", "--uart-port", "COM7",
                         "--uart-identity", identity,
                         "--expected-build-id", "01" * 16],
                        ("host", "keyboard"), "Windows classic conhost.exe cmd.exe", "keys")
        command = tui.command_text(plan, ROOT, "Windows",
                                   executable=r"C:\Program Files\Python\python.exe")
        self.assertTrue(command.startswith(
            '"C:\\Program Files\\Python\\python.exe" "tools/build.py"'))
        self.assertIn('"' + identity + '"', command)
        self.assertIn('"--uart-port" "COM7"', command)

        metacharacters = tui.Plan(["host", "keyboard", "--uart-port", "COM7",
                                   "--expected-build-id", "01" * 16],
                                  ("host", "keyboard"),
                                  "Windows classic conhost.exe cmd.exe", "keys")
        self.assertIn('"C:\\Python ^|<>()& Tools\\python.exe"', tui.command_text(
            metacharacters, ROOT, "Windows",
            executable=r"C:\Python ^|<>()& Tools\python.exe"))
        for unsafe in ("bad%PATH%", "bad!value", "bad\rvalue", "bad\nvalue", "bad\0value",
                       'bad"value'):
            with self.subTest(unsafe=repr(unsafe)), self.assertRaisesRegex(
                    ValueError, "classic cmd.exe review"):
                refused = tui.Plan(["host", "keyboard", "--uart-port", unsafe,
                                    "--expected-build-id", "01" * 16],
                                   ("host", "keyboard"),
                                   "Windows classic conhost.exe cmd.exe", "keys")
                tui.command_text(refused, ROOT, "Windows", executable=r"C:\Python\python.exe")

    def test_foreign_host_commands_use_the_destination_python_launcher(self):
        windows = tui.Plan(["fpga", "build", "v05-board", "--quartus-bin", "tools"],
                           ("fpga", "build"), "Windows PowerShell", "build")
        wsl = tui.Plan(["sim", "test", "builder-smoke", "--sim", "verilator"],
                       ("sim", "test"), "WSL Linux", "simulate")
        with patch("n2m.tui.sys.executable", "/usr/bin/python3"):
            self.assertTrue(tui.command_text(windows, ROOT, "Linux").startswith("& python tools/build.py"))
        with patch("n2m.tui.sys.executable", r"C:\Python Folder\python.exe"):
            self.assertTrue(tui.command_text(wsl, ROOT, "Windows").startswith("python3 tools/build.py"))
        apostrophe = tui.Plan(["sw", "build", "owner's path"], ("sw", "build"),
                              "WSL Linux", "build")
        self.assertEqual(tui.command_text(apostrophe, ROOT, "Windows"),
                         "python3 tools/build.py sw build 'owner'\"'\"'s path'")

    def test_sparse_and_backend_specific_level_label_pairs_remain_selectable(self):
        model = {"labels": {"audio": "audio checks", "builder": "builder checks"},
                 "units": {
                     "audio-q": {"kind": "sim", "level": 2, "labels": ["audio"]},
                     "builder-q": {"kind": "sim", "level": 0, "labels": ["builder"]},
                     "builder-v": {"kind": "sim", "level": 1, "labels": ["builder"]}}}
        with tempfile.TemporaryDirectory(prefix="tui catalogue ") as temporary:
            root = Path(temporary)
            targets = root / "src/dv/builder/targets.json"
            targets.parent.mkdir(parents=True)
            targets.write_text(json.dumps({
                "audio-q": {"simulators": ["questa"]},
                "builder-q": {"simulators": ["questa"]},
                "builder-v": {"simulators": ["verilator"]}}))
            with patch("n2m.tui.catalogue.load", return_value=(model, {})):
                audio = ScriptedTerminal(["ENTER"])
                self.assertEqual(tui._catalogue_selector(tui.Menu(audio), root, "questa", ("audio",)), 2)
                self.assertNotIn("Level 0", "\n".join(audio.frames[-1]))
                builder = ScriptedTerminal([*list("builder"), "ENTER"])
                self.assertEqual(tui._catalogue_label(tui.Menu(builder), root, "questa", paired=True), "builder")
                level = ScriptedTerminal(["ENTER"])
                self.assertEqual(tui._catalogue_selector(tui.Menu(level), root, "questa", ("builder",)), 0)
                self.assertNotIn("Level 1", "\n".join(level.frames[-1]))

    def test_nested_escape_returns_one_page_and_retries_do_not_recurse(self):
        manual = ScriptedTerminal(["ENTER", "ESC", "ESC"])
        self.assertIs(tui._manual_value(tui.Menu(manual), "Tool", ()), tui.BACK)
        self.assertEqual(sum(frame[0] == "Tool" for frame in manual.frames), 3)

        selector = ScriptedTerminal(["ENTER", "ESC", "ESC"])
        self.assertIs(tui._test_selection(tui.Menu(selector), ROOT, "verilator"), tui.BACK)
        self.assertEqual(sum(frame[0] == "Select tests by" for frame in selector.frames), 2)

        for function in (tui._sim_plan, tui._tests_plan, tui._fpga_plan,
                         tui._sw_plan, tui._host_plan, tui._test_selection):
            with self.subTest(function=function.__name__):
                body = "\n".join(inspect.getsource(function).splitlines()[1:])
                self.assertNotIn(function.__name__ + "(", body)
        repeated = ScriptedTerminal(["ENTER", "ESC"] * 100 + ["ESC"])
        self.assertIs(tui._sim_plan(tui.Menu(repeated), ROOT), tui.BACK)

    def test_windows_console_mode_precedes_ansi_and_restores_on_every_exit(self):
        events = []
        class Mode:
            def __enter__(self):
                events.append("mode-enter")
            def __exit__(self, *error):
                events.append(("mode-exit", error[0]))
        class Output(io.StringIO):
            def write(self, value):
                events.append(("write", value))
                return super().write(value)

        output = Output()
        with tui.Terminal(stdout=output, system="Windows", windows_console=Mode()):
            events.append("body")
        self.assertEqual(events[0], "mode-enter")
        self.assertEqual(events[1], ("write", "\x1b[?25l"))
        self.assertEqual(events[-2], ("write", "\x1b[?25h\x1b[0m\n"))
        self.assertEqual(events[-1], ("mode-exit", None))

        events.clear()
        with self.assertRaisesRegex(RuntimeError, "body failure"):
            with tui.Terminal(stdout=Output(), system="Windows", windows_console=Mode()):
                raise RuntimeError("body failure")
        self.assertEqual(events[-1], ("mode-exit", RuntimeError))

        class Unavailable:
            def __enter__(self):
                raise OSError("no console")
        output = io.StringIO()
        with self.assertRaisesRegex(OSError, "no console"):
            tui.Terminal(stdout=output, system="Windows", windows_console=Unavailable()).__enter__()
        self.assertEqual(output.getvalue(), "")

    def test_windows_console_mode_sets_required_bits_then_restores(self):
        calls = []
        class Kernel:
            def GetStdHandle(self, _):
                return 7
            def GetConsoleMode(self, handle, pointer):
                pointer._obj.value = 0x2
                return 1
            def SetConsoleMode(self, handle, mode):
                calls.append((handle, mode))
                return 1
        with tui_terminal.WindowsConsoleMode(Kernel()):
            pass
        self.assertEqual(calls, [(7, 0x7), (7, 0x2)])

    @unittest.skipIf(os.name == "nt", "POSIX PTY contract")
    def test_posix_enter_write_failure_restores_terminal_mode(self):
        import termios
        master, slave = os.openpty()
        reader = os.fdopen(os.dup(slave), "r", encoding="utf-8")
        class BrokenOutput:
            def write(self, _):
                raise OSError("output failed")
            def flush(self):
                pass
        try:
            before = termios.tcgetattr(slave)
            with self.assertRaisesRegex(OSError, "output failed"):
                tui.Terminal(stdin=reader, stdout=BrokenOutput(), system="Linux").__enter__()
            self.assertEqual(termios.tcgetattr(slave), before)
        finally:
            reader.close()
            os.close(master)
            os.close(slave)

    def test_each_leaf_plan_is_complete_before_review(self):
        incomplete = tui.Plan(["fpga", "build", "v05-board"], ("fpga", "build"),
                              "Windows PowerShell", "build")
        with self.assertRaisesRegex(ValueError, "quartus-bin"):
            tui.validate_plan(incomplete)

    def test_foreign_host_review_has_no_run_choice(self):
        plan = tui.Plan(["fpga", "build", "v05-board", "--quartus-bin", "tools"], ("fpga", "build"),
                        "Windows PowerShell", "compile")
        terminal = ScriptedTerminal(["DOWN", "ENTER"])
        self.assertEqual(tui.choose_execution(tui.Menu(terminal), plan, ROOT, "Linux"), "cancel")
        review = "\n".join(terminal.frames[-1])
        self.assertNotIn("Run now", review)
        self.assertIn("will not bridge hosts", review)

    def test_full_sim_selection_delegates_to_public_builder_as_vector(self):
        # Intent Sim is the fourth row after Play, Doctor and Check. The target
        # is found by typing, so registry growth does not affect this script.
        keys = ["DOWN", "DOWN", "DOWN", "ENTER", "ENTER", "ENTER",
                *list("builder-smoke"), "ENTER", "ENTER", "ENTER"]
        terminal = ScriptedTerminal(keys)
        completed = Mock(returncode=7)
        runner = Mock(return_value=completed)
        code = tui.run(ROOT, terminal=terminal, runner=runner, system="Linux")
        self.assertEqual(code, 7)
        command = runner.call_args.args[0]
        self.assertEqual(command[:2], [sys.executable, str(ROOT / "tools/build.py")])
        self.assertEqual(command[2:7], ["sim", "test", "builder-smoke", "--sim", "verilator"])
        self.assertEqual(runner.call_args.kwargs, {"cwd": ROOT, "shell": False})

    def test_escape_from_advanced_reopens_the_last_required_decision(self):
        keys = ["DOWN", "DOWN", "DOWN", "ENTER", "ENTER", "ENTER",
                *list("builder-smoke"), "ENTER",
                "ESC",                  # Advanced -> selected target
                "ESC",                  # Target -> backend
                "DOWN", "ENTER",       # Questa
                *list("builder-smoke"), "ENTER",
                "ENTER",                # Advanced Done
                "DOWN", "DOWN", "ENTER"]  # Cancel at review
        terminal = ScriptedTerminal(keys)
        runner = Mock()
        self.assertEqual(tui.run(ROOT, terminal=terminal, runner=runner, system="Windows"), 0)
        runner.assert_not_called()
        self.assertGreaterEqual(sum(frame[0] == "Select simulator" for frame in terminal.frames), 2)

    def test_escape_from_zero_choice_leaf_reopens_its_family_action(self):
        for query, intent, action, title in (("verification", "tests", "validate", "Verification action"),
                                             ("software", "sw", "oracle", "Software action")):
            with self.subTest(intent=intent, action=action):
                terminal = ScriptedTerminal([*query, "ENTER", *action, "ENTER",
                                             "ESC", "ESC", "ESC"])
                self.assertIs(tui.select_command(tui.Menu(terminal), ROOT), tui.CANCEL)
                headings = [frame[0] for frame in terminal.frames]
                self.assertGreaterEqual(headings.count(title), 2)
                second_action = len(headings) - 1 - headings[::-1].index(title)
                self.assertLess(second_action, len(headings) - 1)
                self.assertEqual(headings[-1], "nand2mario build menu")

        check = ScriptedTerminal([*"check", "ENTER", "ESC", "ESC"])
        self.assertIs(tui.select_command(tui.Menu(check), ROOT), tui.CANCEL)
        self.assertNotIn("Builder action", [frame[0] for frame in check.frames])

    def test_launcher_delegates_to_existing_gui_only_after_confirmation(self):
        plan = tui.Plan(["--expected-build-id", "00" * 16, "--uart-port", "COM7"],
                        ("launcher",), "Windows PowerShell", "GUI")
        runner = Mock(return_value=Mock(returncode=0))
        terminal = ScriptedTerminal([])
        with patch("n2m.tui.select_command", return_value=plan):
            self.assertEqual(tui.run(ROOT, terminal=terminal, runner=runner, system="Windows"), 0)
        command = runner.call_args.args[0]
        self.assertEqual(command[1], str(ROOT / "tools/gb_launcher.py"))
        self.assertIn("COM7", command)
        self.assertFalse(runner.call_args.kwargs["shell"])

    def test_launcher_review_names_uart_transmission_and_gui_effects(self):
        with patch("n2m.tui._launcher_build_id", return_value="00" * 16), \
                patch("n2m.tui._uart", return_value="COM7"):
            plan = tui._launcher_plan(tui.Menu(ScriptedTerminal([])), ROOT)
        terminal = ScriptedTerminal(["ENTER"])
        self.assertEqual(tui.choose_execution(tui.Menu(terminal), plan, ROOT, "Windows"), "run")
        review = "\n".join(terminal.frames[-1])
        self.assertIn("Open UART", review)
        self.assertIn("TRANSMIT load/reset/run/control operations", review)
        self.assertIn("LAUNCH the game catalogue GUI", review)

    def test_non_tty_and_cancel_never_spawn_anything(self):
        runner = Mock()
        with patch("sys.stderr", new=io.StringIO()) as errors, \
                patch("n2m.tui.sys.executable", "/usr/bin/python3"):
            self.assertEqual(tui.run(ROOT, terminal=ScriptedTerminal([], False), runner=runner), 2)
        self.assertIn("`/usr/bin/python3 tools/build.py --help`", errors.getvalue())
        runner.assert_not_called()
        with patch("n2m.tui.select_command", return_value=tui.CANCEL):
            self.assertEqual(tui.run(ROOT, terminal=ScriptedTerminal([]), runner=runner), 0)
        runner.assert_not_called()

    def test_both_tui_spellings_enter_before_argparse_and_budget_dispatch(self):
        from n2m.test_budget import main
        for spelling in ("-tui", "--tui"):
            with self.subTest(spelling=spelling), \
                 patch("sys.argv", ["tools/build.py", spelling]), \
                 patch("n2m.tui.run", return_value=9) as launch:
                self.assertEqual(main(), 9)
                launch.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
