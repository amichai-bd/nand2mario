#!/usr/bin/env python3
"""Create the pinned wiki environment, then build with strict link checks."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "tools" / "wiki" / "requirements.txt"


def main() -> int:
    (ROOT / "workdir/wiki/docs").mkdir(parents=True, exist_ok=True)
    lock_hash = hashlib.sha256(LOCK.read_bytes()).hexdigest()[:16]
    runtime = f"python-{sys.version_info.major}.{sys.version_info.minor}"
    environment = ROOT / "workdir" / "tools" / "wiki" / runtime / lock_hash
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    ready = environment / ".ready"

    if not ready.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--require-hashes",
                "--requirement",
                str(LOCK),
            ],
            cwd=ROOT,
            check=True,
        )
        ready.write_text(lock_hash + "\n", encoding="utf-8")

    subprocess.run(
        [str(python), "-m", "unittest", "discover", "-s", "tools/wiki", "-p", "test_*.py"],
        cwd=ROOT,
        check=True,
    )
    return subprocess.run(
        [str(python), "-m", "mkdocs", "build", "--clean", "--strict"],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
