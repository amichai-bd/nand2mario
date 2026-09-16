"""The `check` host suite: the builder's test modules in concurrent groups, each inside one wall budget.

`unittest` runs one module after another, so the whole suite's wall grew with
every module while its subprocess kept one 180-second budget. The groups here
split that run by module name into subprocesses that run at the same time: the
check wall is the slowest group, the CPU time is unchanged, and a group that
fails or exceeds its budget fails `check` by name. A test module no pattern
matches is a failure too, so a split never silently drops a file.
"""
from concurrent.futures import ThreadPoolExecutor
import fnmatch
from pathlib import Path
import subprocess
import sys
import time

from . import catalogue

TESTS = "tools/n2m/tests"
BUDGET = 180
# Alphabetical groups balanced once by measured module durations (910 tests, WSL2 host at load
# average about 4): a-e about 46 s, f-l about 53 s, m-z about 38 s of test time. A new module
# joins the group its name falls in; rebalance the ranges only from a fresh measurement.
GROUPS = ("test_[a-e]*.py", "test_[f-l]*.py", "test_[m-z]*.py")


def modules(root):
    """Every test module `unittest discover` runs from the suite directory."""
    return sorted(path.name for path in (Path(root) / TESTS).glob("test_*.py"))


def unmatched(names):
    """The modules no group pattern selects."""
    return [name for name in names if not any(fnmatch.fnmatchcase(name, group) for group in GROUPS)]


def command(root, pattern):
    return [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(Path(root) / TESTS), "-p", pattern, "-v"]


def run_group(root, pattern):
    """One group's subprocess under the budget; its output is kept for the combined log."""
    started = time.monotonic()
    run = command(root, pattern)
    outcome = {"pattern": pattern, "command": run}
    try:
        result = subprocess.run(run, cwd=str(root), text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=BUDGET)
        outcome.update(exit_code=result.returncode, output=result.stdout,
                       status="PASS" if result.returncode == 0 else "FAIL")
        if result.returncode:
            outcome["error"] = f"group {pattern}: {catalogue.unit_error(result.stdout)}"
    except subprocess.TimeoutExpired as expired:
        outcome.update(exit_code=None, output=expired.output or "", status="FAIL",
                       error=f"group {pattern} exceeded its {BUDGET}-second wall budget")
    outcome["elapsed_seconds"] = time.monotonic() - started
    return outcome


def run(root, log):
    """Run every group at once, write the combined log and return (report fields, problems)."""
    root = Path(root)
    missing = unmatched(modules(root))
    with ThreadPoolExecutor(len(GROUPS)) as pool:
        groups = list(pool.map(lambda pattern: run_group(root, pattern), GROUPS))
    Path(log).write_text("".join(f"== group {g['pattern']}: {g['status']} in {g['elapsed_seconds']:.1f} s\n"
                                 f"{g['output']}\n" for g in groups), encoding="utf-8")
    problems = ([f"test module {name} matches no check group" for name in missing]
                + [g["error"] for g in groups if g["status"] == "FAIL"])
    fields = {"commands": [g["command"] for g in groups],
              "groups": [{k: v for k, v in g.items() if k not in ("output", "command")} for g in groups],
              "wall_seconds": max(g["elapsed_seconds"] for g in groups)}
    return fields, problems
