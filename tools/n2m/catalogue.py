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
import platform
import re
import subprocess
import sys
import time

from . import host_closure
from .records import atomic_json, atomic_text, file_hash, read_json, workspace
from .simulation import UNSUPPORTED_REASON, simulator_problem, unsupported_backend
from .test_budget import supervise

CATALOGUE = "src/dv/builder/catalogue.yaml"
KINDS = ("sim", "unit")
LEVELS = (0, 1, 2)
# AGENTS.md: the ordinary pre-merge aggregate. Level 0 is built to fit inside it.
ORDINARY_BUDGET = 300
# A child needs its 12 reserved cleanup seconds plus at least one to run.
MINIMUM_CHILD_SECONDS = 13
# The smallest wall a real run may record. Anything that measured faster still
# ran, so it is recorded as 0.01 and 0.00 stays the mark of an unmeasured entry.
MINIMUM_DURATION = 0.01
# The conditions a recorded wall carries, in the order they are written: the UTC
# minute of the run, the commit it measured, the host family, and the run's own
# wall divided by its CPU time. Two entries sharing `at` were measured in one
# sitting, which is the only span their walls are comparable over. A simulation
# also carries `build`, the compile inside that wall, because a cold compile cache
# dominates it: `baseline-good` measured 20.48 s here with 20.17 s of compile,
# against the 0.41 s it records from a warm cache.
MEASURED_KEYS = ("at", "commit", "host", "wall_cpu")
MEASURED_OPTIONAL = ("build",)
MEASURED_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z")
MEASURED_TOKEN = re.compile(r"[A-Za-z0-9._+-]+")
# Contention on this host adds wall and almost no CPU: a measured 1.01 to 1.06
# times from one competitor to six. A run that took more than twice its own CPU
# therefore spent that time waiting rather than computing, and its wall does not
# describe the work. `tests record` refuses such a wall unless it is declared.
CONTENDED_RATIO = 2.0
# Below this wall the ratio is not a contention measurement and is never judged:
# a 0.18-second run measured here spent 0.08 seconds of CPU, a ratio of 2.26,
# with nothing competing, because fsync waits and the 10 ms CPU accounting tick
# dominate at that scale. The walls the ratio protects are the tens of seconds a
# simulation takes. The ratio is still recorded, so a reader can weigh it.
RATIO_FLOOR_SECONDS = 10.0
# How far a measured wall may stand from the recorded one before the run names
# it. The recorded figure has been seen 1.4 to 7 times a fresh measurement in
# either direction, so anything past this is worth a reader's attention.
DRIFT_FACTOR = 2.0
LABEL = re.compile(r"[a-z0-9][a-z0-9-]*")
TARGET = re.compile(r"[a-z0-9][a-z0-9_-]*")
UNIT_FILE = re.compile(r"[A-Za-z0-9_./-]+\.py")
INPUT_PATH = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./-]*")
EXTERNAL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Directories that hold generated output or another checkout, never our tree.
SKIP_DIRECTORIES = frozenset({".git", "workdir", "worktrees", "__pycache__", "node_modules", ".venv"})
# The pinned cocotb interpreter of src/dv/python/README.md; units labelled
# `needs-cocotb` import cocotb and cannot run on the builder interpreter.
COCOTB_PYTHON = ("workdir/builds/python-dv-env/.venv/Scripts/python.exe",
                 "workdir/builds/python-dv-env/.venv/bin/python")
# The pinned Python-Markdown environment `tools/wiki/check.py` builds; units
# labelled `needs-wiki-env` import it and cannot run on the builder interpreter.
WIKI_CHECK = "tools/wiki/check.py"

