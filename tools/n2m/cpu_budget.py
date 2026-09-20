"""One child process, the CPU it spent, and a wall ceiling that only catches a stall.

Three bounds in this repository budget the same quantity: a `check` group's
([host_suite](host_suite.py)), a host unit's ([catalogue](catalogue.py)) and the
play loop's ([springtrail_play](springtrail_play.py)). They budget CPU because
wall time on a shared host says how long work waited for a core, not how much
work it did: the same `check` content has been measured at 229.8, 282.8 and
637.8 s of wall for 141.6, 145.4 and 160.0 s of CPU, all three passing. The wall
spans 2.8 times and the CPU 1.13.

CPU is the better quantity because it has a worst case and the wall has none. On
this host, two physical cores with symmetric multithreading, contention inflates a
serial run's CPU to about 2.3 times its solo cost and then stops: 1.74, 2.31, 2.30
and 2.31 times against 2, 4, 8 and 16 competitors, while the same run's wall-to-CPU
ratio kept climbing to 4.31. That ceiling is the SMT limit, and it is what lets a
budget be judged against every load rather than one. It is not invariance: a
budget derived here has to cover it. The samples are in
[the SPEC](../../wiki/tools/n2m/SPEC.md#test-wall-budget).

The reaping hook and the bounded run live here so the quantity has one
definition rather than one per caller.
"""
import os
import subprocess
import time

# How long the read after a kill may take before it is abandoned. It is not a budget:
# a killed child's remaining output arrives at once, and anything longer means a
# descendant is holding the pipe, which no amount of waiting resolves.
CLEANUP_SECONDS = 5


class Child(subprocess.Popen):
    """A child process that reports the CPU time it and its own children used.

    `resource.getrusage(RUSAGE_CHILDREN)` sums every child this process reaped, so it
    cannot say which concurrent child spent what. `os.wait4` reports one pid's usage,
    but `Popen` reaps its child itself, so the only place the two meet is the reaping
    hook `Popen.wait` calls. When that hook is gone or `os.wait4` is absent, as on
    Windows, `cpu_seconds` stays None and the caller falls back to the wall.
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


def spawn(command, **kwargs):
    """Start `command`, measuring its CPU where the OS reports per-child usage."""
    child = Child if hasattr(os, "wait4") else subprocess.Popen
    return child(command, **kwargs)


def bounded(command, wall_ceiling, **kwargs):
    """Run `command` to its end or to the wall ceiling, and report what it spent.

    The ceiling is a liveness guard, not a performance budget: it exists so a
    child that has stopped computing still ends, and the caller judges the CPU
    afterwards. `cpu_seconds` is None where the OS reports no per-child usage,
    and `stalled` says the ceiling killed the child rather than the child
    finishing.

    A guard has to be bounded itself. Killing the child does not close the pipe
    it was writing to: every descendant that inherited it holds the write end,
    which is the ordinary state of a unit blocked inside a child it waits for.
    So the read after the kill is bounded and then abandoned, and the child is
    reaped either way. `subprocess.run` does the same thing for the same reason,
    reaping rather than reading again.
    """
    started = time.monotonic()
    child = spawn(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs)
    try:
        output, _ = child.communicate(timeout=wall_ceiling)
        stalled = False
    except subprocess.TimeoutExpired:
        stalled = True
        child.kill()
        output = drain(child)
    return {"exit_code": None if stalled else child.returncode, "output": output or "",
            "elapsed_seconds": time.monotonic() - started, "stalled": stalled,
            "cpu_seconds": getattr(child, "cpu_seconds", None)}


def drain(child, seconds=CLEANUP_SECONDS):
    """Whatever a killed child already wrote, without waiting on a descendant's pipe.

    Retrying `communicate` loses nothing that had arrived, so it is tried first
    and bounded. When a surviving descendant still holds the pipe that read
    cannot finish, so it is given up: the child is reaped for its usage and the
    pipe is dropped. Reaping is what makes `cpu_seconds` available at all.
    """
    try:
        return child.communicate(timeout=seconds)[0]
    except subprocess.TimeoutExpired:
        try:
            child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:  # SIGKILL cannot be caught; nothing else to try
            pass
        for stream in (child.stdout, child.stderr, child.stdin):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        return None


def ratio(cpu, wall):
    """How much longer the work took than the CPU it spent, for a message or a log line."""
    return f"{wall / cpu:.1f}x" if cpu and cpu > 0 else "unknown"
