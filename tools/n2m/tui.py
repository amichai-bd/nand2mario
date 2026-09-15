"""Progressive keyboard menu for the existing public build commands.

The menu only selects and reviews an argument vector.  Execution always starts
the public ``tools/build.py`` entry point again, without a shell, so command
ownership, budgets, locks and retained records stay with their existing owners.
"""
from dataclasses import dataclass, field
import argparse
import contextlib
import io
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys

from . import catalogue, interface_codec
from .fpga import identity_target, target_definition
from .progress import powershell_command
from .tui_choices import (build_tags, checked_packages, checked_sofs, command_actions,
                          external_images, fpga_targets, parser_at,
                          regression_subsets, retained_simulator_directory,
                          retained_values, simulation_targets,
                          selection_uses_vendor_model, software_targets,
                          top_families, compatible_selection, uart_candidates)
from .tui_terminal import (BACK, VIEW_ROWS, Choice, Menu, Terminal, decode_posix,
                           decode_windows)


CANCEL = object()


@dataclass
class Plan:
    argv: list
    parser_path: tuple
    host: str
    effect: str
    set_options: dict = field(default_factory=dict)
    editor: object = None
    back_to_action: bool = False




INTENTS = {
    "doctor": ("Inspect environment", "Readiness checks; simulation profile may run a smoke simulation"),
    "check": ("Check builder", "Run the builder's host test suite"),
    "sim": ("Run a simulation", "Compile, run and check simulation evidence"),
    "regress": ("Run a regression", "Run a declared simulation subset"),
    "tests": ("Run or inspect verification", "Validate, list, explain or run the test catalogue"),
    "clean": ("Clean one build", "Delete exactly one selected build tag"),
    "fpga": ("Build or program the FPGA", "Build a checked image or program the attached FPGA"),
    "lint": ("Gate RTL under Questa", "Compile and elaborate product RTL and FPGA tops; no simulation"),
    "sw": ("Build software", "Assemble, link, package or check original software"),
    "host": ("Use UART controls", "Open the selected UART and transmit a host operation"),
}


def _named(values):
    return [Choice(value, str(value)) for value in values]


def _manual_value(menu, title, retained=(), *, allow_default=False, validator=None,
                  invalid_title=None, normalize=lambda value: value):
    options = [Choice(value, value, "reused from a retained local result") for value in retained]
    if allow_default:
        options.append(Choice(None, "Use ordinary PATH discovery"))
    options.append(Choice("__manual__", "Type another value…"))
    while True:
        selected = menu.choose(title, options)
        if selected is BACK:
            return BACK
        if selected != "__manual__":
            selected = normalize(selected)
            if validator is None or validator(selected):
                return selected
            continue
        prompt = title
        while True:
            value = menu.text(prompt)
            if value is BACK:
                break
            value = normalize(value)
            if validator is None or validator(value):
                return value
            prompt = invalid_title or title


def _backend(menu, title="Select simulator"):
    choices = [Choice("verilator", "Verilator", "Runs natively on WSL Linux; no license"),
               Choice("questa", "Questa", "Runs natively on Windows PowerShell; license required")]
    return menu.choose(title, choices, hint="Use arrows and Enter. Escape goes back.")


def _uart(menu, root):
    return _manual_value(
        menu, "Select UART port", uart_candidates(root),
        validator=lambda value: bool(re.fullmatch(r"COM[1-9][0-9]*", value)),
        invalid_title="UART port must be COM followed by a positive number",
        normalize=lambda value: value.upper())


def _checked_build_ids(root, *, target=None):
    return [Choice(build_id, f"{fpga_target or 'unknown target'} — {path}",
                   f"on-wire ID {build_id}")
            for path, fpga_target, build_id in checked_sofs(root)
            if isinstance(build_id, str) and re.fullmatch(r"[0-9a-fA-F]{32}", build_id)
            and int(build_id, 16) != 0 and (target is None or fpga_target == target)]


def _launcher_build_id(menu, root):
    return menu.choose("Select checked playable FPGA build", _checked_build_ids(root, target="v05-board"))