HEADER = ("# Catalogue of every runnable test unit: one entry per registry target and\n"
          "# per standalone test_*.py file. Levels are ordered, so selecting a level runs\n"
          "# every level below it. Labels are a set, validated against the vocabulary\n"
          "# below. duration_seconds is the wall of one deliberate measurement and 0.00\n"
          "# marks an entry nothing measured. Running a test never writes it: only\n"
          "# `tools/build.py tests record --tag <run>` does, from that run's retained\n"
          "# record, and it is never edited by hand. An entry's optional measured names\n"
          "# the sitting behind the wall, because the same work costs a different wall\n"
          "# from one sitting to the next. A host unit's optional inputs list the data\n"
          "# files or directories it reads; its module imports are derived, and\n"
          "# external_imports names the packages outside the tree they reach.\n"
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
    if model.get("external_imports"):
        lines.append("external_imports:\n")
        for name in sorted(model["external_imports"]):
            lines.append(f"  {name}: {_quote(model['external_imports'][name])}\n")
    lines.append("units:\n")
    for name in sorted(model["units"]):
        lines.append(format_unit(name, model["units"][name]))
    for key in ("not_runnable", "retired"):
        entries = model.get(key) or {}
        if not entries:
            if key == "not_runnable":
                lines.append("not_runnable: {}\n")
            continue
        lines.append(f"{key}:\n")
        for name in sorted(entries):
            lines.append(f"  {name}: {_quote(entries[name])}\n")
    return "".join(lines)


def format_unit(name, entry):
    labels = ", ".join(sorted(entry["labels"]))
    inputs = ""
    if entry.get("inputs") is not None:
        inputs = f", inputs: [{', '.join(sorted(entry['inputs']))}]"
    return (f"  {name}: {{kind: {entry['kind']}, level: {entry['level']}, "
            f"labels: [{labels}], duration_seconds: {_duration(entry['duration_seconds'])}"
            f"{inputs}{format_measured(entry.get('measured'))}}}\n")


def format_measured(measured):
    """Render the optional conditions in MEASURED_KEYS order, or nothing."""
    if not measured:
        return ""
    ratio = measured["wall_cpu"]
    body = [f"at: {_quote(measured['at'])}", f"commit: {_quote(measured['commit'])}",
            f"host: {_quote(measured['host'])}",
            "wall_cpu: " + ("null" if ratio is None else f"{float(ratio):.2f}")]
    if measured.get("build") is not None:
        body.append(f"build: {float(measured['build']):.2f}")
    return ", measured: {" + ", ".join(body) + "}"


# ------------------------------------------------------------------ the model

def load(root):
    """Read and validate the catalogue. Every rule here fails the build."""
    path = Path(root) / CATALOGUE
    model = read_yaml(path.read_text(encoding="utf-8"))
    if (not isinstance(model, dict)
            or set(model) - {"retired", "external_imports"} != {"version", "labels", "units", "not_runnable"}):
        raise ValueError("catalogue requires exactly version, labels, units and not_runnable, "
                         "plus optional external_imports and retired mappings")
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
        if (not isinstance(entry, dict)
                or set(entry) - {"inputs", "measured"} != {"kind", "level", "labels", "duration_seconds"}):
            raise ValueError(f"unit {name} requires exactly kind, level, labels and duration_seconds, "
                             "plus optional host inputs and measured conditions")
        if entry["kind"] not in KINDS:
            raise ValueError(f"unit {name} kind must be one of {', '.join(KINDS)}")
        if "inputs" in entry:
            inputs = entry["inputs"]
            if entry["kind"] != "unit":
                raise ValueError(f"unit {name} is a simulation target; its inputs live in targets.json")
            if not isinstance(inputs, list) or len(set(inputs)) != len(inputs):
                raise ValueError(f"unit {name} inputs must be a set of repository paths")
            for source in inputs:
                if (not isinstance(source, str) or not INPUT_PATH.fullmatch(source) or source.endswith("/")
                        or ".." in source.split("/")):
                    raise ValueError(f"unit {name} input is not a repository-relative path: {source}")
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
        if "measured" in entry:
            check_measured(name, entry["measured"], duration)
    excluded = model["not_runnable"]
    if not isinstance(excluded, dict):
        raise ValueError("catalogue not_runnable must be a mapping of path to reason")
    for name, reason in excluded.items():
        if not UNIT_FILE.fullmatch(name) or not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"not_runnable {name} requires a recorded reason")
        if name in units:
            raise ValueError(f"{name} is both a unit and not_runnable")
    # An external import is a package outside the tree that a host unit's import
    # closure reaches; it is named with its provenance so it never passes silently.
    model["external_imports"] = model.get("external_imports") or {}
    if not isinstance(model["external_imports"], dict):
        raise ValueError("catalogue external_imports must be a mapping of package name to provenance")
    for name, reason in model["external_imports"].items():
        if not EXTERNAL.fullmatch(name) or not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"external_imports {name} requires a recorded provenance")
    # A retired target is a former registry target the simulator cannot serve;
    # it is named with its reason so it never disappears silently.
    model["retired"] = model.get("retired") or {}
    if not isinstance(model["retired"], dict):
        raise ValueError("catalogue retired must be a mapping of target name to reason")
    for name, reason in model["retired"].items():
        if not TARGET.fullmatch(name) or not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"retired {name} requires a recorded reason")
        if name in units:
            raise ValueError(f"{name} is both a unit and retired")
    return model, path


