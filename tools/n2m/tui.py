"""Progressive keyboard menu for the existing public build commands.

The menu only selects and reviews an argument vector.  Execution always starts
the public ``tools/build.py`` entry point again, without a shell, so command
ownership, budgets, locks and retained records stay with their existing owners.
"""
from dataclasses import dataclass, field
import argparse
import json
from pathlib import Path
import platform
import shlex
import subprocess
import sys

from . import catalogue, interface_codec
from .progress import powershell_command
from .tui_choices import (build_tags, checked_packages, checked_sofs, command_actions,
                          external_images, fpga_targets, parser_at,
                          regression_subsets, retained_values, simulation_targets,
                          software_targets, top_families, compatible_selection)
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




INTENTS = {
    "doctor": ("Inspect environment", "Readiness checks; simulation profile may run a smoke simulation"),
    "check": ("Check builder", "Run the builder's host test suite"),
    "sim": ("Run a simulation", "Compile, run and check simulation evidence"),
    "regress": ("Run a regression", "Run a declared simulation subset"),
    "tests": ("Run or inspect verification", "Validate, list, explain or run the test catalogue"),
    "clean": ("Clean one build", "Delete exactly one selected build tag"),
    "fpga": ("Build or program the FPGA", "Build a checked image or program the attached FPGA"),
    "sw": ("Build software", "Assemble, link, package or check original software"),
    "host": ("Use UART controls", "Open the selected UART and transmit a host operation"),
}


def _named(values):
    return [Choice(value, str(value)) for value in values]


def _manual_value(menu, title, retained=()):
    options = [Choice(value, value, "reused from a retained local result") for value in retained]
    options.append(Choice("__manual__", "Type another value…"))
    selected = menu.choose(title, options)
    if selected is BACK:
        return BACK
    return menu.text(title) if selected == "__manual__" else selected


def _backend(menu, title="Select simulator"):
    choices = [Choice("verilator", "Verilator", "Runs natively on WSL Linux; no license"),
               Choice("questa", "Questa", "Runs natively on Windows PowerShell; license required")]
    return menu.choose(title, choices, hint="Use arrows and Enter. Escape goes back.")


def _uart(menu, root):
    return _manual_value(menu, "Select UART port", retained_values(root, "uart_port"))


def _wire_id(menu, root):
    values = []
    for _, target, build_id in checked_sofs(root):
        if target == "v05-board" and build_id and build_id not in values:
            values.append(build_id)
    return _manual_value(menu, "Select reviewed on-wire build ID", values)


def _quartus(menu, root):
    return _manual_value(menu, "Select Quartus bin directory", retained_values(root, "quartus_bin"))


def _collect(menu, steps):
    """Run dynamic decision pages with exact Escape-to-previous behavior."""
    answers, index = {}, 0
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


def _sim_plan(menu, root):
    actions = command_actions(("sim",))
    action = menu.choose("Simulation action", _named(actions))
    if action is BACK:
        return BACK
    if action == "test":
        answers = _collect(menu, [
            ("sim", lambda _: _backend(menu)),
            ("target", lambda a: menu.choose("Select simulation test", _named(simulation_targets(root, a["sim"]))))])
        if answers is BACK:
            return _sim_plan(menu, root)
        argv = ["sim", "test", answers["target"], "--sim", answers["sim"]]
        return Plan(argv, ("sim", "test"), _sim_host(answers["sim"]), "Build, run and check a simulation")
    targets = simulation_targets(root, None, preflight=True)
    target = menu.choose("Select fixture preflight", _named(targets))
    if target is BACK:
        return _sim_plan(menu, root)
    return Plan(["sim", "preflight", target], ("sim", "preflight"), "Current host", "Build and check a fixture; no simulator")


def _doctor_plan(menu, root):
    answers = _collect(menu, [
        ("sim", lambda _: _backend(menu)),
        ("profile", lambda _: menu.choose("Select readiness scope", [
            Choice("simulation", "Simulation", "Run the selected simulator smoke only"),
            Choice("environment", "Full environment", "Also inspect Quartus, JTAG and UART without programming or transmission")]))])
    if answers is BACK:
        return BACK
    return Plan(["doctor", "--profile", answers["profile"], "--sim", answers["sim"]],
                ("doctor",), _sim_host(answers["sim"]),
                "Run simulator smoke" + (" and read-only device discovery" if answers["profile"] == "environment" else ""))


def _regress_plan(menu, root):
    answers = _collect(menu, [
        ("sim", lambda _: _backend(menu)),
        ("subset", lambda a: menu.choose("Select compatible regression", regression_subsets(root, a["sim"])))])
    if answers is BACK:
        return BACK
    return Plan(["regress", answers["subset"], "--sim", answers["sim"]], ("regress",),
                _sim_host(answers["sim"]), "Run a bounded simulation regression")


def _catalogue_selector(menu, root, backend=None, labels=()):
    model, _ = catalogue.load(root)
    levels = []
    for level in catalogue.LEVELS:
        selected, _ = catalogue.select(model, level, labels)
        if backend is None or compatible_selection(root, model, backend, level=level, labels=labels):
            levels.append(Choice(level, f"Level {level}", f"{len(selected)} catalogue units"))
    return menu.choose("Select verification level", levels)


