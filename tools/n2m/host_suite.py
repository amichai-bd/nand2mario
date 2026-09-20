"""The `check` host suite: the builder's test modules in concurrent groups, each inside one CPU budget.

`unittest` runs one module after another, so the whole suite's wall grew with
every module while its subprocess kept one budget. The groups here split that
run by module name into subprocesses that run at the same time: the check wall is
the slowest group, the CPU time is unchanged, and a group that fails or exceeds
its budget fails `check` by name. A test module no pattern matches is a failure
too, so a split never silently drops a file.

The budget is the group's own CPU time, not its wall. Up to four agents work
this machine at once, so a group's wall says how long it waited for a core and
a wall budget failed work that was not slow; the CPU a group spends is its own
either way. `WALL_CEILING` is only a liveness guard, so a group that grows slow
by blocking rather than by computing is what neither number catches.
"""
from concurrent.futures import ThreadPoolExecutor
import fnmatch
import os
from pathlib import Path
import subprocess
import sys
import time

from . import catalogue
# A group and a host unit budget the same quantity; `cpu_budget` defines it once.
from . import cpu_budget
from .cpu_budget import Child

TESTS = "tools/n2m/tests"
# One group's own user plus system CPU time, its subprocess and every descendant it waits for.
# Each group has now been measured alone, which `check` itself never does because it runs all
# three at once: a-e 68.7 s, f-l 77.3 to 89.2 s and m-z 89.1 to 94.5 s of CPU across two
# sittings, so the worst group alone spends 94.5 s. Against four deliberate CPU burners in one
# sitting the same three content sets spent 116.9, 135.4 and 118.1 s, up to 1.75 times their
# own solo cost, while their walls went 2.0 to 3.0 times. Beside its siblings on a busy host a
# group has reached 160.0 s.
# 240 is 2.5 times the worst group measured alone. It clears that group's solo cost times the
# 1.75 contention inflation and the 1.16 cross-sitting spread, whose product is 192, and sits
# 1.5 times above the worst group CPU ever measured here. The 180 it replaces was the old wall
# budget carried over, not a derived figure, and it sat only 1.13 times above that 160.0.
CPU_BUDGET = 240
# A liveness guard, not a performance budget. The worst contention measured here stretched a
# group's wall to 4.5 times its CPU, so a group spending the whole CPU budget would take
# 1070 s; five times the budget leaves margin above that, and only a group that stopped
# computing reaches it.
WALL_CEILING = 5 * CPU_BUDGET
# Alphabetical groups, balanced once by measured module durations on another host. Measured alone
# here they cost 68.7, 77.3 to 89.2 and 89.1 to 94.5 s of CPU, a 1.4 spread across the three, so
# the ranges still balance even though the order has changed and m-z is now the heaviest. A new
# module joins the group its name falls in; rebalance the ranges, and take any budget, only from
# a fresh measurement.
GROUPS = ("test_[a-e]*.py", "test_[f-l]*.py", "test_[m-z]*.py")


def modules(root):
    """Every test module `unittest discover` runs from the suite directory."""
    return sorted(path.name for path in (Path(root) / TESTS).glob("test_*.py"))


def unmatched(names):
    """The modules no group pattern selects."""
    return [name for name in names if not any(fnmatch.fnmatchcase(name, group) for group in GROUPS)]


def command(root, pattern):
    return [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(Path(root) / TESTS), "-p", pattern, "-v"]


def load_average():
    """This host's one, five and fifteen minute load averages, or None where the OS keeps none.

    All three, because the one-minute figure alone reads a lull as a quiet host: it has
    been seen at 1.86 with the five-minute average at 4.27 and the load back at 5.68
    immediately after. Nothing here decides anything from load; it is recorded so a
    reader can see what the machine was doing.
    """
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except (OSError, AttributeError):
        return None


def spawn(root, run):
    """The group's subprocess, with CPU accounting where the OS reports per-child usage."""
    child = Child if hasattr(os, "wait4") else subprocess.Popen
    return child(run, cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def run_group(root, pattern):
    """One group's subprocess under the budget; its output is kept for the combined log."""
    started = time.monotonic()
    run = command(root, pattern)
    outcome = {"pattern": pattern, "command": run}
    child = spawn(root, run)
    try:
        output, _ = child.communicate(timeout=WALL_CEILING)
        stalled = False
    except subprocess.TimeoutExpired:
        child.kill()
        output, _ = child.communicate()
        stalled = True
    wall = time.monotonic() - started
    cpu = getattr(child, "cpu_seconds", None)
    outcome.update(exit_code=None if stalled else child.returncode, output=output or "",
                   elapsed_seconds=wall, cpu_seconds=cpu, load_average=load_average(),
                   status="PASS" if child.returncode == 0 and not stalled else "FAIL")
    if stalled:
        spent = f"{cpu:.0f} s of CPU" if cpu is not None else "an unmeasured amount of CPU"
        outcome["error"] = (f"group {pattern} made no progress: it ran {wall:.0f} s, past the "
                            f"{WALL_CEILING}-second wall ceiling, for {spent}")
    elif child.returncode:
        outcome["error"] = f"group {pattern}: {catalogue.unit_error(output or '')}"
    elif cpu is None and wall > CPU_BUDGET:
        # No per-child CPU on this OS, so the wall is all there is; say which it failed on.
        outcome.update(status="FAIL",
                       error=f"group {pattern} ran {wall:.0f} s, over its {CPU_BUDGET}-second budget; "
                             "this host reports no per-child CPU time, so a busy machine can fail it")
    elif cpu is not None and cpu > CPU_BUDGET:
        outcome.update(status="FAIL",
                       error=f"group {pattern} used {cpu:.0f} s of CPU, over its {CPU_BUDGET}-second "
                             f"CPU budget (wall {wall:.0f} s)")
    return outcome


def summary(group):
    """One group's headline for the combined log: its wall, and the CPU that was budgeted."""
    cpu, wall, load = group["cpu_seconds"], group["elapsed_seconds"], group["load_average"]
    if cpu is None:
        return f"{wall:.1f} s wall (this host reports no per-child CPU time)"
    where = "" if load is None else ", load average " + "/".join(f"{value:.1f}" for value in load)
    return f"{wall:.1f} s wall, {cpu:.1f} s CPU, {cpu_budget.ratio(cpu, wall)} its CPU{where}"


def run(root, log):
    """Run every group at once, write the combined log and return (report fields, problems)."""
    root = Path(root)
    missing = unmatched(modules(root))
    with ThreadPoolExecutor(len(GROUPS)) as pool:
        groups = list(pool.map(lambda pattern: run_group(root, pattern), GROUPS))
    Path(log).write_text("".join(f"== group {g['pattern']}: {g['status']} in {summary(g)}\n"
                                 f"{g['output']}\n" for g in groups), encoding="utf-8")
    problems = ([f"test module {name} matches no check group" for name in missing]
                + [g["error"] for g in groups if g["status"] == "FAIL"])
    fields = {"commands": [g["command"] for g in groups],
              "groups": [{k: v for k, v in g.items() if k not in ("output", "command")} for g in groups],
              "wall_seconds": max(g["elapsed_seconds"] for g in groups),
              "cpu_seconds": None if any(g["cpu_seconds"] is None for g in groups)
                             else sum(g["cpu_seconds"] for g in groups)}
    return fields, problems