def check_measured(name, measured, duration):
    """Prove one entry's recorded conditions describe a real measurement.

    A wall is only usable by the next reader with the sitting that produced it,
    so the conditions are validated as strictly as the wall itself. An entry may
    carry no conditions at all, which says the sitting behind its wall is
    unknown; it may never carry conditions without a wall."""
    if (not isinstance(measured, dict)
            or set(measured) - set(MEASURED_OPTIONAL) != set(MEASURED_KEYS)):
        raise ValueError(f"unit {name} measured requires exactly {', '.join(MEASURED_KEYS)}, "
                         f"plus optional {', '.join(MEASURED_OPTIONAL)}")
    if duration is None:
        raise ValueError(f"unit {name} records measured conditions without a duration_seconds")
    if not isinstance(measured["at"], str) or not MEASURED_AT.fullmatch(measured["at"]):
        raise ValueError(f"unit {name} measured at must be a UTC minute like 2026-09-20T14:22Z")
    for key in ("commit", "host"):
        if not isinstance(measured[key], str) or not MEASURED_TOKEN.fullmatch(measured[key]):
            raise ValueError(f"unit {name} measured {key} must be a single token")
    ratio = measured["wall_cpu"]
    if ratio is not None and (not isinstance(ratio, (int, float)) or ratio <= 0):
        raise ValueError(f"unit {name} measured wall_cpu must be null or a positive ratio")
    build = measured.get("build")
    if "build" in measured and (not isinstance(build, (int, float)) or not 0 <= build <= duration):
        raise ValueError(f"unit {name} measured build must be a share of its own wall")


def unmeasured(model):
    """Name every unit recording an impossible 0.00 wall.

    A measured wall is at least MINIMUM_DURATION and a unit nothing ran is
    null, so 0.00 can only be a hand-written duration that makes every
    selection holding it under-count its budget. This is reported by `validate`
    and `check` rather than by `coverage`, so the run that measures the unit is
    never blocked by the entry it is about to fix."""
    return [f"unit {name} records duration_seconds 0.00; run it so the catalogue carries "
            "its measured wall, or restore null"
            for name in sorted(model["units"]) if model["units"][name]["duration_seconds"] == 0]


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
    for name in sorted(set(model["retired"]) & set(targets)):
        problems.append(f"retired target {name} is still registered in targets.json")
    # A preload target's fixture inputs are checked here, not only when someone
    # runs that simulation, so an undeclared input fails a required check.
    # A SystemVerilog target declares them in `preload_inputs` and a Python one
    # in `python.inputs`; both must cover what the builder reads.
    from . import python_tb
    fixtures = {}
    for name in sorted(targets):
        target = targets[name]
        problem = simulator_problem(name, target)
        if problem:
            problems.append(f"registry {problem}")
            continue
        if target.get("preload") is None:
            continue
        try:
            if target.get("testbench") == "python":
                declared = set((target.get("python") or {}).get("inputs") or [])
                missing = sorted(python_tb.fixture_inputs(root, target["preload"]) - declared)
                if missing:
                    raise ValueError(f"{name}: python inputs omit fixture inputs: {', '.join(missing)}")
            else:
                python_tb.validate_fixture(root, target, name, fixtures)
        except (ValueError, OSError) as error:
            message = str(error)
            problems.append(f"registry {message if message.startswith(name + ':') else f'{name}: {message}'}")
    owned = target_inputs(targets)
    for path in discovered_tests(root):
        if path in files or path in model["not_runnable"] or path in owned:
            continue
        problems.append(f"test file {path} is missing from {CATALOGUE}")
    for path in sorted(files | set(model["not_runnable"])):
        if not (root / path).is_file():
            problems.append(f"catalogue entry {path} names no file in the tree")
    # Every host unit's import closure must be derivable, and a declared closure consistent.
    cache = {}
    for path in sorted(files):
        if (root / path).is_file():
            problems += host_closure.check(root, path, units[path], model["external_imports"], cache)
    # The recorded mutations name catalogue units and tracked paths; a stale row is a
    # coverage failure. Fixture trees carry no manifest; the proof harness requires the real one.
    from . import mutations
    if (root / mutations.MANIFEST).is_file():
        try:
            mutations.load(root, model)
        except (OSError, ValueError) as error:
            problems.append(f"{mutations.MANIFEST}: {error}")
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


