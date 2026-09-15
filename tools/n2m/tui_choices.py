"""Live registry and retained-record choices for the progressive build menu."""
import argparse
import json
from pathlib import Path

from . import catalogue
from .fpga_program import attempt_record, wire_build_id
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
    rows = read_object(root / "src/fpga/de10_lite/targets.json").get("targets")
    if not isinstance(rows, dict):
        raise ValueError("FPGA target registry has no targets object")
    return sorted(rows)


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


def checked_sofs(root):
    found = []
    builds = root / "workdir/builds"
    if not builds.is_dir():
        return found
    for sof in builds.glob("*/fpga/*/attempts/*/output/design.sof"):
        try:
            record = attempt_record(root, sof)
            if record.get("status") != "PASS":
                continue
            on_wire = wire_build_id(record)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        found.append((sof.relative_to(root).as_posix(), record.get("target"), on_wire))
    return sorted(found, reverse=True)


def checked_packages(root):
    found = []
    builds = root / "workdir/builds"
    if not builds.is_dir():
        return found
    for manifest in builds.glob("*/sw/build/*/runs/*/result.json"):
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

