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
    lock = LOCK.with_name('requirements-browser.txt') if args.browser else LOCK
    (ROOT / "workdir/wiki/docs").mkdir(parents=True, exist_ok=True)
    lock_hash = hashlib.sha256(LOCK.read_bytes() + lock.read_bytes()).hexdigest()[:16]
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
                str(lock),
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