def wiki_check(root):
    """Load `tools/wiki/check.py`, or None when it is absent.

    That module owns where the pinned wiki environment lives and how it is
    built. Both rules are read from there rather than repeated, so a changed
    pin moves the check and the catalogue together.
    """
    import importlib.util
    path = Path(root) / WIKI_CHECK
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("wiki_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WikiEnvironmentDefect(Exception):
    """The checkout cannot say where the pinned wiki environment belongs.

    This is a repository defect, not a host condition: `check.py` is missing or
    unreadable, or a lock file it hashes is gone. It is kept apart from a host
    that simply has not built the environment, because that one is a named skip
    and this one is a failure.
    """


def wiki_environment(root):
    """`(check.py module, installed interpreter)` for the pinned wiki environment.

    The interpreter is None when this host has not built the environment, which
    is an ordinary state a build can fix. A checkout that cannot answer the
    question at all raises `WikiEnvironmentDefect` instead, so the two never
    reach a caller as the same value.
    """
    try:
        module = wiki_check(root)
    except Exception as error:
        raise WikiEnvironmentDefect(f"{WIKI_CHECK} could not be read: {error}") from error
    if module is None:
        raise WikiEnvironmentDefect(f"{WIKI_CHECK} is not present")
    try:
        return module, module.installed(root)
    except Exception as error:
        # `installed` hashes the lock files, so a missing or unreadable
        # requirements file lands here rather than returning None.
        raise WikiEnvironmentDefect(
            f"the pinned tools/wiki environment could not be located: {error}") from error


def wiki_python(root):
    """The pinned wiki interpreter, or None when this host has not built it.

    Raises `WikiEnvironmentDefect` when the checkout itself is broken, so that
    cause can never be reported as a skipped unit.
    """
    _, interpreter = wiki_environment(root)
    return str(interpreter) if interpreter else None


def prepare_wiki_environment(root):
    """Build the pinned wiki environment once, before the aggregate clock starts.

    `test_site.py` imports the pinned Python-Markdown through `site.py`, so on a
    host that has never built the environment the unit has nothing to run on.
    Building it here makes the unit run for real rather than report a skip that
    would let the selection pass without it.

    Three outcomes are distinguished because they deserve different treatment:
    `PRESENT` or `BUILT` when the unit can run, `UNAVAILABLE` when the build
    itself cannot complete on this host, offline for example, and `BROKEN` when
    the checkout cannot locate the environment at all. Only `UNAVAILABLE` is a
    host condition, and only it degrades to a named skip.
    """
    started = time.monotonic()
    try:
        module, interpreter = wiki_environment(root)
    except WikiEnvironmentDefect as error:
        return {"status": "BROKEN", "elapsed_seconds": round(time.monotonic() - started, 3),
                "error": f"broken checkout: {error}"}
    if interpreter:
        return {"status": "PRESENT", "interpreter": str(interpreter)}
    try:
        # Captured: a `--json` run must leave exactly one object on stdout.
        interpreter = module.build(root, capture=True)
    except Exception as error:
        return {"status": "UNAVAILABLE", "elapsed_seconds": round(time.monotonic() - started, 3),
                "error": f"the pinned tools/wiki environment could not be built here: {error}"}
    return {"status": "BUILT", "elapsed_seconds": round(time.monotonic() - started, 3),
            "interpreter": str(interpreter)}


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
    elif "needs-wiki-env" in entry["labels"]:
        try:
            python = wiki_python(root)
        except WikiEnvironmentDefect as error:
            # A broken checkout is this repository's defect, so it fails the
            # unit. Skipping here is what would let a selection narrowed to
            # this label report success while the unit never ran.
            return {"status": "FAIL", "error": f"broken checkout: {error}"}
        if python is None:
            return {"status": "SKIPPED", "reason": "wiki-environment",
                    # Spelled as `wiki/tools/wiki/SPEC.md` spells it, which is the
                    # document this points the reader at. `discovery_note` says
                    # `python3` because its own SPEC's Linux examples do.
                    "error": "the pinned tools/wiki environment is not installed here and could "
                             "not be built; see the run's preparation record, or build it "
                             "with python tools/wiki/check.py"}
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


def run_simulation(root, tag, target, args, remaining):
    """Run one registry target as the ordinary sim-test worker."""
    command = [sys.executable, str(Path(root) / "tools/n2m/test_budget.py"), "sim", "test", target,
               "--tag", tag, "--seed", str(args.seed), "--sim", args.sim, "--json"]
    if args.rebuild:
        command.append("--rebuild")
    if getattr(args, "verilator_bin", None):
        command += ["--verilator-bin", args.verilator_bin]
    if getattr(args, "questa_bin", None):
        command += ["--questa-bin", args.questa_bin]
    if getattr(args, "intel_sim_lib", None):
        command += ["--intel-sim-lib", args.intel_sim_lib]
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
    for key in ("cache", "error", "timing"):
        if key in child:
            outcome[key] = child[key]
    if code == 0 and child.get("status") == "PASS":
        outcome["status"] = "PASS"
    else:
        outcome["status"] = "FAIL"
        outcome.setdefault("error", f"child exit {code} with status {child.get('status')}")
    for key in ("stale_lock_removed", "lock_left"):
        if key in child:
            outcome[key] = child[key]
    return outcome


def measured_duration(seconds):
    """The canonical recorded wall: two decimals, never a bare 0.00.

    A real run always took some time, so 0.00 is reserved: it can only come
    from an entry nothing ever measured, and `validate` fails on it."""
    return max(round(float(seconds), 2), MINIMUM_DURATION)


def record_durations(path, durations, measured=None):
    """Rewrite only the recorded unit lines, so comments and order survive.

    `measured` optionally carries each recorded unit's conditions; a unit it
    names keeps them beside its wall, and a unit it omits loses whatever
    conditions the entry held, because they described the previous wall."""
    if not durations:
        return 0
    measured = measured or {}
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
            entry.pop("measured", None)
            if name in measured:
                entry["measured"] = measured[name]
            lines[index] = format_unit(name, entry)
            written += 1
    atomic_text(Path(path), "".join(lines))
    return written


def cpu_seconds():
    """This process and every child it has reaped, in CPU seconds, or None.

    Windows reports no per-child CPU through `os.times`, so the whole idea of a
    wall-to-CPU ratio is unavailable there rather than wrong: a sim test spends
    its work in a child, and counting only this process would read as a host
    stalled on nothing. Off Windows the four fields are the run's own CPU."""
    if os.name == "nt":
        return None
    spent = os.times()
    return round(spent.user + spent.system + spent.children_user + spent.children_system, 3)


def wall_cpu_ratio(wall, cpu):
    """How much longer a run took than the CPU it spent, or None when unknown.

    The ratio is the instrument, not the load average: this host has reported
    the idle 0.27 while six competitors were live, while a run's own wall
    against its own CPU says directly whether it computed or waited."""
    if not isinstance(cpu, (int, float)) or cpu <= 0 or not isinstance(wall, (int, float)):
        return None
    return round(wall / cpu, 2)


def measured_walls(record):
    """Every unit in one retained run record whose wall describes actual work.

    Accepts either shape a run leaves behind: the `tests run` summary, which
    already names its own measured units, and the `sim test` manifest, which
    names one target and its locked wall. Only a run that actually executed
    counts: a cache hit reports the cache check, a skipped unit never ran and a
    failure has no trustworthy wall."""
    if isinstance(record.get("measured_walls"), dict):
        return record["measured_walls"]
    target = (record.get("requested") or {}).get("target")
    timing = record.get("timing") or {}
    if (not isinstance(target, str) or record.get("status") != "PASS"
            or record.get("cache") == "CACHED"
            or not isinstance(timing.get("locked_seconds"), (int, float))):
        return {}
    return {target: {"wall": timing["locked_seconds"], "cpu": timing.get("locked_cpu_seconds"),
                     "build": timing.get("build_seconds")}}


def sitting(record):
    """The conditions every wall in one run record shares: its minute, commit and host."""
    stamp = record.get("finished") or record.get("created") or ""
    minute = stamp[:16] + "Z" if MEASURED_AT.fullmatch(stamp[:16] + "Z") else (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
    # Twelve characters locate the commit in this repository and keep the entry
    # readable; the run's own record holds the full SHA.
    commit = str(record.get("commit") or "unknown")[:12]
    host = str(record.get("os") or "unknown") + "-" + platform.machine()
    return {"at": minute, "commit": commit, "host": host}


def record_from_run(root, tag, contended=False):
    """Write one retained run's measured walls into the catalogue, with conditions.

    This is the only path that writes a duration. It reads a run that already
    happened rather than measuring anything itself, so the figures it commits
    are the ones the author saw, and the sitting that produced them travels with
    them. A wall measured under contention is refused by name, because the
    recorded figures size shared budgets."""
    root = Path(root)
    source = None
    for candidate in (f"workdir/builds/{tag}/tests/summary.json", f"workdir/builds/{tag}/manifest.json"):
        if (root / candidate).is_file():
            source = candidate
            break
    if source is None:
        raise ValueError(f"no retained run record for tag {tag}; expected "
                         f"workdir/builds/{tag}/tests/summary.json or manifest.json")
    run = read_json(root / source)
    model, path = load(root)
    conditions = sitting(run)
    durations, measured, refused = {}, {}, {}
    for name, wall in sorted(measured_walls(run).items()):
        if name not in model["units"]:
            refused[name] = f"not a unit of {CATALOGUE}"
            continue
        ratio = wall_cpu_ratio(wall.get("wall"), wall.get("cpu"))
        judged = ratio is not None and wall.get("wall", 0) >= RATIO_FLOOR_SECONDS
        if judged and ratio > CONTENDED_RATIO and not contended:
            refused[name] = (f"took {ratio:.2f} times its own CPU, above {CONTENDED_RATIO:.2f}; "
                             "this wall measures waiting, not work. Pass --contended to record it")
            continue
        durations[name] = measured_duration(wall["wall"])
        measured[name] = {**conditions, "wall_cpu": ratio}
        # A simulation's wall is mostly its compile on a cold cache, so the
        # compile travels with it; a host unit builds nothing and omits it.
        if isinstance(wall.get("build"), (int, float)):
            measured[name]["build"] = min(round(wall["build"], 2), durations[name])
    written = record_durations(path, durations, measured)
    report = {"source": source, "measured": conditions,
              "recorded": {name: durations[name] for name in sorted(durations)},
              "not_recorded": refused, "durations_written": written,
              "catalogue": {"path": CATALOGUE, "sha256": file_hash(path)}}
    if not measured_walls(run):
        report.update(status="FAIL", error=f"{source} records no wall that describes actual work")
    else:
        report["status"] = "PASS"
    return report


def drifted(wall, recorded):
    """Whether a measured wall stands far enough from the recorded one to say so."""
    if not isinstance(recorded, (int, float)) or recorded <= 0:
        return True
    return not 1 / DRIFT_FACTOR <= wall / recorded <= DRIFT_FACTOR


def run_selection(root, model, path, tag, args, budget, provenance):
    """Run the selection under one aggregate budget; the walls stay in its record."""
    chosen, selector = select(model, args.level, args.label)
    simulations = [name for name in chosen if model["units"][name]["kind"] == "sim"]
    # Validate every selected target before any simulator time is spent. A
    # registry problem still fails the selection; a valid row that lacks the
    # requested backend is SKIPPED by name and never launched. It is neither a
    # pass nor a defect, and there is no fallback to the other simulator.
    unsupported = {}
    for target in simulations:
        message = unsupported_backend(Path(root), target, args.sim)
        if message:
            unsupported[target] = message
    # A unit that needs the pinned wiki interpreter gets it built here, once,
    # before the clock starts: installing a tool is preparation, not test work,
    # and the unit must actually run rather than skip on a fresh checkout. The
    # wall is recorded so the cost is visible and never hides inside the budget.
    preparation = {}
    if any("needs-wiki-env" in model["units"][name]["labels"] for name in chosen):
        preparation["wiki-environment"] = prepare_wiki_environment(root)
    record = {"selector": selector, "level": args.level, "labels": list(args.label),
              "selected": len(chosen), "budget_seconds": budget, "broader": bool(args.broader),
              "catalogue": {"path": CATALOGUE, "sha256": file_hash(path)},
              "seed": args.seed, "simulator": args.sim, "units": {}, "failed": [], "skipped": [],
              "preparation": preparation,
              "provenance": provenance or {}, "started": datetime.now(timezone.utc).isoformat(),
              "measured_walls": {}, "drift": []}
    started = time.monotonic()
    cpu_at = cpu_seconds()
    for name in chosen:
        entry = model["units"][name]
        remaining = budget - (time.monotonic() - started)
        if name in unsupported:
            outcome = {"status": "SKIPPED", "reason": UNSUPPORTED_REASON, "error": unsupported[name]}
        elif remaining < MINIMUM_CHILD_SECONDS:
            outcome = {"status": "FAIL", "error": "aggregate budget exhausted before start"}
        elif entry["kind"] == "sim":
            outcome = run_simulation(root, tag, name, args, remaining)
        else:
            outcome = run_unit(root, name, entry)
        # Units run one after another, so the CPU this process and its children
        # spent across two snapshots is this unit's own. A unit that never ran
        # has no CPU worth naming, so only a measured one carries the figure.
        now = cpu_seconds()
        spent = None if cpu_at is None else round(now - cpu_at, 3)
        cpu_at = now
        record["units"][name] = outcome
        if outcome["status"] == "SKIPPED":
            record["skipped"].append(name)
        elif outcome["status"] != "PASS":
            record["failed"].append(name)
        # Only an actual run has a wall worth keeping: a skipped unit never ran,
        # and a CACHED simulation reports the cache check, not the work. The
        # wall goes into this retained record and no further; writing it into
        # the tracked catalogue is `tests record`, which a person asks for.
        if ("elapsed_seconds" in outcome and outcome["status"] != "SKIPPED"
                and outcome.get("cache") != "CACHED"):
            wall = measured_duration(outcome["elapsed_seconds"])
            outcome["recorded_seconds"] = entry["duration_seconds"]
            if spent is not None:
                outcome["cpu_seconds"] = spent
            record["measured_walls"][name] = {"wall": wall, "cpu": spent,
                                              "build": (outcome.get("timing") or {}).get("build_seconds")}
            if drifted(wall, entry["duration_seconds"]):
                record["drift"].append(name)
    record["elapsed_seconds"] = time.monotonic() - started
    record["finished"] = datetime.now(timezone.utc).isoformat()
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
    if args.action in ("mutations", "closure-trace"):
        # Both are opt-in proofs about the catalogue's declarations; their clones,
        # traces and records live under the tag like any other build output.
        from . import closure_trace, mutations
        proof = mutations if args.action == "mutations" else closure_trace
        with workspace(root, args.tag) as build:
            report = header(build.name)
            try:
                report.update(proof.command(root, build, args))
            except Exception as error:
                report.update(status="FAIL", error=str(error))
            publish(build, report)
        return report
    if args.action == "record":
        # No workspace and no measurement: this reads a run that already
        # happened and writes its walls into the tracked catalogue, which is a
        # reviewed source change like any other.
        report = header(args.tag)
        report.update(record_from_run(root, args.tag, args.contended))
        return report
    if args.action in ("list", "validate"):
        report = header(args.tag or "-")
        model, path = load(root)
        if args.action == "validate":
            problems = coverage(root, model) + unmeasured(model)
            report.update(units=len(model["units"]), labels=sorted(model["labels"]),
                          not_runnable=sorted(model["not_runnable"]), retired=sorted(model["retired"]),
                          problems=problems,
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
