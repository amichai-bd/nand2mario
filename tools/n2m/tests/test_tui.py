"""Scripted build-menu checks; no simulator, FPGA, UART or GUI is opened."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import interface_codec, tui


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
            self.assertEqual(tui.checked_sofs(root),
                             [(relative, "v05-board", "ffeeddccbbaa99887766554433221100")])

    def test_powershell_review_quotes_paths_with_spaces(self):
        plan = tui.Plan(["fpga", "build", "v05-board", "--quartus-bin",
                         r"C:\Program Files\Intel FPGA\bin64"],
                        ("fpga", "build"), "Windows PowerShell", "build")
        text = tui.command_text(plan, ROOT, "Windows")
        self.assertIn("'C:\\Program Files\\Intel FPGA\\bin64'", text)
        self.assertTrue(text.startswith("python tools/build.py fpga build"))
        local = tui.Plan(["sw", "build", "path with spaces"], ("sw", "build"), "Current host", "build")
        self.assertIn("'path with spaces'", tui.command_text(local, ROOT, "Windows"))

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
            selected = tui._wire_id(tui.Menu(terminal), root)
            self.assertEqual(selected, "01" * 16)

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

    def test_launcher_delegates_to_existing_gui_only_after_confirmation(self):
        plan = tui.Plan(["--expected-build-id", "00" * 16, "--uart-port", "COM 7"],
                        ("launcher",), "Windows PowerShell", "GUI")
        runner = Mock(return_value=Mock(returncode=0))
        terminal = ScriptedTerminal([])
        with patch("n2m.tui.select_command", return_value=plan):
            self.assertEqual(tui.run(ROOT, terminal=terminal, runner=runner, system="Windows"), 0)
        command = runner.call_args.args[0]
        self.assertEqual(command[1], str(ROOT / "tools/gb_launcher.py"))
        self.assertIn("COM 7", command)
        self.assertFalse(runner.call_args.kwargs["shell"])

    def test_non_tty_and_cancel_never_spawn_anything(self):
        runner = Mock()
        with patch("sys.stderr", new=io.StringIO()) as errors:
            self.assertEqual(tui.run(ROOT, terminal=ScriptedTerminal([], False), runner=runner), 2)
        self.assertIn("--help", errors.getvalue())
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
