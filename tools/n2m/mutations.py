"""Recorded mutations that prove affected selection is conservative; never a required check.

`src/dv/builder/mutations.json` records, for a representative set of inputs,
one byte mutation and the units recorded as detecting it. The proof is that
`affected.decide` selects every recorded detector when that one path differs
from the base; a recorded detector left unselected is a miss named as such.
`confirm` re-derives the record itself: it applies each mutation in a shared
clone and runs the detectors before and after, so the record never claims a
detection an environment failure produced.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from . import affected, catalogue
from .records import atomic_json

MANIFEST = "src/dv/builder/mutations.json"
KINDS = ("rtl", "python", "catalogue", "tool", "data")
FIELDS = {"name", "kind", "path", "mutation", "detectors", "evidence"}
# The interpreter directory the clone borrows so a python-testbench detector can run.
COCOTB_ENV = "workdir/builds/python-dv-env"


def load(root, model=None):
    """The validated mutation rows; a malformed manifest is a ValueError naming the row."""
    root = Path(root)
    document = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"version", "marker", "mutations"} or document["version"] != 1:
        raise ValueError(f"{MANIFEST} must carry version 1, a marker and mutations")
    marker = document["marker"]
    if not isinstance(marker, str) or not marker.strip():
        raise ValueError(f"{MANIFEST} marker must be a non-empty string")
    rows = document["mutations"]
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{MANIFEST} must record at least one mutation")
    names = set()
    units = model["units"] if model else None
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError(f"{MANIFEST} row must have exactly {sorted(FIELDS)}: {row}")
        name = row["name"]
        if not isinstance(name, str) or name in names:
            raise ValueError(f"{MANIFEST} mutation names must be unique strings: {name}")
        names.add(name)
        if row["kind"] not in KINDS:
            raise ValueError(f"mutation {name} kind must be one of {KINDS}")
        path = row["path"]
        if not isinstance(path, str) or not (root / path).is_file() or not tracked(root, path):
            raise ValueError(f"mutation {name} path is not a tracked file: {path}")
        mutation = row["mutation"]
        if mutation != "append" and not (isinstance(mutation, dict) and set(mutation) == {"replace"}
                                        and isinstance(mutation["replace"], list) and len(mutation["replace"]) == 2
                                        and all(isinstance(t, str) for t in mutation["replace"])
                                        and mutation["replace"][0] and mutation["replace"][0] != mutation["replace"][1]):
            raise ValueError(f"mutation {name} must be \"append\" or {{\"replace\": [old, new]}}")
        if mutation != "append" and mutation["replace"][0] not in (root / path).read_text(encoding="utf-8"):
            raise ValueError(f"mutation {name} replaces text {path} does not contain")
        if (not isinstance(row["detectors"], list) or not row["detectors"]
                or any(not isinstance(d, str) for d in row["detectors"])):
            raise ValueError(f"mutation {name} must record at least one detecting unit")
        if units is not None:
            for detector in row["detectors"]:
                if detector not in units:
                    raise ValueError(f"mutation {name} detector is not a catalogue unit: {detector}")
        if not isinstance(row["evidence"], str) or not row["evidence"].strip():
            raise ValueError(f"mutation {name} must record its detection evidence")
    return marker, rows


def tracked(root, path):
    return subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", path],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode == 0


def mutate(root, row, marker):
    """Apply one recorded mutation to a checkout; returns the bytes written."""
    target = Path(root) / row["path"]
    if row["mutation"] == "append":
        data = target.read_bytes() + f"\n{marker}\n".encode()
    else:
        old, new = row["mutation"]["replace"]
        text = target.read_text(encoding="utf-8")
        if old not in text:
            raise ValueError(f"mutation {row['name']} replaces text {row['path']} does not contain")
        data = text.replace(old, new, 1).encode("utf-8")
    target.write_bytes(data)
    return data


def selection(root, model, known, path, only=None):
    """The advisory decision when exactly `path` differs from the base."""
    changed = [dict(status="M", path=path)]
    return affected.decide(root, model, changed, lambda p: ("mutated", "base") if p == path else ("same", "same"),
                           known, only)


def misses(root, model, rows, known=None):
    """Every recorded detector the selection omits, as `mutation NAME: unit U not selected for PATH (reason)`."""
    root = Path(root).resolve()
    known = known or affected.closures(root, model)
    found = []
    for row in rows:
        _, units = selection(root, model, known, row["path"], set(row["detectors"]))
        for detector in row["detectors"]:
            decision = units.get(detector)
            if decision is None or decision["decision"] != "selected":
                why = "not a selectable unit" if decision is None else "; ".join(decision["reasons"])
                found.append(f"mutation {row['name']}: unit {detector} not selected for {row['path']} ({why})")
    return found


def clone(root, destination):
    """A shared clone of HEAD to mutate; the live tree is never edited."""
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    subprocess.run(["git", "clone", "-q", "--shared", "--no-hardlinks", str(root), str(destination)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
    env = Path(root) / COCOTB_ENV
    if env.is_dir():
        borrowed = destination / COCOTB_ENV
        borrowed.parent.mkdir(parents=True, exist_ok=True)
        borrowed.symlink_to(env.resolve(), target_is_directory=True)
    return destination


def run_detector(root, name, entry, verilator_bin=None):
    """One detector's outcome in `root`: a host unit through the catalogue runner, a target through sim test."""
    if entry["kind"] == "unit":
        return catalogue.run_unit(root, name, entry)
    python = sys.executable
    definitions = json.loads((Path(root) / "src/dv/builder/targets.json").read_text(encoding="utf-8"))
    if definitions[name].get("testbench") == "python":
        python = catalogue.cocotb_python(root)
        if python is None:
            return {"status": "SKIPPED", "reason": "cocotb-environment",
                    "error": "the pinned src/dv/python environment is not installed"}
    command = [python, str(Path(root) / "tools/build.py"), "sim", "test", name, "--tag", "mutation", "--json"]
    if verilator_bin:
        command += ["--verilator-bin", verilator_bin]
    started = time.monotonic()
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(command, cwd=str(root), env=env, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=catalogue.ORDINARY_BUDGET)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    try:
        child = json.loads(lines[-1]) if lines else {}
    except ValueError:
        child = {}
    outcome = {"command": command, "exit_code": result.returncode, "elapsed_seconds": time.monotonic() - started,
               "status": "PASS" if result.returncode == 0 and child.get("status") == "PASS" else "FAIL"}
    if outcome["status"] == "FAIL":
        outcome["error"] = child.get("error") or catalogue.unit_error(result.stdout)
    return outcome