def _catalogue_label(menu, root, backend=None):
    model, _ = catalogue.load(root)
    choices = []
    for label, detail in sorted(model["labels"].items()):
        if backend is None or compatible_selection(root, model, backend, labels=(label,)):
            selected, _ = catalogue.select(model, None, (label,))
            choices.append(Choice(label, label, f"{len(selected)} units — {detail}"))
    return menu.choose("Select verification label", choices)


def _test_selection(menu, root, backend=None):
    mode = menu.choose("Select tests by", [Choice("level", "Confidence level"),
                                            Choice("label", "Subsystem label"),
                                            Choice("both", "Level and label")])
    if mode is BACK:
        return BACK
    if mode == "level":
        level = _catalogue_selector(menu, root, backend)
        return BACK if level is BACK else ["--level", str(level)]
    label = _catalogue_label(menu, root, backend)
    if label is BACK:
        return _test_selection(menu, root, backend)
    if mode == "label":
        return ["--label", label]
    level = _catalogue_selector(menu, root, backend, (label,))
    if level is BACK:
        return _test_selection(menu, root, backend)
    return ["--level", str(level), "--label", label]


def _tests_plan(menu, root):
    actions = command_actions(("tests",))
    action = menu.choose("Verification action", _named(actions))
    if action is BACK:
        return BACK
    if action == "validate":
        return Plan(["tests", action], ("tests", action), "Current host", "Validate the test catalogue")
    if action == "affected":
        base = menu.text("Git base reference", default="origin/main")
        if base is BACK:
            return _tests_plan(menu, root)
        return Plan(["tests", action, "--base", base], ("tests", action), "Current host", "Inspect repository impact; no tests")
    if action == "list":
        selector = _test_selection(menu, root)
        if selector is BACK:
            return _tests_plan(menu, root)
        return Plan(["tests", action, *selector], ("tests", action), "Current host", "List matching tests; no tests run")
    answers = _collect(menu, [
        ("sim", lambda _: _backend(menu)),
        ("selector", lambda a: _test_selection(menu, root, a["sim"]))])
    if answers is BACK:
        return _tests_plan(menu, root)
    return Plan(["tests", action, *answers["selector"], "--sim", answers["sim"]],
                ("tests", action), _sim_host(answers["sim"]), "Run the selected unit and simulation tests")


def _fpga_plan(menu, root):
    action = menu.choose("FPGA action", _named(command_actions(("fpga",))))
    if action is BACK:
        return BACK
    if action == "build":
        answers = _collect(menu, [
            ("target", lambda _: menu.choose("Select FPGA target", _named(fpga_targets(root)))),
            ("quartus", lambda _: _quartus(menu, root))])
        if answers is BACK:
            return _fpga_plan(menu, root)
        return Plan(["fpga", "build", answers["target"], "--quartus-bin", answers["quartus"]],
                    ("fpga", "build"), "Windows PowerShell", "Compile and check an FPGA image; no programming")
    sofs = [Choice(path, f"{target or 'unknown target'} — {path}",
                   f"on-wire ID {build_id}" if build_id else "checked attempt")
            for path, target, build_id in checked_sofs(root)]
    answers = _collect(menu, [
        ("sof", lambda _: menu.choose("Select checked FPGA image", sofs)),
        ("quartus", lambda _: _quartus(menu, root))])
    if answers is BACK:
        return _fpga_plan(menu, root)
    return Plan(["fpga", "program", "--sof", answers["sof"], "--quartus-bin", answers["quartus"]],
                ("fpga", "program"), "Windows PowerShell", "PROGRAM the attached FPGA over JTAG")


def _sw_plan(menu, root):
    action = menu.choose("Software action", _named(command_actions(("sw",))))
    if action is BACK:
        return BACK
    argv = ["sw", action]
    if action in ("assemble", "build"):
        target = menu.choose("Select software target", _named(software_targets(root, action)))
        if target is BACK:
            return _sw_plan(menu, root)
        argv.append(target)
    effects = {"oracle": "Run the pinned RGBDS comparison", "assemble": "Assemble original software",
               "build": "Build and package original software", "conformance": "Run assembler conformance",
               "link-conformance": "Run linker/package conformance", "asset-conformance": "Run asset conformance"}
    return Plan(argv, ("sw", action), "Current host", effects[action])


def _host_required(menu, root, action):
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
    if action in ("crc-proof", "keyboard"):
        steps.append(("build", lambda _: _wire_id(menu, root)))
    return _collect(menu, steps)


def _host_plan(menu, root):
    action = menu.choose("UART action", _named(command_actions(("host",))))
    if action is BACK:
        return BACK
    answers = _host_required(menu, root, action)
    if answers is BACK:
        return _host_plan(menu, root)
    argv = ["host", action, "--uart-port", answers["uart"]]
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
    if action in ("crc-proof", "keyboard"):
        argv += ["--expected-build-id", answers["build"]]
    return Plan(argv, ("host", action), "Windows PowerShell", "Open UART and TRANSMIT the selected host operation")