def _reviewed_build_id(menu, root):
    choices = _checked_build_ids(root)
    choices.append(Choice("__manual__", "Type another reviewed build ID…"))
    while True:
        selected = menu.choose("Select reviewed on-wire build ID", choices)
        if selected is BACK:
            return BACK
        if selected != "__manual__":
            return selected
        title = "Reviewed 32-digit on-wire build ID"
        while True:
            value = menu.text(title)
            if value is BACK:
                break
            if re.fullmatch(r"[0-9a-fA-F]{32}", value) and int(value, 16) != 0:
                return value.lower()
            title = "Build ID must be 32 hexadecimal digits and nonzero"


def _quartus(menu, root):
    return _manual_value(menu, "Select Quartus bin directory", retained_values(root, "quartus_bin"))


def _collect(menu, steps, answers=None, start=0):
    """Run dynamic decision pages with exact Escape-to-previous behavior."""
    answers, index = dict(answers or {}), start
    while index < len(steps):
        key, action = steps[index]
        value = action(answers)
        if value is BACK:
            if index == 0:
                return BACK
            index -= 1
            for stale, _ in steps[index:]:
                answers.pop(stale, None)
            continue
        answers[key] = value
        index += 1
    return answers


def _editable(menu, steps, factory):
    answers = _collect(menu, steps)
    if answers is BACK:
        return BACK

    def make(values):
        plan = factory(values)
        def edit(active_menu):
            updated = _collect(active_menu, steps, values, len(steps) - 1)
            return BACK if updated is BACK else make(updated)
        plan.editor = edit
        return plan
    return make(answers)


def _sim_plan(menu, root):
    while True:
        action = menu.choose("Simulation action", _named(command_actions(("sim",))))
        if action is BACK:
            return BACK
        if action == "test":
            steps = [
                ("sim", lambda _: _backend(menu)),
                ("target", lambda a: menu.choose(
                    "Select simulation test", _named(simulation_targets(root, a["sim"]))))]
            plan = _editable(menu, steps, lambda answers: _simulator_default(Plan(
                ["sim", "test", answers["target"], "--sim", answers["sim"]],
                ("sim", "test"), _sim_host(answers["sim"]), "Build, run and check a simulation"), root))
        else:
            targets = simulation_targets(root, None, preflight=True)
            plan = _editable(menu, [("target", lambda _: menu.choose(
                "Select fixture preflight", _named(targets)))], lambda answers: Plan(
                    ["sim", "preflight", answers["target"]], ("sim", "preflight"),
                    "Current host", "Build and check a fixture; no simulator"))
        if plan is not BACK:
            return plan


def _doctor_plan(menu, root):
    steps = [
        ("profile", lambda _: menu.choose("Select readiness scope", [
            Choice("simulation", "Simulation", "Run the selected simulator smoke only"),
            Choice("environment", "Full Windows environment", "Inspect Questa, Quartus, JTAG and UART without programming or transmission")])),
        ("sim", lambda answers: menu.choose(
            "Select simulator" if answers["profile"] == "simulation" else "Full environment simulator",
            [Choice("verilator", "Verilator", "Runs natively on WSL Linux; no license"),
             Choice("questa", "Questa", "Runs natively on Windows PowerShell; license required")]
            if answers["profile"] == "simulation" else
            [Choice("questa", "Questa", "The full hardware environment is Windows-owned")]))]
    return _editable(menu, steps, lambda answers: _simulator_default(Plan(
                ["doctor", "--profile", answers["profile"], "--sim", answers["sim"]],
                ("doctor",), _sim_host(answers["sim"]),
                "Run simulator smoke" + (" and read-only device discovery" if answers["profile"] == "environment" else "")), root))


def _regress_plan(menu, root):
    steps = [
        ("sim", lambda _: _backend(menu)),
        ("subset", lambda a: menu.choose("Select compatible regression", regression_subsets(root, a["sim"])))]
    return _editable(menu, steps, lambda answers: _simulator_default(Plan(
        ["regress", answers["subset"], "--sim", answers["sim"]], ("regress",),
        _sim_host(answers["sim"]), "Run a bounded simulation regression"), root))


def _available_selection(root, model, backend, *, level=None, labels=()):
    try:
        selected, _ = catalogue.select(model, level, labels)
    except ValueError:
        return None
    if backend is not None and not compatible_selection(
            root, model, backend, level=level, labels=labels):
        return None
    return selected