def confirm(root, model, rows, marker, build, verilator_bin=None):
    """Re-derive each record: every detector passes unmutated and fails mutated, in a clone.

    A detector that fails before the mutation, or is skipped, leaves the row
    unconfirmed; that is an environment or record problem, never a detection."""
    root = Path(root).resolve()
    outcome = {"rows": {}, "problems": []}
    for row in rows:
        checkout = clone(root, Path(build) / "mutations" / row["name"])
        record = {"path": row["path"], "detectors": {}}
        for detector in row["detectors"]:
            entry = model["units"][detector]
            before = run_detector(checkout, detector, entry, verilator_bin)
            record["detectors"][detector] = {"before": before}
            if before["status"] != "PASS":
                outcome["problems"].append(f"mutation {row['name']}: unit {detector} did not pass before the "
                                           f"mutation ({before.get('error', before.get('reason', before['status']))})")
        mutate(checkout, row, marker)
        for detector in row["detectors"]:
            entry = model["units"][detector]
            after = run_detector(checkout, detector, entry, verilator_bin)
            record["detectors"][detector]["after"] = {k: v for k, v in after.items() if k != "output"}
            if after["status"] != "FAIL":
                outcome["problems"].append(f"mutation {row['name']}: unit {detector} still {after['status']} "
                                           f"after mutating {row['path']}")
        for detector in record["detectors"]:
            record["detectors"][detector]["before"].pop("output", None)
        outcome["rows"][row["name"]] = record
        atomic_json(Path(build) / "mutations" / (row["name"] + ".json"), record)
        shutil.rmtree(checkout, ignore_errors=True)
    return outcome


def command(root, build, args):
    """`tests mutations [--confirm] [--name N]`: the selection proof, then optionally the detection re-derivation."""
    started = time.monotonic()
    root = Path(root).resolve()
    model, _ = catalogue.load(root)
    problems = catalogue.coverage(root, model)
    if problems:
        raise ValueError(problems[0])
    marker, rows = load(root, model)
    if args.name:
        unknown = sorted(set(args.name) - {r["name"] for r in rows})
        if unknown:
            raise ValueError(f"unknown mutation: {', '.join(unknown)}")
        rows = [r for r in rows if r["name"] in args.name]
    report = {"scope": "advisory selection proof; required checks unchanged", "manifest": MANIFEST,
              "mutations": [r["name"] for r in rows], "misses": misses(root, model, rows), "confirm": None}
    if args.confirm:
        report["confirm"] = confirm(root, model, rows, marker, build, getattr(args, "verilator_bin", None))
    failures = report["misses"] + (report["confirm"]["problems"] if report["confirm"] else [])
    report.update(status="FAIL" if failures else "PASS", elapsed_seconds=time.monotonic() - started)
    if failures:
        report["error"] = failures[0]
    return report