def _clean_plan(menu, root):
    tag = menu.choose("Select one build tag to delete", _named(build_tags(root)))
    if tag is BACK:
        return BACK
    return Plan(["clean", "--tag", tag], ("clean",), "Current host", f"DELETE workdir/builds/{tag}")


def _launcher_plan(menu, root):
    answers = _collect(menu, [("build", lambda _: _wire_id(menu, root)),
                              ("uart", lambda _: _uart(menu, root))])
    if answers is BACK:
        return BACK
    return Plan(["--expected-build-id", answers["build"], "--uart-port", answers["uart"]],
                ("launcher",), "Windows PowerShell", "Open UART and LAUNCH the game catalogue GUI")


def _sim_host(backend):
    return "WSL Linux" if backend == "verilator" else "Windows PowerShell"


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
    if intent == "sw":
        return _sw_plan(menu, root)
    if intent == "host":
        return _host_plan(menu, root)
    raise ValueError(f"unsupported builder family: {intent}")


def _option_actions(plan):
    if plan.parser_path == ("launcher",):
        return []
    used = set(plan.argv)
    choices = []
    for action in parser_at(plan.parser_path)._actions:
        flags = action.option_strings
        if not flags or action.dest in ("help", "json") or action.required or any(flag in used for flag in flags):
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


def advanced(menu, plan):
    """Edit only optional leaf flags.  JSON stays on the ordinary CLI."""
    if plan.parser_path == ("launcher",):
        definitions = [
            ("tag", "--tag", None, None), ("seconds", "--seconds", 900, int),
            ("uart_vid", "--uart-vid", None, None), ("uart_pid", "--uart-pid", None, None),
            ("uart_identity", "--uart-identity", None, None)]
        while True:
            choices = [Choice("done", "Done")]
            for dest, flag, default, _ in definitions:
                choices.append(Choice((dest, flag, default), f"{flag}: {plan.set_options.get(dest, default) or 'default'}"))
            selected = menu.choose("Advanced launcher options", choices)
            if selected is BACK:
                return BACK
            if selected == "done":
                return plan
            dest, flag, default = selected
            value = menu.text(f"Set {flag} (empty uses default)", required=False)
            if value is not BACK:
                plan.set_options[dest] = value
    actions = _option_actions(plan)
    while True:
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
        elif action.choices:
            values = [Choice(None, "Use default")]
            values += [Choice(value, str(value)) for value in action.choices]
            value = menu.choose(f"Set {action.option_strings[-1]}", values)
        else:
            value = menu.text(f"Set {action.option_strings[-1]} (empty uses default)", required=False)
        if value is not BACK:
            plan.set_options[action.dest] = value


def final_argv(plan):
    argv = list(plan.argv)
    if plan.parser_path == ("launcher",):
        definitions = [("tag", "--tag"), ("seconds", "--seconds"), ("uart_vid", "--uart-vid"),
                       ("uart_pid", "--uart-pid"), ("uart_identity", "--uart-identity")]
        for dest, flag in definitions:
            value = plan.set_options.get(dest)
            if value not in (None, ""):
                argv += [flag, str(value)]
        return argv
    for action in _option_actions(plan):
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


def command_text(plan, root, system=None):
    system = system or platform.system()
    program = "tools/gb_launcher.py" if plan.parser_path == ("launcher",) else "tools/build.py"
    shown = ["python", program, *final_argv(plan)]
    return powershell_command(shown) if plan.host == "Windows PowerShell" or system == "Windows" else shlex.join(shown)


def compatible_host(plan, system=None):
    system = system or platform.system()
    if plan.host == "Windows PowerShell":
        return system == "Windows"
    if plan.host == "WSL Linux":
        return system != "Windows"
    return True


def choose_execution(menu, plan, root, system=None):
    command = command_text(plan, root, system)
    while True:
        lines = ["Review", "", f"Native host: {plan.host}", f"Effect: {plan.effect}", "", command, ""]
        if compatible_host(plan, system):
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


def select_command(menu, root, system=None):
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
            configured = advanced(menu, plan)
            if configured is BACK:
                break
            decision = choose_execution(menu, plan, root, system)
            if decision == "back":
                continue
            if decision == "cancel":
                return CANCEL
            return plan


def run(root=None, terminal=None, runner=subprocess.run, system=None):
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    terminal = terminal or Terminal(system=system)
    if not terminal.interactive():
        print("The build menu needs an interactive terminal. Run `python tools/build.py --help` for the ordinary CLI.",
              file=sys.stderr, flush=True)
        return 2
    try:
        with terminal:
            selected = select_command(Menu(terminal), root, system)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Build menu: {error}", file=sys.stderr, flush=True)
        return 1
    if selected is CANCEL:
        print("Cancelled; nothing was run.", flush=True)
        return 0
    leaf = root / "tools" / ("gb_launcher.py" if selected.parser_path == ("launcher",) else "build.py")
    command = [sys.executable, str(leaf), *final_argv(selected)]
    return runner(command, cwd=root, shell=False).returncode
