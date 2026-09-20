"""Live registry and retained-record choices for the progressive build menu."""
import argparse
import json
import os
import platform
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile

from . import catalogue
from .fpga import REGISTRIES as FPGA_REGISTRIES
from .fpga_program import checked_attempt
from .host.package import read_package
from .records import read_json, valid_tag
from .regress import load_subsets
from .simulation import simulator_problem
from .tui_terminal import Choice


def read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def simulation_targets(root, backend, *, preflight=False):
    rows = read_object(root / "src/dv/builder/targets.json")
    names = []
    for name in sorted(rows):
        target = rows[name]
        problem = simulator_problem(name, target)
        if problem:
            raise ValueError(problem)
        if preflight:
            if target.get("testbench") == "python":
                names.append(name)
        elif backend in target["simulators"]:
            names.append(name)
    return names


def fpga_targets(root):
    """Every registered target across the board registries, in name order."""
    names = []
    for registry in FPGA_REGISTRIES:
        rows = read_object(root / registry).get("targets")
        if not isinstance(rows, dict):
            raise ValueError("FPGA target registry has no targets object")
        names.extend(rows)
    return sorted(names)


def software_targets(root, action):
    rows = read_object(root / "src/sw/targets.json").get("targets")
    if not isinstance(rows, dict):
        raise ValueError("software target registry has no targets object")
    if action == "build":
        return sorted(name for name, row in rows.items() if isinstance(row, dict) and "layout" in row)
    return sorted(rows)


def regression_subsets(root, backend):
    subsets, _ = load_subsets(root)
    targets = read_object(root / "src/dv/builder/targets.json")
    compatible = []
    for name, subset in sorted(subsets.items()):
        if all(backend in targets[target]["simulators"] for target in subset["targets"]):
            compatible.append(Choice(name, name, subset["purpose"]))
    return compatible


def build_tags(root):
    builds = root / "workdir/builds"
    if not builds.is_dir():
        return []
    return sorted((path.name for path in builds.iterdir()
                   if path.is_dir() and not path.is_symlink() and valid_tag(path.name)), reverse=True)


def measured_tags(root):
    """Every retained build tag holding a run whose walls `tests record` can write."""
    found = []
    for tag in build_tags(root):
        for relative in ("tests/summary.json", "manifest.json"):
            record = root / "workdir/builds" / tag / relative
            if not record.is_file():
                continue
            try:
                walls = catalogue.measured_walls(read_object(record))
            except (OSError, ValueError):
                walls = {}
            if walls:
                found.append(tag)
            break
    return found


def checked_sofs(root):
    found = []
    builds = root / "workdir/builds"
    if not builds.is_dir():
        return found
    candidates = sorted(builds.glob("*/fpga/*/attempts/*/output/design.sof"),
                        key=lambda path: path.lstat().st_mtime, reverse=True)
    for sof in candidates[:50]:
        try:
            record, on_wire, target = checked_attempt(root, sof)
            if record.get("status") != "PASS":
                continue
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        found.append((sof.relative_to(root).as_posix(), target, on_wire))
    return sorted(found, reverse=True)


def checked_packages(root):
    found = []
    builds = root / "workdir/builds"
    if not builds.is_dir():
        return found
    candidates = sorted(builds.glob("*/sw/build/*/runs/*/result.json"),
                        key=lambda path: path.stat().st_mtime, reverse=True)
    for manifest in candidates[:50]:
        try:
            read_package(root, manifest)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        found.append(manifest.relative_to(root).as_posix())
    return sorted(found, reverse=True)


def external_images(root):
    rows = read_object(root / "tools/n2m/dependencies.json").get("external_roms", {}).get("images", {})
    if not isinstance(rows, dict):
        raise ValueError("external ROM manifest has no images object")
    return list(rows)


def _walk_values(value, key):
    if isinstance(value, dict):
        if isinstance(value.get(key), str) and value[key]:
            yield value[key]
        for child in value.values():
            yield from _walk_values(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child, key)


