"""One catalogue of every runnable test unit, selected by level and label.

The catalogue is `src/dv/builder/catalogue.yaml`. It holds one entry per
runnable unit: every registry target of `src/dv/builder/targets.json` and every
standalone `test_*.py` unittest file in the tree. `validate` proves the
catalogue still covers the tree, so a test added without an entry fails.

The file is a small, strict YAML subset so the builder keeps its stdlib-only
dependency set: block mappings, flow mappings, flow sequences, plain and quoted
scalars, and whole-line comments. Inline comments are not accepted, because a
`#` inside an unquoted value would otherwise be silently truncated.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from .records import atomic_json, atomic_text, file_hash, workspace
from .simulation import load_target
from .test_budget import supervise

CATALOGUE = "src/dv/builder/catalogue.yaml"
KINDS = ("sim", "unit")
LEVELS = (0, 1, 2)
# AGENTS.md: the ordinary pre-merge aggregate. Level 0 is built to fit inside it.
ORDINARY_BUDGET = 300
# A child needs its 12 reserved cleanup seconds plus at least one to run.
MINIMUM_CHILD_SECONDS = 13
LABEL = re.compile(r"[a-z0-9][a-z0-9-]*")
TARGET = re.compile(r"[a-z0-9][a-z0-9_-]*")
UNIT_FILE = re.compile(r"[A-Za-z0-9_./-]+\.py")
# Directories that hold generated output or another checkout, never our tree.
SKIP_DIRECTORIES = frozenset({".git", "workdir", "worktrees", "__pycache__", "node_modules", ".venv"})
# Questa is one node-locked seat. A refused checkout is contention, not a defect.
CONTENTION = ("License checkout has been disallowed", "Licensing error",
              "Unable to checkout a license", "queued for a license")
CONTENTION_EXIT = 12
# The pinned cocotb interpreter of src/dv/python/README.md; units labelled
# `needs-cocotb` import cocotb and cannot run on the builder interpreter.
COCOTB_PYTHON = ("workdir/builds/python-dv-env/.venv/Scripts/python.exe",
                 "workdir/builds/python-dv-env/.venv/bin/python")

HEADER = ("# Catalogue of every runnable test unit: one entry per registry target and\n"
          "# per standalone test_*.py file. Levels are ordered, so selecting a level runs\n"
          "# every level below it. Labels are a set, validated against the vocabulary\n"
          "# below. duration_seconds is the wall of the last actual run, written back by\n"
          "# `tools/build.py tests run`; it is never edited by hand.\n"
          "#\n"
          "# Whole-line comments only; see tools/n2m/catalogue.py for the accepted subset.\n")


# ---------------------------------------------------------------- YAML subset

def _scalar(text):
    text = text.strip()
    if text in ("", "null", "~"):
        return None
    if text in ("true", "false"):
        return text == "true"
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        body = text[1:-1]
        return body.replace('\\"', '"').replace("\\\\", "\\") if text[0] == '"' else body.replace("''", "'")
    for convert in (int, float):
        try:
            return convert(text)
        except ValueError:
            pass
    if text[0] in "\"'":
        raise ValueError(f"unterminated quoted scalar: {text}")
    return text


def _split(text):
    """Split one flow collection body on its top-level commas."""
    parts, depth, quote, current = [], 0, None, ""
    for character in text:
        if quote:
            current += character
            if character == quote:
                quote = None
            continue
        if character in "\"'":
            quote = character
        elif character in "[{":
            depth += 1
        elif character in "]}":
            depth -= 1
        if character == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += character
    if quote or depth:
        raise ValueError(f"unterminated flow collection: {text}")
    if current.strip():
        parts.append(current)
    return [part.strip() for part in parts]


def _flow(text):
    text = text.strip()
    if text[:1] in "[{" and text[-1:] != {"[": "]", "{": "}"}[text[:1]]:
        raise ValueError(f"unterminated flow collection: {text}")
    if text.startswith("[") and text.endswith("]"):
        return [_flow(item) for item in _split(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        mapping = {}
        for item in _split(text[1:-1]):
            key, separator, value = item.partition(":")
            if not separator:
                raise ValueError(f"flow mapping entry needs a key: {item}")
            key = str(_scalar(key))
            if key in mapping:
                raise ValueError(f"duplicate flow key: {key}")
            mapping[key] = _flow(value)
        return mapping
    return _scalar(text)


def _block(lines, index, indent):
    mapping, sequence = {}, []
    while index < len(lines):
        number, column, text = lines[index]
        if column < indent:
            break
        if column > indent:
            raise ValueError(f"line {number}: unexpected indentation")
        if text.startswith("- "):
            sequence.append(_flow(text[2:]))
            index += 1
            continue
        key, separator, rest = text.partition(":")
        if not separator:
            raise ValueError(f"line {number}: expected 'key: value'")
        key = str(_scalar(key))
        if key in mapping:
            raise ValueError(f"line {number}: duplicate key {key}")
        rest = rest.strip()
        index += 1
        if rest:
            mapping[key] = _flow(rest)
        elif index < len(lines) and lines[index][1] > indent:
            mapping[key], index = _block(lines, index, lines[index][1])
        else:
            mapping[key] = None
        if sequence:
            raise ValueError(f"line {number}: a block mixes a sequence and a mapping")
    if sequence and mapping:
        raise ValueError("a block mixes a sequence and a mapping")
    return (sequence if sequence else mapping), index


def read_yaml(text):
    """Parse the accepted YAML subset into plain Python values."""
    lines = []
    for number, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw:
            raise ValueError(f"line {number}: tabs are not indentation")
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.append((number, len(raw) - len(raw.lstrip(" ")), stripped))
    if not lines:
        return {}
    value, index = _block(lines, 0, lines[0][1])
    if index != len(lines):
        raise ValueError(f"line {lines[index][0]}: unexpected indentation")
    return value


def _quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _duration(value):
    return "null" if value is None else f"{float(value):.2f}"


def format_document(model):
    """Render the canonical catalogue text; `load` reads exactly this back."""
    lines = [HEADER, "version: %d\n" % model["version"], "labels:\n"]
    for label in sorted(model["labels"]):
        lines.append(f"  {label}: {_quote(model['labels'][label])}\n")
    lines.append("units:\n")
    for name in sorted(model["units"]):
        lines.append(format_unit(name, model["units"][name]))
    if not model["not_runnable"]:
        lines.append("not_runnable: {}\n")
    else:
        lines.append("not_runnable:\n")
        for name in sorted(model["not_runnable"]):
            lines.append(f"  {name}: {_quote(model['not_runnable'][name])}\n")
    return "".join(lines)


def format_unit(name, entry):
    labels = ", ".join(sorted(entry["labels"]))
    return (f"  {name}: {{kind: {entry['kind']}, level: {entry['level']}, "
            f"labels: [{labels}], duration_seconds: {_duration(entry['duration_seconds'])}}}\n")


# ------------------------------------------------------------------ the model

def load(root):
    """Read and validate the catalogue. Every rule here fails the build."""
    path = Path(root) / CATALOGUE
    model = read_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(model, dict) or set(model) != {"version", "labels", "units", "not_runnable"}:
        raise ValueError("catalogue requires exactly version, labels, units and not_runnable")
    if model["version"] != 1:
        raise ValueError("catalogue requires version 1")
    vocabulary = model["labels"]
    if not isinstance(vocabulary, dict) or not vocabulary:
        raise ValueError("catalogue requires a nonempty label vocabulary")
    for label, purpose in vocabulary.items():
        if not LABEL.fullmatch(label):
            raise ValueError(f"invalid label in vocabulary: {label}")
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValueError(f"label {label} requires a purpose")
    units = model["units"]
    if not isinstance(units, dict) or not units:
        raise ValueError("catalogue requires a nonempty units mapping")
    for name, entry in units.items():
        if not isinstance(entry, dict) or set(entry) != {"kind", "level", "labels", "duration_seconds"}:
            raise ValueError(f"unit {name} requires exactly kind, level, labels and duration_seconds")
        if entry["kind"] not in KINDS:
            raise ValueError(f"unit {name} kind must be one of {', '.join(KINDS)}")
        if entry["level"] not in LEVELS:
            raise ValueError(f"unit {name} level must be 0, 1 or 2")
        pattern = TARGET if entry["kind"] == "sim" else UNIT_FILE
        if not pattern.fullmatch(name):
            raise ValueError(f"unit {name} is not a valid {entry['kind']} identifier")
        labels = entry["labels"]
        if not isinstance(labels, list) or len(set(labels)) != len(labels):
            raise ValueError(f"unit {name} labels must be a set")
        for label in labels:
            if not isinstance(label, str) or label not in vocabulary:
                raise ValueError(f"unit {name} uses undeclared label: {label}")
        duration = entry["duration_seconds"]
        if duration is not None and (not isinstance(duration, (int, float)) or duration < 0):
            raise ValueError(f"unit {name} duration_seconds must be null or a nonnegative number")
    excluded = model["not_runnable"]
    if not isinstance(excluded, dict):
        raise ValueError("catalogue not_runnable must be a mapping of path to reason")
    for name, reason in excluded.items():
        if not UNIT_FILE.fullmatch(name) or not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"not_runnable {name} requires a recorded reason")
        if name in units:
            raise ValueError(f"{name} is both a unit and not_runnable")
    return model, path


def discovered_tests(root):
    """Every test_*.py present in the tree, generated output excluded."""
    root = Path(root)
    found, pending = [], [root]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIP_DIRECTORIES:
                        pending.append(Path(entry.path))
                elif entry.name.startswith("test_") and entry.name.endswith(".py"):
                    found.append(Path(entry.path).relative_to(root).as_posix())
    return sorted(found)


def target_inputs(targets):
    """Every repository file a registry target already carries as an input."""
    owned = set()
    for target in targets.values():
        owned.update(target.get("sources", []))
        if isinstance(target.get("python"), dict):
            owned.update(target["python"].get("inputs", []))
        driver = target.get("driver")
        if isinstance(driver, dict):
            owned.update([driver.get("script"), driver.get("peer"), *driver.get("inputs", [])])
    return {path for path in owned if isinstance(path, str)}


def coverage(root, model):
    """Return the ordered list of coverage failures; empty means covered."""
    root = Path(root)
    targets = json.loads((root / "src/dv/builder/targets.json").read_text(encoding="utf-8"))
    units = model["units"]
    simulations = {name for name, entry in units.items() if entry["kind"] == "sim"}
    files = {name for name, entry in units.items() if entry["kind"] == "unit"}
    problems = []
    for name in sorted(set(targets) - simulations):
        problems.append(f"registry target {name} is missing from {CATALOGUE}")
    for name in sorted(simulations - set(targets)):
        problems.append(f"catalogue target {name} is not a registered simulation target")
    owned = target_inputs(targets)
    for path in discovered_tests(root):
        if path in files or path in model["not_runnable"] or path in owned:
            continue
        problems.append(f"test file {path} is missing from {CATALOGUE}")
    for path in sorted(files | set(model["not_runnable"])):
        if not (root / path).is_file():
            problems.append(f"catalogue entry {path} names no file in the tree")
    return problems


# -------------------------------------------------------------------- select

def select(model, level=None, labels=()):
    """Return (ordered names, selector description). Raises on a bad selector."""
    if level is None and not labels:
        raise ValueError("a selection requires --level, --label or both")
    for label in labels:
        if label not in model["labels"]:
            raise ValueError(f"unknown label: {label}; declare it in {CATALOGUE}")
    chosen = []
    for name in sorted(model["units"]):
        entry = model["units"][name]
        if level is not None and entry["level"] > level:
            continue
        if not set(labels) <= set(entry["labels"]):
            continue
        chosen.append(name)
    described = []
    if level is not None:
        described.append(f"--level {level}")
    described += [f"--label {label}" for label in labels]
    selector = " ".join(described)
    if not chosen:
        empty = [label for label in labels
                 if not any(label in entry["labels"] for entry in model["units"].values())]
        if level is not None and not any(entry["level"] <= level for entry in model["units"].values()):
            empty.append(f"level {level}")
        detail = f"; nothing carries {', '.join(empty)}" if empty else ""
        raise ValueError(f"selection matched no tests: {selector}{detail}")
    return chosen, selector


# --------------------------------------------------------------------- runner

def unit_command(root, path, entry, python=None):
    """Run exactly one unittest file with its own directory as the top level."""
    directory = str((Path(root) / path).parent)
    return [python or sys.executable, "-B", "-m", "unittest", "discover",
            "-s", directory, "-t", directory, "-p", Path(path).name, "-v"]


def unit_environment(root):
    environment = dict(os.environ)
    # tools/ carries the n2m, ci, sw and wiki packages the fixtures import.
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join([str(Path(root) / "tools")] + ([existing] if existing else []))
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def cocotb_python(root):
    for candidate in COCOTB_PYTHON:
        path = Path(root) / candidate
        if path.is_file():
            return str(path)
    return None


def unit_error(output):
    """Name the failing test rather than whatever the unit printed last.

    The child's stdout and stderr share one pipe, and its block-buffered stdout
    flushes at exit, after unittest's verdict. The last line is therefore as
    often a passing diagnostic print as it is the failure, so prefer the first
    failure header, then the verdict, and only then the last line."""
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    for line in lines:
        if line.startswith(("FAIL: ", "ERROR: ")):
            return line
    for line in reversed(lines):
        if line.startswith("FAILED"):
            return line
    return lines[-1] if lines else "no output"


def run_unit(root, path, entry):
    """Run one unittest file and return its outcome and measured wall."""
    python = None
    if "needs-cocotb" in entry["labels"]:
        python = cocotb_python(root)
        if python is None:
            return {"status": "SKIPPED", "reason": "cocotb-environment",
                    "error": "the pinned src/dv/python environment is not installed"}
    command = unit_command(root, path, entry, python)
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=str(root), env=unit_environment(root), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    except subprocess.TimeoutExpired:
        return {"status": "FAIL", "elapsed_seconds": time.monotonic() - started,
                "error": "unit exceeded its 300-second wall budget", "command": command}
    elapsed = time.monotonic() - started
    outcome = {"command": command, "exit_code": result.returncode, "elapsed_seconds": elapsed,
               "status": "PASS" if result.returncode == 0 else "FAIL"}
    if result.returncode:
        outcome["error"] = unit_error(result.stdout)
        outcome["output"] = result.stdout
    return outcome


def contended(code, text):
    """True when Questa refused the node-locked seat rather than failing a test."""
    return code == CONTENTION_EXIT or any(marker in text for marker in CONTENTION)


def referenced_log(root, error):
    """Read the simulator log a failing child pointed at, if it named one.

    A refused license checkout reaches the runner only as the child's short
    `unexpected exit 12; see <path>` line, so the refusal itself is in the log.
    """
    match = re.search(r"see (\S+\.log)", str(error or ""))
    if not match:
        return ""
    path = (Path(root) / match.group(1).replace("\\", "/")).resolve()
    if not path.is_relative_to(Path(root).resolve() / "workdir") or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def run_simulation(root, tag, target, args, remaining):
    """Run one registry target as the ordinary sim-test worker."""
    command = [sys.executable, str(Path(root) / "tools/n2m/test_budget.py"), "sim", "test", target,
               "--tag", tag, "--seed", str(args.seed), "--json"]
    if args.rebuild:
        command.append("--rebuild")
    for option in ("questa_bin", "intel_sim_lib"):
        if getattr(args, option, None):
            command += ["--" + option.replace("_", "-"), getattr(args, option)]
    started = time.monotonic()
    code, text = supervise(command, Path(root), tag, target=target, ceiling=math.floor(remaining))
    elapsed = time.monotonic() - started
    outcome = {"command": command, "exit_code": code, "elapsed_seconds": elapsed}
    lines = [line for line in text.splitlines() if line.strip()]
    try:
        child = json.loads(lines[-1]) if lines else {}
        if not isinstance(child, dict):
            raise ValueError
    except ValueError:
        child = {"status": "FAIL", "error": "child result is not a JSON object"}
    for key in ("cache", "error"):
        if key in child:
            outcome[key] = child[key]
    if code == 0 and child.get("status") == "PASS":
        outcome["status"] = "PASS"
    elif contended(code, " ".join([text, str(child.get("error", "")),
                                   referenced_log(root, child.get("error"))])):
        # The seat is held elsewhere. Report it by name; never call it a defect.
        outcome.update(status="SKIPPED", reason="questa-contention")
    else:
        outcome["status"] = "FAIL"
        outcome.setdefault("error", f"child exit {code} with status {child.get('status')}")
    for key in ("stale_lock_removed", "lock_left"):
        if key in child:
            outcome[key] = child[key]
    return outcome


def record_durations(path, durations):
    """Rewrite only the changed unit lines, so comments and order survive."""
    if not durations:
        return 0
    lines = Path(path).read_text(encoding="utf-8").splitlines(keepends=True)
    written, inside = 0, False
    for index, line in enumerate(lines):
        if not line.startswith((" ", "#")) and line.strip():
            # A label and a target may share a name, so only the units section
            # is ever rewritten; a vocabulary line is not an entry.
            inside = line.startswith("units:")
            continue
        name = line.strip().partition(":")[0]
        if inside and line.startswith("  ") and name in durations:
            entry = read_yaml(line.strip())[name]
            entry["duration_seconds"] = durations[name]
            lines[index] = format_unit(name, entry)
            written += 1
    atomic_text(Path(path), "".join(lines))
    return written


def run_selection(root, model, path, tag, args, budget, provenance):
    """Run the selection under one aggregate budget and write the walls back."""
    chosen, selector = select(model, args.level, args.label)
    simulations = [name for name in chosen if model["units"][name]["kind"] == "sim"]
    # Fail before any simulator time is spent when a selected target cannot run.
    unrunnable = {}
    for target in simulations:
        try:
            load_target(Path(root), target)
        except Exception as error:
            unrunnable[target] = str(error)
    record = {"selector": selector, "level": args.level, "labels": list(args.label),
              "selected": len(chosen), "budget_seconds": budget, "broader": bool(args.broader),
              "catalogue": {"path": CATALOGUE, "sha256": file_hash(path)},
              "seed": args.seed, "units": {}, "failed": [], "skipped": [],
              "provenance": provenance or {}, "started": datetime.now(timezone.utc).isoformat()}
    started = time.monotonic()
    durations = {}
    for name in chosen:
        entry = model["units"][name]
        remaining = budget - (time.monotonic() - started)
        if remaining < MINIMUM_CHILD_SECONDS:
            outcome = {"status": "FAIL", "error": "aggregate budget exhausted before start"}
        elif name in unrunnable:
            outcome = {"status": "FAIL", "error": unrunnable[name]}
        elif entry["kind"] == "sim":
            outcome = run_simulation(root, tag, name, args, remaining)
        else:
            outcome = run_unit(root, name, entry)
        record["units"][name] = outcome
        if outcome["status"] == "SKIPPED":
            record["skipped"].append(name)
        elif outcome["status"] != "PASS":
            record["failed"].append(name)
        # Only an actual run has a wall worth recording: a skipped unit never
        # ran, and a CACHED simulation reports the cache check, not the work.
        if ("elapsed_seconds" in outcome and outcome["status"] != "SKIPPED"
                and outcome.get("cache") != "CACHED"):
            durations[name] = round(outcome["elapsed_seconds"], 2)
    record["elapsed_seconds"] = time.monotonic() - started
    record["finished"] = datetime.now(timezone.utc).isoformat()
    record["durations_written"] = record_durations(path, durations)
    if record["failed"]:
        named = ", ".join(f"{name} {record['units'][name]['status']}" for name in record["failed"])
        record.update(status="FAIL", error=f"selection {selector} failed: {named}")
    elif record["elapsed_seconds"] > budget:
        record.update(status="FAIL",
                      error=f"selection {selector} exceeded its {budget}-second aggregate budget")
    else:
        record["status"] = "PASS"
    return record


def budget_for(args):
    """Level 0 fits the ordinary pre-merge aggregate; anything wider declares itself."""
    budget = ORDINARY_BUDGET if args.budget is None else args.budget
    if type(budget) is not int or budget < MINIMUM_CHILD_SECONDS:
        raise ValueError(f"--budget must be an integer of at least {MINIMUM_CHILD_SECONDS} seconds")
    if budget > ORDINARY_BUDGET and not args.broader:
        raise ValueError(f"this selection declares {budget} seconds, above the ordinary "
                         f"{ORDINARY_BUDGET}-second pre-merge aggregate; pass --broader to run it "
                         "as a declared broader aggregate")
    return budget


def command(root, args, header, publish):
    """Dispatch one `tests` action."""
    root = Path(root)
    if args.action == "affected":
        from .affected import report as impact_report
        return {**header(args.tag or "-"), **impact_report(root, args.base)}
    if args.action in ("list", "validate"):
        report = header(args.tag or "-")
        model, path = load(root)
        if args.action == "validate":
            problems = coverage(root, model)
            report.update(units=len(model["units"]), labels=sorted(model["labels"]),
                          not_runnable=sorted(model["not_runnable"]), problems=problems,
                          status="FAIL" if problems else "PASS")
            if problems:
                report["error"] = problems[0]
            return report
        chosen, selector = select(model, args.level, args.label)
        known = [model["units"][name]["duration_seconds"] for name in chosen]
        report.update(status="PASS", selector=selector, selected=len(chosen), tests=chosen,
                      measured=sum(1 for value in known if value is not None),
                      measured_seconds=round(sum(value for value in known if value is not None), 2))
        return report

    model, path = load(root)
    problems = coverage(root, model)
    if problems:
        raise ValueError(problems[0])
    budget = budget_for(args)
    reclaimed = []
    with workspace(root, args.tag, reclaimed) as build:
        report = {**header(build.name), "status": "RUNNING"}
        if reclaimed:
            report["stale_lock_reclaimed"] = reclaimed[0].relative_to(Path(root)).as_posix()
        atomic_json(build / "status.json", {"status": "RUNNING"})
        atomic_json(build / "manifest.json", report)
    # The workspace is released before the children run: each simulation takes
    # the same tag as an ordinary sim test, exactly as a regression does.
    guard = build / "tests/.lock"
    guard.parent.mkdir(parents=True, exist_ok=True)
    latest = root / "workdir/latest.txt"
    previous = latest.read_text(encoding="utf-8") if latest.is_file() else None
    try:
        try:
            os.close(os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise ValueError(f"a selection on tag {build.name} is locked; confirm its runner "
                             f"stopped before removing {guard}")
        try:
            provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python")
                          if k in report}
            report.update(run_selection(root, model, path, build.name, args, budget, provenance))
            summary = build / "tests/summary.json"
            atomic_json(summary, report)
            report["summary"] = summary.relative_to(root).as_posix()
        finally:
            guard.unlink()
            if report.get("status") != "PASS":
                if previous is None:
                    latest.unlink(missing_ok=True)
                else:
                    atomic_text(latest, previous)
    except Exception as error:
        report.update(status="FAIL", error=str(error))
    try:
        with workspace(root, build.name) as build:
            publish(build, report)
    except ValueError as error:
        report.update(status="FAIL", error=f"{report.get('error', 'selection not published')}; {error}")
    return report