def _catalogue_selector(menu, root, backend=None, labels=()):
    model, _ = catalogue.load(root)
    levels = []
    for level in catalogue.LEVELS:
        selected = _available_selection(root, model, backend, level=level, labels=labels)
        if selected is not None:
            levels.append(Choice(level, f"Level {level}", f"{len(selected)} catalogue units"))
    return menu.choose("Select verification level", levels)


def _catalogue_label(menu, root, backend=None, *, paired=False):
    model, _ = catalogue.load(root)
    choices = []
    for label, detail in sorted(model["labels"].items()):
        pairs = [level for level in catalogue.LEVELS
                 if _available_selection(root, model, backend, level=level,
                                         labels=(label,)) is not None]
        selected = _available_selection(root, model, backend, labels=(label,))
        if pairs and (paired or selected is not None):
            count = len(selected) if selected is not None else len(
                _available_selection(root, model, backend, level=pairs[-1], labels=(label,)))
            choices.append(Choice(label, label, f"{count} units — {detail}"))
    return menu.choose("Select verification label", choices)


def _test_selection(menu, root, backend=None):
    while True:
        mode = menu.choose("Select tests by", [Choice("level", "Confidence level"),
                                                Choice("label", "Subsystem label"),
                                                Choice("both", "Level and label")])
        if mode is BACK:
            return BACK
        if mode == "level":
            level = _catalogue_selector(menu, root, backend)
            if level is not BACK:
                return ["--level", str(level)]
            continue
        while True:
            label = _catalogue_label(menu, root, backend, paired=mode == "both")
            if label is BACK:
                break
            if mode == "label":
                return ["--label", label]
            level = _catalogue_selector(menu, root, backend, (label,))
            if level is not BACK:
                return ["--level", str(level), "--label", label]


def _tests_plan(menu, root):
    while True:
        action = menu.choose("Verification action", _named(command_actions(("tests",))))
        if action is BACK:
            return BACK
        if action == "validate":
            return Plan(["tests", action], ("tests", action), "Current host",
                        "Validate the test catalogue", back_to_action=True)
        if action == "affected":
            plan = _editable(menu, [("base", lambda _: menu.text(
                "Git base reference", default="origin/main"))], lambda answers: Plan(
                    ["tests", action, "--base", answers["base"]], ("tests", action),
                    "Current host", "Inspect repository impact; no tests"))
        elif action == "list":
            plan = _editable(menu, [("selector", lambda _: _test_selection(menu, root))], lambda answers: Plan(
                ["tests", action, *answers["selector"]], ("tests", action), "Current host",
                "List matching tests; no tests run"))
        else:
            steps = [("sim", lambda _: _backend(menu)),
                     ("selector", lambda a: _test_selection(menu, root, a["sim"]))]
            plan = _editable(menu, steps, lambda answers: _simulator_default(Plan(
                ["tests", action, *answers["selector"], "--sim", answers["sim"]],
                ("tests", action), _sim_host(answers["sim"]),
                "Run the selected unit and simulation tests"), root))
        if plan is not BACK:
            return plan


def _fpga_plan(menu, root):
    while True:
        action = menu.choose("FPGA action", _named(command_actions(("fpga",))))
        if action is BACK:
            return BACK
        if action == "build":
            steps = [
                ("target", lambda _: menu.choose("Select FPGA target", _named(fpga_targets(root)))),
                ("quartus", lambda _: _quartus(menu, root))]
            plan = _editable(menu, steps, lambda answers: Plan(
                ["fpga", "build", answers["target"], "--quartus-bin", answers["quartus"]],
                ("fpga", "build"), "Windows PowerShell",
                "Compile and check an FPGA image; no programming"))
        else:
            sofs = [Choice(path, f"{target or 'unknown target'} — {path}",
                           f"on-wire ID {build_id}" if build_id else "checked attempt")
                    for path, target, build_id in checked_sofs(root)]
            steps = [("sof", lambda _: menu.choose("Select checked FPGA image", sofs)),
                     ("quartus", lambda _: _quartus(menu, root))]
            plan = _editable(menu, steps, lambda answers: Plan(
                ["fpga", "program", "--sof", answers["sof"], "--quartus-bin", answers["quartus"]],
                ("fpga", "program"), "Windows PowerShell", "PROGRAM the attached FPGA over JTAG"))
        if plan is not BACK:
            return plan


