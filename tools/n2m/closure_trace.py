"""Dynamic proof of declared host closures: run a unit under a file tracer and compare.

`host_closure.check` is a positive heuristic: a read through a root the test
passes into a helper, or inside an imported module, is invisible to it. This
module runs a declared unit exactly as the catalogue runner does, with a
`sitecustomize` audit hook on `PYTHONPATH` that records every repository file
the interpreter and its child interpreters open, list, glob or copy, and names
every tracked file read outside `host_closure.closure()`. Reads under `tools/`,
`cfg/`, `.github/`, the registry and the catalogue are not misses: a change
there already puts every unit on the affected report's global fallback.
Native tools such as Verilator read files the hook cannot see.
"""
import os
from pathlib import Path
import subprocess
import time

from . import affected, catalogue, host_closure
from .records import atomic_json

FALLBACK_PREFIXES = ("tools/", "cfg/", ".github/")
FALLBACK_FILES = ("src/dv/builder/targets.json", catalogue.CATALOGUE)
LOG = "N2M_TRACE_LOG"
TRACE_ROOT = "N2M_TRACE_ROOT"

# Installed as sitecustomize.py; every interpreter that inherits PYTHONPATH loads it at start.
TRACER = r'''
import os, sys
_log = os.environ.get("N2M_TRACE_LOG")
_root = os.environ.get("N2M_TRACE_ROOT")
if _log and _root:
    _skip = ("/workdir/", "/.git/", "/__pycache__/", "/.venv/", "/worktrees/")
    _busy = [False]

    def _record(kind, path):
        if _busy[0]:
            return
        _busy[0] = True
        try:
            p = os.fspath(path)
            if isinstance(p, bytes):
                p = p.decode(errors="replace")
            if not os.path.isabs(p):
                p = os.path.join(os.getcwd(), p)
            p = os.path.normpath(p)
            if p.startswith(_root + os.sep):
                rel = p[len(_root) + 1:].replace(os.sep, "/")
                if not any(s in "/" + rel + "/" for s in _skip):
                    with open(_log, "a", encoding="utf-8") as f:
                        f.write(kind + "|" + rel + "\n")
        except Exception:
            pass
        finally:
            _busy[0] = False

    def _hook(event, args):
        if event == "open":
            mode = args[1] or "r"
            if isinstance(mode, str) and ("r" in mode or mode == ""):
                _record("open", args[0])
        elif event in ("os.scandir", "os.listdir"):
            if args and args[0] is not None:
                _record("list", args[0])
        elif event == "glob.glob":
            _record("glob", args[0])
        elif event in ("shutil.copyfile", "shutil.copytree", "shutil.copymode", "shutil.copystat"):
            _record("copy", args[0])
        elif event == "subprocess.Popen" and not _busy[0]:
            _busy[0] = True
            try:
                with open(_log, "a", encoding="utf-8") as f:
                    f.write("popen|" + " ".join(str(a) for a in (args[1] or []))[:400].replace("\n", " ") + "\n")
            except Exception:
                pass
            finally:
                _busy[0] = False

    sys.addaudithook(_hook)
'''