def retained_values(root, key):
    """Return recent local selections without probing a tool or device."""
    builds = root / "workdir/builds"
    values = []
    if builds.is_dir():
        manifests = sorted(builds.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in manifests[:50]:
            record = read_json(path)
            if record:
                for value in _walk_values(record, key):
                    if value not in values:
                        values.append(value)
    return values


def retained_simulator_directory(root, backend, *, system=None, which=None):
    """Return one usable retained tool directory when PATH lacks the backend.

    This is a browse-time filesystem and PATH check only. Simulator version
    queries and all other child processes remain owned by the confirmed build.
    """
    tools = {"verilator": ("verilator",),
             "questa": ("vlib", "vmap", "vlog", "vsim")}
    if backend not in tools:
        raise ValueError(f"unsupported simulator: {backend}")
    which = which or shutil.which
    suffix = ".exe" if (system or platform.system()) == "Windows" else ""
    names = tuple(name + suffix for name in tools[backend])
    if all(which(name) for name in names):
        return None

    root = Path(root)
    applicable = []
    seen = set()
    for value in retained_values(root, backend + "_bin"):
        directory = Path(value)
        checked = directory if directory.is_absolute() else root / directory
        if not checked.is_dir() or not all(which(str(checked / name)) for name in names):
            continue
        identity = os.path.normcase(str(checked.resolve()))
        if identity not in seen:
            seen.add(identity)
            applicable.append(value)
    return applicable[0] if len(applicable) == 1 else None


def current_uart_candidates(root, *, system=None, discover=None):
    """Enumerate healthy Windows PnP ports without opening a serial device."""
    if (system or platform.system()) != "Windows":
        return []
    if discover is None:
        from .doctor import uart as discover
    scratch = root / "workdir/.tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    args = SimpleNamespace(uart_port=None, uart_vid=None, uart_pid=None, uart_identity=None)
    try:
        with tempfile.TemporaryDirectory(prefix="tui-uart-", dir=scratch) as temporary:
            result = discover(Path(temporary), args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return []
    return [row["DeviceID"] for row in result.get("ports", [])
            if isinstance(row, dict) and re_port(row.get("DeviceID"))
            and row.get("Status") == "OK" and row.get("ConfigManagerErrorCode") == 0]


def uart_candidates(root, *, system=None, discover=None):
    """Return current healthy PnP ports, then retained explicit selections.

    Discovery is the doctor's read-only Windows CIM query. It never imports the
    serial backend, opens a port or sends a byte. The existing host command still
    repeats PnP identity and health checks before opening the chosen port.
    """
    values = current_uart_candidates(root, system=system, discover=discover)
    builds = root / "workdir/builds"
    if builds.is_dir():
        manifests = sorted(builds.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in manifests[:50]:
            record = read_json(path)
            if not record:
                continue
            pending = [record]
            while pending:
                item = pending.pop()
                if isinstance(item, dict):
                    device = item.get("DeviceID")
                    if (isinstance(device, str) and re_port(device)
                            and item.get("Status") == "OK"
                            and item.get("ConfigManagerErrorCode") == 0
                            and device not in values):
                        values.append(device)
                    pending.extend(item.values())
                elif isinstance(item, list):
                    pending.extend(item)
    for value in retained_values(root, "uart_port"):
        if re_port(value) and value not in values:
            values.append(value)
    return values


def re_port(value):
    return isinstance(value, str) and value.upper().startswith("COM") and value[3:].isdigit() and int(value[3:]) > 0


def _subparsers(command_parser):
    for action in command_parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def parser_at(path):
    from .cli import parser
    current = parser()
    for name in path:
        current = _subparsers(current)[name]
    return current


def command_actions(path):
    return list(_subparsers(parser_at(path)))


def top_families():
    return list(_subparsers(parser_at(())))


def compatible_selection(root, model, backend, *, level=None, labels=()):
    selected, _ = catalogue.select(model, level, labels)
    targets = read_object(root / "src/dv/builder/targets.json")
    simulations = [name for name in selected if model["units"][name]["kind"] == "sim"]
    return all(backend in targets[name]["simulators"] for name in simulations)


def selection_uses_vendor_model(root, parser_path, argv, set_options=None):
    """Return whether the selected live simulation set needs an Intel model."""
    set_options = set_options or {}
    if parser_path == ("sim", "test"):
        selected = [argv[2]]
    elif parser_path == ("regress",):
        subsets, _ = load_subsets(root)
        selected = subsets[argv[1]]["targets"]
    elif parser_path == ("tests", "run"):
        model, _ = catalogue.load(root)
        level = _argument_value(argv, "--level")
        if level is None:
            level = set_options.get("level")
        level = int(level) if level is not None else None
        labels = _argument_values(argv, "--label")
        labels.extend(set_options.get("label", []))
        chosen, _ = catalogue.select(model, level, labels)
        selected = [name for name in chosen if model["units"][name]["kind"] == "sim"]
    else:
        return False
    targets = read_object(root / "src/dv/builder/targets.json")
    return any(targets[name].get("vendor_model") is not None for name in selected)


def _argument_value(argv, flag):
    values = _argument_values(argv, flag)
    return values[-1] if values else None


def _argument_values(argv, flag):
    return [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == flag]