def _sw_plan(menu, root):
    effects = {"oracle": "Run the pinned RGBDS comparison", "assemble": "Assemble original software",
               "build": "Build and package original software", "conformance": "Run assembler conformance",
               "link-conformance": "Run linker/package conformance", "asset-conformance": "Run asset conformance"}
    while True:
        action = menu.choose("Software action", _named(command_actions(("sw",))))
        if action is BACK:
            return BACK
        argv = ["sw", action]
        if action not in ("assemble", "build"):
            return Plan(argv, ("sw", action), "Current host", effects[action],
                        back_to_action=True)
        plan = _editable(menu, [("target", lambda _: menu.choose(
            "Select software target", _named(software_targets(root, action))))], lambda answers: Plan(
                [*argv, answers["target"]], ("sw", action), "Current host", effects[action]))
        if plan is not BACK:
            return plan


def _host_steps(menu, root, action):
    steps = [("uart", lambda _: _uart(menu, root))]
    if action == "load":
        steps.append(("source", lambda _: menu.choose("Select image source", [
            Choice("package", "Checked local package"), Choice("external", "Pinned external image")])))
        steps.append(("image", lambda a: menu.choose(
            "Select checked package" if a["source"] == "package" else "Select pinned external image",
            _named(checked_packages(root) if a["source"] == "package" else external_images(root)))))
    if action in ("step", "run-dots"):
        steps.append(("dots", lambda _: menu.text("Dot count", default="1")))
    if action == "input":
        steps.append(("mask", lambda _: menu.text("Input mask (for example 0x01)", default="0")))
    if action == "peek":
        steps.append(("store", lambda _: menu.choose("Storage to read", _named(sorted(interface_codec.PEEK_STORES)))))
    if action == "write":
        steps += [("address", lambda _: menu.text("Host register address")),
                  ("value", lambda _: menu.text("Value"))]
    if action in ("sdram-write", "sdram-read"):
        steps.append(("address", lambda _: menu.text("Line-aligned SDRAM device address (for example 0x0)", default="0x0")))
    if action == "sdram-write":
        steps.append(("data", lambda _: menu.text("Sixteen line bytes as 32 hex digits", default="00" * 16)))
    if action == "sdram-read":
        steps.append(("lines", lambda _: menu.text("Lines to read (1-15)", default="1")))
    if action == "sdram-test":
        steps += [("start", lambda _: menu.text("Line-aligned start address", default="0x0")),
                  ("length", lambda _: menu.text("Bytes to test, a line multiple", default="0x8000"))]
    if action in ("crc-proof", "keyboard"):
        steps.append(("build", lambda _: _reviewed_build_id(menu, root)))
    if action == "library":
        steps.append(("verb", lambda _: menu.choose("Library action", [
            Choice("load", "Load one checked package into slot 0 and verify"), Choice("status", "Read the catalogue")])))
        steps.append(("image", lambda a: "" if a["verb"] == "status" else menu.choose(
            "Select checked package for slot 0", _named(checked_packages(root)))))
    return steps


def _host_plan(menu, root):
    while True:
        action = menu.choose("UART action", _named(command_actions(("host",))))
        if action is BACK:
            return BACK
        def factory(answers):
            argv = ["host", action, "--uart-port", answers["uart"]]
            if action == "library":
                argv = ["host", action, answers["verb"], *([answers["image"]] if answers["image"] else []),
                        "--uart-port", answers["uart"]]
            if action == "load":
                argv += ["--" + answers["source"], answers["image"]]
            if action in ("step", "run-dots"):
                argv += ["--dots", answers["dots"]]
            if action == "input":
                argv += ["--mask", answers["mask"]]
            if action == "peek":
                argv += ["--store", answers["store"]]
            if action == "write":
                argv += ["--address", answers["address"], "--value", answers["value"]]
            if action == "sdram-write":
                argv += ["--address", answers["address"], "--data", answers["data"]]
            if action == "sdram-read":
                argv += ["--address", answers["address"], "--lines", answers["lines"]]
            if action == "sdram-test":
                argv += ["--start", answers["start"], "--length", answers["length"]]
            if action in ("crc-proof", "keyboard"):
                argv += ["--expected-build-id", answers["build"]]
            host = "Windows classic conhost.exe cmd.exe" if action == "keyboard" else "Windows PowerShell"
            return Plan(argv, ("host", action), host,
                        "Open UART and TRANSMIT interactive key events" if action == "keyboard"
                        else "Open UART and TRANSMIT the selected host operation")
        plan = _editable(menu, _host_steps(menu, root, action), factory)
        if plan is not BACK:
            return plan


