#!/usr/bin/env python3
"""Create the pinned Markdown environment, test, scan text, and build the wiki."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "tools" / "wiki" / "requirements.txt"


def environment(root=ROOT, *, browser=False):
    """Return (directory, interpreter, lock) for the pinned environment of these locks.

    The directory is keyed by the running Python and by both lock files, so a
    changed pin builds a new environment instead of reusing an older one. It is
    the one place that rule lives; other tools read it rather than repeat it.
    """
    lock = LOCK.with_name("requirements-browser.txt") if browser else LOCK
    lock_hash = hashlib.sha256(LOCK.read_bytes() + lock.read_bytes()).hexdigest()[:16]
    runtime = f"python-{sys.version_info.major}.{sys.version_info.minor}"
    directory = Path(root) / "workdir" / "tools" / "wiki" / runtime / lock_hash
    interpreter = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return directory, interpreter, lock


def installed(root=ROOT):
    """The pinned interpreter with Python-Markdown, or None when none is built."""
    for browser in (False, True):
        directory, interpreter, _ = environment(root, browser=browser)
        if (directory / ".ready").is_file() and interpreter.is_file():
            return interpreter
    return None


def build(root=ROOT, *, browser=False, capture=False):
    """Create the pinned environment when it is absent; return its interpreter.

    The ready marker is written last, so an interrupted install is rebuilt
    rather than discovered. This is the one place the environment is created;
    other tools call it rather than repeat the venv and pip steps. `capture`
    keeps pip off the caller's stdout, which a `--json` caller needs; the
    transcript then travels in the raised error instead of being lost.
    """
    directory, interpreter, lock = environment(root, browser=browser)
    ready = directory / ".ready"
    if ready.is_file() and interpreter.is_file():
        return interpreter
    venv.EnvBuilder(with_pip=True).create(directory)
    install = [str(interpreter), "-m", "pip", "install", "--disable-pip-version-check",
               "--require-hashes", "--requirement", str(lock)]
    if not capture:
        subprocess.run(install, cwd=Path(root), check=True)
    else:
        result = subprocess.run(install, cwd=Path(root), text=True, encoding="utf-8",
                                errors="replace", stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"pip exited {result.returncode}: {result.stdout.strip()}")
    ready.write_text(directory.name + "\n", encoding="utf-8")
    return interpreter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true', help='Run headless interaction tests after building')
    parser.add_argument('--install-browser', action='store_true', help='Install pinned Chromium and OS dependencies')
    parser.add_argument('--browser-executable', type=Path, help='Use a local Chromium executable (local checks only)')
    args = parser.parse_args()
    if (args.install_browser or args.browser_executable) and not args.browser:
        parser.error('Browser options require --browser')
    if args.browser:
        output = ROOT / 'workdir/wiki/browser'
        output.mkdir(parents=True, exist_ok=True)
        (output / 'result.json').write_text('{"status": "starting"}', encoding='utf-8')
        for name in ('failure.png', 'trace.zip', 'quality-result.json', 'quality-trace.zip'):
            (output / name).unlink(missing_ok=True)
    (ROOT / "workdir/wiki/docs").mkdir(parents=True, exist_ok=True)
    python = build(ROOT, browser=args.browser)

    subprocess.run(
        [str(python), "-m", "unittest", "discover", "-s", "tools/wiki", "-p", "test_*.py"],
        cwd=ROOT,
        check=True,
    )
    result = subprocess.run(
        [str(python), "tools/wiki/site.py"],
        cwd=ROOT,
        check=False,
    ).returncode
    if result or not args.browser:
        return result
    temporary = ROOT / 'workdir/wiki/browser/tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': str(ROOT / 'workdir/tools/playwright'),
           'TMPDIR': str(temporary), 'TMP': str(temporary), 'TEMP': str(temporary)}
    if args.install_browser:
        subprocess.run([str(python), '-m', 'playwright', 'install', '--with-deps', '--only-shell', 'chromium'],
                       cwd=ROOT, env=env, check=True)
    extra = ['--browser-executable', str(args.browser_executable.resolve())] if args.browser_executable else []
    for script in ('tools/wiki/browser_tests.py', 'tools/wiki/browser_quality.py'):
        result = subprocess.run([str(python), script, *extra], cwd=ROOT, env=env, check=False).returncode
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
