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
        fd = take_lock(lock)
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
            fd = take_lock(lock)
        except FileExistsError:
            raise ValueError(f"tag {tag} was taken by another writer while its stale lock {lock} was reclaimed")
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode())
        discard_dead_siblings(lock)
        yield build
    finally:
        release_held_lock(fd, lock)


def take_lock(lock):
    """Create the lock exclusively and keep it held for the workspace's life.

    The handle stays open until release. On Windows that alone denies every
    rename or unlink by another process, so a live lock cannot be moved. On
    POSIX a rename or unlink is never denied, so the holder also takes an
    advisory flock on the file; a reclaimer must win that flock on the very
    inode it read before it may remove the lock. A reclaimer that opened this
    fresh file first holds the flock only for its check, so waiting is bounded.
    Raises FileExistsError when the tag is already locked.
    """
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    if os.name != "nt":
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def release_held_lock(fd, lock):
    """Release a held lock so no closed file recording a live pid is left.

    POSIX unlinks first and closes last: the flock covers the unlink, and a
    reclaimer that still holds the old inode open fails its identity check.
    Windows denies the unlink of an open file, so the handle closes first; if
    a stalled reclaimer moves the closed file in that instant, it puts the
    file back within its refusal, so the unlink waits briefly for our own pid
    to return rather than leaving a stale lock behind.
    """
    if os.name != "nt":
        try:
            os.unlink(lock)
        finally:
            os.close(fd)
        return
    os.close(fd)
    for attempt in range(6):
        owner = lock_owner(lock)
        if owner == os.getpid():
            try:
                # A loser reading the lock denies the unlink for an instant.
                retry_denials(lambda: os.unlink(lock))
                return
            except FileNotFoundError:
                pass  # moved between the read and the unlink; wait for it
        elif owner is not None or lock.exists():
            return  # another writer's fresh lock holds the tag now
        time.sleep(.01 * 2 ** attempt)
    # Still missing: a third writer took the tag and the moved file stays a
    # sibling recording this pid, swept by a later writer once it is dead.


def lock_owner(lock):
    """Return the pid a tag lock records, or None when it cannot be read."""
    try:
        return recorded_pid(Path(lock).read_bytes())
    except OSError:
        return None


def recorded_pid(data):
    try:
        match = re.fullmatch(r"pid=(\d+)\s*", data.decode("utf-8"))
    except ValueError:
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

    Exactly one reclaimer can remove a given stale lock, and a lock a live
    holder keeps cannot be removed at all. Windows proves both by an atomic
    rename: a held file cannot be moved, and the moved file is removed only
    while it still records the dead writer, else it is put back. POSIX proves
    both by the holder's flock: the reclaimer opens the lock, must win the
    flock without waiting, must find the same inode still at the lock path,
    and must re-read the dead writer from that inode before unlinking it.
    Nothing is ever renamed on POSIX, so a fresh lock is never displaced.
    Any loss returns False and never raises; the caller then retries the
    exclusive create and fails as taken by another writer.
    """
    lock = Path(lock)
    removed = _reclaim_nt(lock, owner) if os.name == "nt" else _reclaim_posix(lock, owner)
    if removed:
        print(f"reclaimed stale lock {lock}: its writer pid {owner} is not alive", file=sys.stderr)
    return removed


def _reclaim_posix(lock, owner):
    import fcntl
    try:
        fd = os.open(lock, os.O_RDONLY)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False  # a live writer or a reclaimer mid-check holds it
        try:
            held, named = os.fstat(fd), os.stat(lock)
        except OSError:
            return False  # unlinked or replaced since it was read
        if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
            return False  # the path now carries another writer's fresh lock
        if recorded_pid(os.pread(fd, 4096, 0)) != owner:
            return False
        try:
            os.unlink(lock)
        except OSError:
            return False
        return True
    finally:
        os.close(fd)


def _reclaim_nt(lock, owner):
    claimed = lock.with_name(f".lock.stale-{uuid.uuid4().hex}")
    try:
        # A held lock denies the rename for good; a concurrent reader of a
        # dead writer's lock denies it for an instant, so wait that out.
        retry_denials(lambda: os.replace(lock, claimed))
    except OSError:
        return False
    if lock_owner(claimed) == owner:
        try:
            retry_denials(lambda: claimed.unlink(missing_ok=True))
        except OSError:
            pass  # still open elsewhere; a later writer sweeps it
        return True
    # Another writer's closed file was moved: put it back. The put-back fails
    # when the writer released it meanwhile (nothing left to keep) or a third
    # writer already holds a fresh lock; then only a dead writer's file goes.
    try:
        retry_denials(lambda: os.replace(claimed, lock))
    except OSError:
        discard_dead_siblings(lock)
    return False


def discard_dead_siblings(lock):
    """Remove `.lock.stale-<id>` files a failed put-back left, once dead."""
    for sibling in Path(lock).parent.glob(".lock.stale-*"):
        try:
            if stale_lock(sibling):
                sibling.unlink(missing_ok=True)
        except OSError:
            pass  # still open elsewhere; the next writer sweeps again


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
