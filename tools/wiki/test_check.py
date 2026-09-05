"""Failed setup must not present previous browser evidence as current."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('wiki_check', Path(__file__).with_name('check.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


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
