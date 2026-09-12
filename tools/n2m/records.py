"""Content records, atomic publication, and exclusive tagged workspaces."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def sharing_denial(error):
    """A Windows replace blocked by another handle on the destination."""
    return getattr(error, "winerror", None) in (5, 32, 33)


def retry_denials(action, transient=sharing_denial, limit=6):
    """Retry the brief denials a concurrent reader or scanner causes. Any other
    error, and a denial that outlasts the backoff, propagates unchanged."""
    for attempt in range(limit):
        try:
            return action()
        except PermissionError as error:
            if not transient(error) or attempt == limit - 1:
                raise
            time.sleep(.01 * 2 ** attempt)


def published_bytes(path):
    """Read a file another writer may be replacing. Windows denies the open for
    the width of the replace, reporting a bare EACCES with no winerror."""
    def opening(error):
        return os.name == "nt" or sharing_denial(error)
    return retry_denials(Path(path).read_bytes, opening)


def atomic_text(path, text):
    _publish(path, lambda temp: temp.write_text(text, encoding="utf-8", newline="\n"))


def atomic_bytes(path, data):
    _publish(path, lambda temp: temp.write_bytes(data))


def _publish(path, write):
    """Write an owned temporary sibling, then replace the destination in one step."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        write(temp)
        # Never unlink the destination: readers must see the complete old or
        # new record, so a held handle is waited out rather than worked around.
        retry_denials(lambda: os.replace(temp, path))
    finally:
        # Do not mask a publication failure if a handle also blocks cleanup.
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def valid_tag(tag):
    reserved = {"con", "prn", "aux", "nul"} | {
        f"{name}{n}" for name in ("com", "lpt") for n in range(1, 10)
    }
    return (bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,47}", tag))
            and not tag.endswith(".") and tag.split(".")[0] not in reserved)


@contextmanager
def workspace(root, tag, notices=None):
    builds = root / "workdir/builds"
    builds.mkdir(parents=True, exist_ok=True)
    if tag is None:
        base = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
        tag = base
        suffix = 0
        while True:
            try:
                (builds / tag).mkdir()
                break
            except FileExistsError:
                suffix += 1
                tag = f"{base}-{suffix}"
    elif not valid_tag(tag):
        raise ValueError("tag must be a safe lowercase name of 1–48 characters")
    build = builds / tag
    build.mkdir(exist_ok=True)
    if build.resolve().parent != builds.resolve() or build.is_symlink():
        raise ValueError("tag path escapes workdir/builds")
    lock = build / ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # A lock whose recorded writer is dead is the leftover of a killed or
        # crashed process, never a live builder: reclaim it once, out loud.
        # A live or unreadable owner keeps the tag; nothing steals by age.
        owner = lock_owner(lock)
        if owner is None or pid_alive(owner):
            raise ValueError(f"tag {tag} is locked" + (f" by live pid {owner}" if owner else "")
                             + f"; confirm its writer stopped before removing {lock}")
        if reclaim_stale_lock(lock, owner) and notices is not None:
            notices.append(lock)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ValueError(f"tag {tag} was taken by another writer while its stale lock {lock} was reclaimed")
    try:
        # The handle stays open for the whole workspace: on Windows that denies
        # every rename or unlink by another process, so a live lock cannot be
        # reclaimed; only a dead writer's closed lock can.
        os.write(fd, f"pid={os.getpid()}\n".encode())
        yield build
    finally:
        os.close(fd)
        lock.unlink()


def lock_owner(lock):
    """Return the pid a tag lock records, or None when it cannot be read."""
    try:
        match = re.fullmatch(r"pid=(\d+)\s*", Path(lock).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return int(match.group(1)) if match else None


def pid_alive(pid):
    """True while the process exists; an access denial counts as alive."""
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # PROCESS_QUERY_LIMITED_INFORMATION opens another user's process too.
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: it exists
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stale_lock(lock):
    """True when the lock records a writer pid that is no longer alive."""
    owner = lock_owner(lock)
    return owner is not None and not pid_alive(owner)


def reclaim_stale_lock(lock, owner):
    """Remove a lock whose recorded writer is dead, saying so on stderr.

    The rename is the atomic claim: two reclaimers of one stale lock cannot
    both move it, and a lock a live holder keeps open cannot be moved at all
    on Windows. The claimed file is removed only while it still records the
    dead writer; anything else was another writer's fresh lock and goes back.
    Returns True when this call removed the stale lock.
    """
    lock = Path(lock)
    claimed = lock.with_name(f".lock.stale-{uuid.uuid4().hex}")
    try:
        os.replace(lock, claimed)
    except (FileNotFoundError, PermissionError):
        return False
    if lock_owner(claimed) != owner:
        os.replace(claimed, lock)
        return False
    claimed.unlink()
    print(f"reclaimed stale lock {lock}: its writer pid {owner} is not alive", file=sys.stderr)
    return True


def git_state(root):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "diff", "HEAD", "--binary"])
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    return {"commit": git("rev-parse", "HEAD"),
            "dirty_tree_fingerprint": digest({"diff": hashlib.sha256(dirty).hexdigest(),
                "untracked": {p: file_hash(root / p) for p in untracked if (root / p).is_file()}})}


def cache_matches(record, fingerprint, root, build=None):
    if record.get("status") != "PASS" or record.get("fingerprint") != fingerprint:
        return False
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return False
    boundary = (build or root / "workdir/builds").resolve()
    try:
        for name, expected in artifacts.items():
            path = (root / name).resolve()
            if not path.is_relative_to(boundary) or not path.is_file() or file_hash(path) != expected:
                return False
    except (OSError, TypeError, ValueError):
        return False
    return True