def install(directory):
    """Write the tracer where PYTHONPATH will find it; returns that directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sitecustomize.py").write_text(TRACER.lstrip(), encoding="utf-8")
    return directory


def trace_unit(root, name, entry, tracer, log, python=None):
    """Run one unit under the tracer; returns its outcome and the accessed paths by kind."""
    root = Path(root).resolve()
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("", encoding="utf-8")
    command = catalogue.unit_command(root, name, entry, python)
    # The runner's own environment, with the tracer directory after tools/ so any
    # interpreter the unit starts loads sitecustomize from it.
    environment = catalogue.unit_environment(root)
    environment["PYTHONPATH"] = os.pathsep.join([environment["PYTHONPATH"], str(tracer)])
    environment[LOG] = str(log)
    environment[TRACE_ROOT] = str(root)
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=str(root), env=environment, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        outcome = {"exit_code": result.returncode, "status": "PASS" if result.returncode == 0 else "FAIL"}
        if result.returncode:
            outcome["error"] = catalogue.unit_error(result.stdout)
    except subprocess.TimeoutExpired:
        outcome = {"status": "FAIL", "error": "unit exceeded its 300-second wall budget"}
    outcome.update(command=command, elapsed_seconds=time.monotonic() - started)
    accessed, popen = {}, []
    for line in log.read_text(encoding="utf-8").splitlines():
        kind, _, path = line.partition("|")
        if kind == "popen":
            popen.append(path)
        elif path:
            accessed.setdefault(path, set()).add(kind)
    return outcome, accessed, popen


READS = ("open", "copy")


def misses(root, entry, closure, accessed, tracked):
    """Tracked files whose contents the unit read outside its closure and the global fallback.

    A directory listing or glob is not a miss: the affected report judges
    modified contents, and a file added, removed or renamed in a listed
    directory already forces its full fallback. Namespace-package imports
    list every parent directory, which is the common source of listings."""
    found = {}
    for path, kinds in accessed.items():
        if not kinds & set(READS) or path not in tracked:
            continue  # a listing, or an untracked scratch file, is never an input
        if path in closure or path in FALLBACK_FILES or path.startswith(FALLBACK_PREFIXES):
            continue
        found[path] = sorted(kinds)
    return found


def command(root, build, args):
    """`tests closure-trace [--unit NAME]`: every declared unit, or the named ones, traced and compared."""
    started = time.monotonic()
    root = Path(root).resolve()
    model, _ = catalogue.load(root)
    problems = catalogue.coverage(root, model)
    if problems:
        raise ValueError(problems[0])
    declared = {name: entry for name, entry in model["units"].items()
                if entry["kind"] == "unit" and entry.get("inputs") is not None}
    names = sorted(declared)
    if args.unit:
        unknown = sorted(set(args.unit) - set(declared))
        if unknown:
            raise ValueError(f"not a declared host unit: {', '.join(unknown)}")
        names = [n for n in names if n in args.unit]
    tracked = set(affected.tracked_files(root, "."))
    tracer = install(Path(build) / "closure-trace/tracer")
    cache = {}
    report = {"scope": "dynamic closure proof of the named declared units; required checks unchanged",
              "units": {}, "problems": []}
    for name in names:
        entry = declared[name]
        python = None
        if "needs-cocotb" in entry["labels"]:
            python = catalogue.cocotb_python(root)
            if python is None:
                report["units"][name] = {"status": "SKIPPED", "reason": "cocotb-environment"}
                report["problems"].append(f"unit {name} not traced: the pinned src/dv/python environment is not installed")
                continue
        log = Path(build) / "closure-trace" / (name.replace("/", "__") + ".log")
        outcome, accessed, popen = trace_unit(root, name, entry, tracer, log, python)
        closure = host_closure.closure(root, name, entry, model["external_imports"], cache,
                                       lambda d: affected.tracked_files(root, d))
        outside = misses(root, entry, closure, accessed, tracked)
        record = {**outcome, "accessed": len(accessed), "closure": len(closure), "misses": outside,
                  "children": sorted(set(popen)), "log": log.relative_to(root).as_posix()}
        report["units"][name] = record
        if outcome["status"] != "PASS":
            report["problems"].append(f"unit {name} not traced: {outcome.get('error', outcome['status'])}")
        for path in sorted(outside):
            report["problems"].append(f"unit {name} reads outside its declared closure: {path}")
        atomic_json(Path(build) / "closure-trace" / (name.replace("/", "__") + ".json"), record)
    report.update(traced=sum(1 for r in report["units"].values() if r.get("status") == "PASS"),
                  status="FAIL" if report["problems"] else "PASS", elapsed_seconds=time.monotonic() - started)
    if report["problems"]:
        report["error"] = report["problems"][0]
    return report
