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


def supervise(command, root, tag):
    from n2m.records import atomic_json, valid_tag
    if not valid_tag(tag):
        raise ValueError("invalid test budget tag")
    build = root / "workdir/builds" / tag
    if build.is_symlink() or build.resolve().parent != (root / "workdir/builds").resolve():
        raise ValueError("test budget path escapes builds")
    record = {"started": datetime.now(timezone.utc).isoformat(),
              "wall_limit_seconds": 600, "command": command, "status": "RUNNING"}
    path = build / "wall-budget" / (uuid.uuid4().hex + ".json")
    atomic_json(path, record)
    started = time.monotonic()
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, **options)
    timed_out = False
    try:
        output, _ = process.communicate(timeout=max(.001, 600 - (time.monotonic() - started)))
    except subprocess.TimeoutExpired as error:
        timed_out = True
        # Same process-tree termination used by the Quartus executor. Reap before
        # returning so a timed-out compiler, simulator or peer cannot keep running.
        output = error.output or b""
        record["cleanup_complete"] = False
        try:
            if os.name == "nt":
                cleanup = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
                record["cleanup_exit_code"] = cleanup.returncode
                if cleanup.returncode:
                    raise RuntimeError(f"process-tree cleanup failed: {cleanup.returncode}")
            else:
                os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate(timeout=5)
            record["cleanup_complete"] = True
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as cleanup_error:
            record["cleanup_error"] = str(cleanup_error)
            if isinstance(cleanup_error, subprocess.TimeoutExpired) and cleanup_error.output:
                output = cleanup_error.output
            # Reap the immediate worker if possible, but never wait indefinitely
            # for an inherited pipe held by a surviving descendant.
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired) as reap_error:
                record["reap_error"] = str(reap_error)
    text = output.decode("utf-8", errors="replace")
    record.update(status="TIMEOUT" if timed_out else "FINISHED", raw_exit_code=process.returncode,
                  elapsed_seconds=time.monotonic() - started,
                  finished=datetime.now(timezone.utc).isoformat())
    log = path.with_suffix(".log")
    log.write_text(text, encoding="utf-8")
    record["output"] = log.relative_to(root).as_posix()
    atomic_json(path, record)
    if timed_out:
        return 1, json.dumps({"status": "FAIL", "error": "test wall timeout after 600 seconds",
                              "tag": tag, "wall_budget": path.relative_to(root).as_posix(),
                              "raw_exit_code": process.returncode,
                              "cleanup_complete": record["cleanup_complete"],
                              "cleanup_error": record.get("cleanup_error")}) + "\n"
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
        code, output = supervise(command, root, tag)
    except (OSError, ValueError) as error:
        code, output = 1, json.dumps({"status": "FAIL", "error": str(error)}) + "\n"
    print(output, end="")
    return code


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from n2m.cli import main as worker
    raise SystemExit(worker())
