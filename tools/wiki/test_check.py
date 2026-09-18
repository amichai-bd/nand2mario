"""`installed` tells "not built" apart from "cannot tell", and failed setup must
not present previous browser evidence as current."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('wiki_check', Path(__file__).with_name('check.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class LocationTests(unittest.TestCase):
    """`installed` returns None only for "not built", and raises when it cannot tell.

    This module owns where the pinned environment lives, so it owns that
    distinction too. The test catalogue reads it through
    `n2m.catalogue.wiki_environment`: a None means the host has not built the
    environment and the `needs-wiki-env` unit may be skipped by name, while a
    raised error means the checkout cannot locate it at all and the unit must
    fail. Guarding the lock read here with `if not LOCK.is_file(): return None`
    would silently turn a broken checkout back into a passing selection with a
    skipped unit, which is the regression
    [the build SPEC](../../wiki/tools/n2m/SPEC.md#execution-and-contention)
    forbids. No test in the catalogue's own module can see that, because it
    stubs this one.
    """

    def workspace(self):
        parent = check.ROOT / 'workdir/wiki/tests'
        parent.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        locks = root / 'tools/wiki'
        locks.mkdir(parents=True)
        return root, locks / 'requirements.txt'

    def test_both_locks_present_and_nothing_built_reports_nothing_installed(self):
        root, lock = self.workspace()
        lock.write_text('Markdown==3.10.3\n', encoding='utf-8')
        lock.with_name('requirements-browser.txt').write_text('playwright==1.0\n', encoding='utf-8')
        with patch.object(check, 'LOCK', lock):
            self.assertIsNone(check.installed(root))
            directory, interpreter, _ = check.environment(root)
            self.assertEqual(interpreter.parent.parent, directory)

    def test_a_missing_lock_raises_rather_than_reporting_nothing_installed(self):
        """Each lock in turn: the hash cannot be computed, so nothing may be claimed."""
        for absent, browser in (('requirements.txt', False), ('requirements-browser.txt', True)):
            with self.subTest(absent=absent):
                root, lock = self.workspace()
                for name in ('requirements.txt', 'requirements-browser.txt'):
                    if name != absent:
                        lock.with_name(name).write_text('Markdown==3.10.3\n', encoding='utf-8')
                with patch.object(check, 'LOCK', lock):
                    with self.assertRaises(FileNotFoundError) as raised:
                        check.environment(root, browser=browser)
                    self.assertIn(absent, str(raised.exception.filename))
                    # `installed` tries both locks, so either one stops it.
                    with self.assertRaises(FileNotFoundError) as raised:
                        check.installed(root)
                    self.assertIn(absent, str(raised.exception.filename))


class EvidenceTests(unittest.TestCase):
    def test_setup_failure_invalidates_previous_browser_evidence(self):
        parent = check.ROOT / 'workdir/wiki/tests'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            root = Path(directory)
            output = root / 'workdir/wiki/browser'
            output.mkdir(parents=True)
            (output / 'result.json').write_text('{"status":"passed"}')
            for name in ('trace.zip', 'failure.png'):
                (output / name).write_bytes(b'old evidence')
            with patch.object(check, 'ROOT', root), patch.object(check.sys, 'argv', ['check.py', '--browser']), \
                    patch.object(check.venv.EnvBuilder, 'create'), \
                    patch.object(check.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'pip')):
                with self.assertRaises(subprocess.CalledProcessError):
                    check.main()
            self.assertIn('starting', (output / 'result.json').read_text())
            self.assertFalse((output / 'trace.zip').exists())
            self.assertFalse((output / 'failure.png').exists())
