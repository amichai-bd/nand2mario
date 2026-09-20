"""The `check` host suite: the builder's test modules in concurrent groups, each inside one CPU budget.

`unittest` runs one module after another, so the whole suite's wall grew with
every module while its subprocess kept one 180-second budget. The groups here
split that run by module name into subprocesses that run at the same time: the
check wall is the slowest group, the CPU time is unchanged, and a group that
fails or exceeds its budget fails `check` by name. A test module no pattern
matches is a failure too, so a split never silently drops a file.

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

TESTS = "tools/n2m/tests"
# One group's own user plus system CPU time, its subprocess and every descendant it waits for.
# The f-l group of today's 913 tests measured about 112 s of CPU at load average 3, 149.1 s at 6.3,
# 151.3 s beside its two sibling groups at 7.0 to 9.7 and 144.3 s under six added CPU burners at
# 10.8, while its wall went 231, 260, 338 and 461 s. Contention costs some CPU and stops there; it
# stretches the wall without limit. 180 is the wall budget this replaced, kept as the number because
# a group's CPU never exceeds its wall, so nothing that passed before fails now.
CPU_BUDGET = 180
# A liveness guard, not a performance budget. The worst contention measured here stretched a
# group's wall to 3.2 times its CPU, so a group spending the whole CPU budget would take 574 s;
# 900 leaves margin above that, and only a group that stopped computing reaches it.
WALL_CEILING = 5 * CPU_BUDGET
# Alphabetical groups balanced once by measured module durations (910 tests, WSL2 host at load
# average about 4): a-e about 46 s, f-l about 53 s, m-z about 38 s of test time. Those figures no
# longer size this host, where the same groups spend about 100 to 122, 112 to 151 and 84 to 93 s of
# CPU; their order still holds. A new module joins the group its name falls in; rebalance the
# ranges, and take any budget, only from a fresh measurement.
GROUPS = ("test_[a-e]*.py", "test_[f-l]*.py", "test_[m-z]*.py")


class Child(subprocess.Popen):
    """A child process that reports the CPU time it and its own children used.

    `resource.getrusage(RUSAGE_CHILDREN)` sums every child this process reaped, so it
    cannot say which concurrent group spent what. `os.wait4` reports one pid's usage,
    but `Popen` reaps its child itself, so the only place the two meet is the reaping
    hook `Popen.wait` calls. When that hook is gone or `os.wait4` is absent, as on
    Windows, `cpu_seconds` stays None and the group falls back to its wall.
    """
    rusage = None

    def _try_wait(self, wait_flags):
        """Reap as `Popen` does and keep the rusage; the caller holds `_waitpid_lock`."""
        try:
            pid, status, usage = os.wait4(self.pid, wait_flags)
        except ChildProcessError:  # the child is gone and its status with it
            return self.pid, 0
        if pid == self.pid:  # 0 under WNOHANG means still running, with no usage yet
            self.rusage = usage
        return pid, status

    @property
    def cpu_seconds(self):
        return None if self.rusage is None else self.rusage.ru_utime + self.rusage.ru_stime


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


def contention(cpu, wall):
    """How much longer the group took than the CPU it spent, for a message or a log line."""
    return f"{wall / cpu:.1f}x" if cpu and cpu > 0 else "unknown"


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
    return f"{wall:.1f} s wall, {cpu:.1f} s CPU, {contention(cpu, wall)} its CPU{where}"


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
