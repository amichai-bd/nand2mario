"""Bound the public sim-test invocation, including its preparation and children."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


# The user's bounded Mooneye authorization; this is not a configurable override.
MILESTONE_TARGETS = frozenset({'mooneye-reg-f', 'mooneye-corrupt', 'mooneye-missing'})
# Every target that declares nothing gets exactly this.
WALL_DEFAULT = 300
# The owner's hard ceiling for a declared per-target allowance. Not a default.
WALL_ALLOWANCE_CEILING = 900


def declared_allowance(name, row):
    """Return a target row's declared wall allowance, or None when it declares none.

    A malformed, over-ceiling or reasonless declaration raises; it is never
    clamped, because a silent clamp would hide the budget the target needs.
    """
    if not isinstance(row, dict) or "wall_allowance" not in row:
        return None
    allowance = row["wall_allowance"]
    if not isinstance(allowance, dict) or set(allowance) != {"seconds", "reason"}:
        raise ValueError(f"{name} wall_allowance requires exactly seconds and reason")
    seconds = allowance["seconds"]
    if type(seconds) is not int or not WALL_DEFAULT < seconds <= WALL_ALLOWANCE_CEILING:
        raise ValueError(f"{name} wall_allowance seconds must be an integer in "
                         f"{WALL_DEFAULT + 1}..{WALL_ALLOWANCE_CEILING}")
    reason = allowance["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{name} wall_allowance requires a recorded reason")
    return seconds, reason.strip()


def target_selection(name, row):
    """Return (limit, reason) for one registry row."""
    if name in MILESTONE_TARGETS:
        return 1500, None
    allowance = declared_allowance(name, row)
    return allowance if allowance else (WALL_DEFAULT, None)


def wall_selection(target, root=None):
    """Resolve (limit, reason) for a target name by reading the target registry."""
    if target in MILESTONE_TARGETS:
        return 1500, None
    if not isinstance(target, str) or not target:
        return WALL_DEFAULT, None
    root = Path(__file__).resolve().parents[2] if root is None else Path(root)
    registry = root / "src/dv/builder/targets.json"
    if not registry.is_file():
        return WALL_DEFAULT, None
    return target_selection(target, json.loads(registry.read_text(encoding="utf-8")).get(target))


def wall_limit(target, root=None):
    return wall_selection(target, root)[0]


def release_lock(lock, worker_pid, record):
    """Free the tag lock a killed worker never released.

    The worker's finally never ran, so its lock outlives it. A lock whose
    recorded writer is dead is removed; one a live foreign writer holds is
    not ours. Any lock left is named, and one that should have gone marks
    the cleanup incomplete, so no report calls a locked tag clean.
    """
    from n2m.records import lock_owner, pid_alive, reclaim_stale_lock
    if not lock.is_file():
        return
    owner = lock_owner(lock)
    if owner is not None and not pid_alive(owner):
        try:
            if reclaim_stale_lock(lock, owner):
                record["stale_lock_removed"] = True
                return
        except OSError as error:
            record["cleanup_error"] = f"lock release failed: {error}"
    if not lock.is_file():
        # Another command reclaimed it first; the tag is free.
        return
    record["lock_left"] = lock.as_posix()
    # Unreadable, still the worker's, or dead but not removable: not clean.
    if owner is None or owner == worker_pid or not pid_alive(owner):
        record["cleanup_complete"] = False


def supervise(command, root, tag, *, target=None, ceiling=None):
    limit, allowance_reason = wall_selection(target, root)
    # A regression caps a child at its remaining aggregate seconds. The cap
    # only shrinks the selected budget; nothing here extends it.
    if ceiling is not None:
        if type(ceiling) is not int or ceiling < 13:
            raise ValueError("wall ceiling must be an integer of at least 13 seconds")
        limit = min(limit, ceiling)
    execution_limit = limit - 12
    started = time.monotonic()
    wall_started = datetime.now(timezone.utc).timestamp()
    deadline = started + limit
    # Reserve the existing 5s tree kill, 5s pipe drain and 2s fallback reap.
    execution_deadline = deadline - 12
    def remaining(wait_limit, end=deadline):
        seconds = end - time.monotonic()
        if seconds <= 0:
            raise subprocess.TimeoutExpired(command, limit)
        return min(wait_limit, seconds)

    from n2m.records import atomic_json, valid_tag
    if not valid_tag(tag):
        raise ValueError("invalid test budget tag")
    build = root / "workdir/builds" / tag
    if build.is_symlink() or build.resolve().parent != (root / "workdir/builds").resolve():
        raise ValueError("test budget path escapes builds")
    record = {"started": datetime.now(timezone.utc).isoformat(),
              "wall_limit_seconds": limit, "execution_limit_seconds": execution_limit,
              "target": target,
              "command": command, "status": "RUNNING"}
    if allowance_reason is not None:
        record["wall_allowance_reason"] = allowance_reason
    if ceiling is not None:
        record["wall_ceiling_seconds"] = ceiling
    path = build / "wall-budget" / (uuid.uuid4().hex + ".json")
    atomic_json(path, record)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    environment = dict(os.environ)
    # Cross-OS children need their own deadline; Windows taskkill cannot reap WSL.
    environment['N2M_TEST_EXECUTION_DEADLINE'] = str(wall_started + execution_limit)
    process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=environment, **options)
    timed_out = False
    errors = b""
    try:
        output, errors = process.communicate(timeout=remaining(execution_limit, execution_deadline))
    except subprocess.TimeoutExpired as error:
        timed_out = True
        # Same process-tree termination used by the Quartus executor. Reap before
        # returning so a timed-out compiler, simulator or peer cannot keep running.
        output = error.output or b""
        errors = error.stderr or b""
        record["cleanup_complete"] = False
        try:
            if os.name == "nt":
                cleanup = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=remaining(5))
                record["cleanup_exit_code"] = cleanup.returncode
                if cleanup.returncode:
                    raise RuntimeError(f"process-tree cleanup failed: {cleanup.returncode}")
            else:
                os.killpg(process.pid, signal.SIGKILL)
            output, errors = process.communicate(timeout=remaining(5))
            record["cleanup_complete"] = True
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as cleanup_error:
            record["cleanup_error"] = str(cleanup_error)
            if isinstance(cleanup_error, subprocess.TimeoutExpired) and cleanup_error.output:
                output = cleanup_error.output
            if isinstance(cleanup_error, subprocess.TimeoutExpired) and cleanup_error.stderr:
                errors = cleanup_error.stderr
            # Reap the immediate worker if possible, but never wait indefinitely
            # for an inherited pipe held by a surviving descendant.
            try:
                process.kill()
                process.wait(timeout=remaining(2))
            except (OSError, subprocess.TimeoutExpired) as reap_error:
                record["reap_error"] = str(reap_error)
    if timed_out:
        release_lock(build / ".lock", process.pid, record)
    text = output.decode("utf-8", errors="replace")
    error_text = (errors or b"").decode("utf-8", errors="replace")
    record.update(status="TIMEOUT" if timed_out else "FINISHED", raw_exit_code=process.returncode,
                  elapsed_seconds=time.monotonic() - started,
                  finished=datetime.now(timezone.utc).isoformat())
    log = path.with_suffix(".log")
    log.write_text(text, encoding="utf-8")
    record["output"] = log.relative_to(root).as_posix()
    error_log = path.with_suffix(".stderr.log")
    error_log.write_text(error_text, encoding="utf-8")
    record["stderr"] = error_log.relative_to(root).as_posix()
    atomic_json(path, record)
    if timed_out:
        return 1, json.dumps({"status": "FAIL", "error": f"test wall budget exhausted ({limit} seconds total, 12 reserved for cleanup)",
                              "tag": tag, "wall_budget": path.relative_to(root).as_posix(),
                              "raw_exit_code": process.returncode,
                              "cleanup_complete": record["cleanup_complete"],
                              "cleanup_error": record.get("cleanup_error"),
                              **{key: record[key] for key in ("stale_lock_removed", "lock_left") if key in record}}) + "\n"
    # Keep --json stdout parseable even when discovery/git emits stderr.
    print(error_text, end="", file=sys.stderr)
    return process.returncode, text


def main():
    from n2m.cli import main as worker, parser
    argv = sys.argv[1:]
    if argv[:2] != ["sim", "test"]:
        return worker(argv)
    args = parser().parse_args(argv)
    tag = args.tag
    if tag is None:
        tag = "test-" + uuid.uuid4().hex
        argv += ["--tag", tag]
    root = Path(__file__).resolve().parents[2]
    command = [sys.executable, str(Path(__file__).resolve()), *argv]
    try:
        code, output = supervise(command, root, tag, target=args.target)
    except (OSError, ValueError) as error:
        code, output = 1, json.dumps({"status": "FAIL", "error": str(error)}) + "\n"
    print(output, end="")
    return code


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from n2m.cli import main as worker
    raise SystemExit(worker())