def _clean_plan(menu, root):
    return _editable(menu, [("tag", lambda _: menu.choose(
        "Select one build tag to delete", _named(build_tags(root))))], lambda answers: Plan(
            ["clean", "--tag", answers["tag"]], ("clean",), "Current host",
            f"DELETE workdir/builds/{answers['tag']}"))


def _launcher_plan(menu, root):
    return _editable(menu, [("build", lambda _: _launcher_build_id(menu, root)),
                            ("uart", lambda _: _uart(menu, root))], lambda answers: Plan(
        ["--expected-build-id", answers["build"], "--uart-port", answers["uart"]],
        ("launcher",), "Windows PowerShell",
        "Open UART, TRANSMIT load/reset/run/control operations, and LAUNCH the game catalogue GUI"))


def _sim_host(backend):
    return "WSL Linux" if backend == "verilator" else "Windows PowerShell"


def _simulator_default(plan, root):
    backend = _argument_value(plan, "--sim")
    if backend is not None:
        option = backend + "_bin"
        directory = retained_simulator_directory(root, backend)
        if directory is not None and option not in plan.set_options:
            plan.set_options[option] = directory
    return plan


def make_plan(menu, root, intent):
    if intent == "launcher":
        return _launcher_plan(menu, root)
    if intent == "doctor":
        return _doctor_plan(menu, root)
    if intent == "check":
        return Plan(["check"], ("check",), "Current host", "Run the builder host tests")
    if intent == "sim":
        return _sim_plan(menu, root)
    if intent == "regress":
        return _regress_plan(menu, root)
    if intent == "tests":
        return _tests_plan(menu, root)
    if intent == "clean":
        return _clean_plan(menu, root)
    if intent == "fpga":
        return _fpga_plan(menu, root)
    if intent == "lint":
        return Plan(["lint", "questa"], ("lint", "questa"), "Windows PowerShell",
                    "Compile src/rtl and elaborate every FPGA top under Questa; no vsim, no license")
    if intent == "sw":
        return _sw_plan(menu, root)
    if intent == "host":
        return _host_plan(menu, root)
    raise ValueError(f"unsupported builder family: {intent}")


def _leaf_parser(plan):
    if plan.parser_path == ("launcher",):
        from gb_launcher import parser
        return parser()
    return parser_at(plan.parser_path)


