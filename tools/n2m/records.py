"""Content records, atomic publication, and exclusive tagged workspaces."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8", newline="\n")
        # Windows readers may briefly deny delete sharing. Never unlink the
        # destination: readers must see the complete old or new record.
        for attempt in range(6):
            try:
                os.replace(temp, path)
                break
            except PermissionError as error:
                if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == 5:
                    raise
                time.sleep(.01 * 2 ** attempt)
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
def workspace(root, tag):
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
        raise ValueError(f"tag {tag} is locked; confirm its writer stopped before removing {lock}")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(f"pid={os.getpid()}\n")
        yield build
    finally:
        lock.unlink()


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