def _argument_value(plan, flag):
    try:
        return plan.argv[plan.argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _option_applies(plan, action, root=None):
    root = Path(root or Path(__file__).resolve().parents[2])
    backend = "questa" if plan.parser_path == ("lint", "questa") else _argument_value(plan, "--sim")
    if action.dest == "verilator_bin" and backend != "verilator":
        return False
    if action.dest in ("questa_bin", "intel_sim_lib") and backend != "questa":
        return False
    if action.dest == "intel_sim_lib" and not selection_uses_vendor_model(
            root, plan.parser_path, plan.argv, plan.set_options):
        return False
    if plan.parser_path == ("fpga", "build") and action.dest == "build_id":
        return identity_target(target_definition(root, plan.argv[2]))
    if plan.parser_path == ("doctor",):
        profile = _argument_value(plan, "--profile")
        hardware = {"quartus_bin", "jtag_cable", "uart_port", "uart_vid", "uart_pid", "uart_identity"}
        if profile != "environment" and action.dest in hardware:
            return False
    if plan.parser_path in (("host", "crc-proof"), ("host", "keyboard")) \
            and action.dest == "endpoint_restarted":
        return False
    return True


def _option_actions(plan, root=None):
    leaf = _leaf_parser(plan)
    used = {value for value in plan.argv if isinstance(value, str) and value.startswith("-")}
    choices = []
    for action in leaf._actions:
        flags = action.option_strings
        if not flags or action.dest in ("help", "json") or action.required or any(flag in used for flag in flags):
            continue
        if not _option_applies(plan, action, root):
            continue
        if any(action in group._group_actions
               and any(peer is not action and any(flag in used for flag in peer.option_strings)
                       for peer in group._group_actions)
               for group in leaf._mutually_exclusive_groups):
            continue
        choices.append(action)
    return choices


def _option_label(action, current):
    flag = action.option_strings[-1]
    value = current.get(action.dest, action.default)
    if isinstance(action, argparse._StoreTrueAction):
        return f"{flag}: {'on' if value else 'off'}"
    if value in (None, [], ""):
        return f"{flag}: default"
    return f"{flag}: {value}"


def advanced(menu, plan, root):
    """Edit only optional leaf flags.  JSON stays on the ordinary CLI."""
    while True:
        actions = _option_actions(plan, root)
        choices = [Choice("done", "Done")]
        choices += [Choice(action, _option_label(action, plan.set_options)) for action in actions]
        selected = menu.choose("Advanced options", choices,
                               hint="Defaults are safe. Select a flag to change it; Enter on Done continues.")
        if selected is BACK:
            return BACK
        if selected == "done":
            return plan
        action = selected
        if isinstance(action, argparse._StoreTrueAction):
            current = bool(plan.set_options.get(action.dest, action.default))
            value = menu.choose(f"Set {action.option_strings[-1]}", [Choice(False, "Off"), Choice(True, "On")])
        elif isinstance(action, argparse._AppendAction):
            current = plan.set_options.get(action.dest, [])
            value = menu.text(f"Set {action.option_strings[-1]} values (comma-separated)",
                              default=",".join(str(item) for item in current), required=False)
            if value is not BACK:
                value = [item.strip() for item in value.split(",") if item.strip()]
        elif action.dest in ("verilator_bin", "questa_bin", "intel_sim_lib", "quartus_bin"):
            value = _manual_value(
                menu, f"Set {action.option_strings[-1]}", retained_values(root, action.dest),
                allow_default=(action.dest in ("verilator_bin", "questa_bin")
                               and plan.set_options.get(action.dest) is not None))
        elif action.choices:
            values = [Choice(None, "Use default")]
            values += [Choice(value, str(value)) for value in action.choices]
            value = menu.choose(f"Set {action.option_strings[-1]}", values)
        else:
            value = menu.text(f"Set {action.option_strings[-1]} (empty uses default)", required=False)
        if value is not BACK:
            plan.set_options[action.dest] = value


def final_argv(plan, root=None):
    argv = list(plan.argv)
    for action in _option_actions(plan, root):
        if action.dest not in plan.set_options:
            continue
        value = plan.set_options[action.dest]
        flag = action.option_strings[-1]
        if isinstance(action, argparse._StoreTrueAction):
            if value:
                argv.append(flag)
        elif value not in (None, "", []):
            if isinstance(value, list):
                for item in value:
                    argv += [flag, str(item)]
            else:
                argv += [flag, str(value)]
    return argv


def _cmd_argument(value):
    """Quote one CRT argv token for an interactive cmd.exe paste."""
    value = str(value)
    unsafe = next((char for char in value if char in '\0\r\n%!"'), None)
    if unsafe is not None:
        name = {"\0": "NUL", "\r": "CR", "\n": "LF", "%": "%", "!": "!", '"': '"'}[unsafe]
        raise ValueError(f"classic cmd.exe review cannot safely display an argument containing {name}")
    encoded = ['"']
    backslashes = 0
    for char in value:
        if char == "\\":
            backslashes += 1
            continue
        encoded.append("\\" * backslashes)
        backslashes = 0
        encoded.append(char)
    encoded.append("\\" * (backslashes * 2))
    encoded.append('"')
    return "".join(encoded)


def _cmd_command(argv):
    return " ".join(_cmd_argument(value) for value in argv)


def command_text(plan, root, system=None, executable=None):
    system = system or platform.system()
    program = "tools/gb_launcher.py" if plan.parser_path == ("launcher",) else "tools/build.py"
    if executable is not None:
        interpreter = executable
    elif compatible_host(plan, system, classic_console=lambda: True):
        interpreter = sys.executable
    else:
        interpreter = "python" if plan.host.startswith("Windows") else "python3"
    shown = [interpreter, program, *final_argv(plan, root)]
    if plan.host == "Windows classic conhost.exe cmd.exe":
        return _cmd_command(shown)
    if plan.host == "Windows PowerShell" or (plan.host == "Current host" and system == "Windows"):
        return "& " + powershell_command(shown)
    return shlex.join(shown)


def validate_plan(plan, root=None):
    """Prove the selected builder vector satisfies its existing argparse leaf."""
    argv = final_argv(plan, root)
    errors = io.StringIO()
    if plan.parser_path == ("launcher",):
        from gb_launcher import parse_args
        parser_call = lambda: parse_args(argv, root=Path(root or Path(__file__).resolve().parents[2]))
    else:
        from .cli import parser
        parser_call = lambda: parser().parse_args(argv)
    try:
        with contextlib.redirect_stderr(errors):
            parser_call()
    except SystemExit as error:
        detail = errors.getvalue().strip().splitlines()
        raise ValueError(detail[-1] if detail else f"invalid command (argparse exit {error.code})") from None


def compatible_host(plan, system=None, classic_console=None):
    system = system or platform.system()
    if plan.host == "Windows PowerShell":
        return system == "Windows"
    if plan.host == "Windows classic conhost.exe cmd.exe":
        if system != "Windows":
            return False
        if classic_console is None:
            from .host.console import classic_cmd_console_available
            classic_console = classic_cmd_console_available
        return bool(classic_console())
    if plan.host == "WSL Linux":
        return system != "Windows"
    return True


def choose_execution(menu, plan, root, system=None, classic_console=None):
    validate_plan(plan, root)
    command = command_text(plan, root, system)
    while True:
        lines = ["Review", "", f"Native host: {plan.host}", f"Effect: {plan.effect}", "", command, ""]
        if compatible_host(plan, system, classic_console):
            choices = [Choice("run", "Run now"), Choice("back", "Back to options"), Choice("cancel", "Cancel")]
            hint = "Nothing runs until Run now is selected."
        else:
            lines += [f"This command must run on {plan.host}. Copy it there; this menu will not bridge hosts.", ""]
            choices = [Choice("back", "Back to options"), Choice("cancel", "Exit without running")]
            hint = "Execution is unavailable on this host."
        selected = menu.choose("\n".join(lines), choices, hint=hint)
        if selected is BACK:
            return "back"
        return selected


def select_command(menu, root, system=None, classic_console=None):
    families = top_families()
    missing = set(families) - set(INTENTS)
    if missing:
        raise ValueError("TUI has no intent for builder family: " + ", ".join(sorted(missing)))
    choices = [Choice("launcher", "Play or load a game", "Open the existing one-window catalogue and controller")]
    choices += [Choice(name, *INTENTS[name]) for name in families]
    while True:
        intent = menu.choose("nand2mario build menu", choices,
                             hint="Choose one intent. Use arrows and Enter; type to filter; Escape cancels.")
        if intent is BACK:
            return CANCEL
        plan = make_plan(menu, root, intent)
        if plan is BACK:
            continue
        while True:
            configured = advanced(menu, plan, root)
            if configured is BACK:
                if plan.editor is None:
                    if plan.back_to_action:
                        plan = make_plan(menu, root, intent)
                        if plan is not BACK:
                            continue
                    break
                edited = plan.editor(menu)
                if edited is BACK:
                    plan = make_plan(menu, root, intent)
                    if plan is BACK:
                        break
                else:
                    plan = edited
                continue
            decision = choose_execution(menu, plan, root, system, classic_console)
            if decision == "back":
                continue
            if decision == "cancel":
                return CANCEL
            return plan


def run(root=None, terminal=None, runner=subprocess.run, system=None, classic_console=None):
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    terminal = terminal or Terminal(system=system)
    if not terminal.interactive():
        help_argv = [sys.executable, "tools/build.py", "--help"]
        help_command = ("& " + powershell_command(help_argv)
                        if (system or platform.system()) == "Windows"
                        else shlex.join(help_argv))
        print(f"The build menu needs an interactive terminal. Run `{help_command}` for the ordinary CLI.",
              file=sys.stderr, flush=True)
        return 2
    try:
        with terminal:
            selected = select_command(Menu(terminal), root, system, classic_console)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Build menu: {error}", file=sys.stderr, flush=True)
        return 1
    if selected is CANCEL:
        print("Cancelled; nothing was run.", flush=True)
        return 0
    leaf = root / "tools" / ("gb_launcher.py" if selected.parser_path == ("launcher",) else "build.py")
    command = [sys.executable, str(leaf), *final_argv(selected, root)]
    return runner(command, cwd=root, shell=False).returncode
