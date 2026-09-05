"""Host failure contracts. Actual upstream runs are separate retained evidence."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.rgbds import compare, fetch, install, oracle

ROOT = Path(__file__).resolve().parents[3]


class RGBDSTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'workdir/builds/rgbds-host-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='space ', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'tools/n2m').mkdir(parents=True)
        shutil.copy(ROOT / 'tools/n2m/rgbds.py', self.root / 'tools/n2m/rgbds.py')
        shutil.copytree(ROOT / 'src/sw/oracle', self.root / 'src/sw/oracle')
        self.cache = self.root / 'workdir/builds/run/sw/oracle/cache'
        self.cache.mkdir(parents=True)
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            for name in ('rgbasm', 'rgblink'):
                archive.writestr('bin/' + name + '.exe', name.encode())
        self.data = data.getvalue()
        self.pin = {'version': '1.0.3', 'commit': 'reviewed-test-pin', 'notices': {},
                    'packages': {'windows-x86_64': {'url': 'https://invalid.example/package',
                                 'sha256': hashlib.sha256(self.data).hexdigest()}}}
        (self.root / 'tools/n2m/dependencies.json').write_text(json.dumps({'rgbds': self.pin}))
        (self.cache / 'package').write_bytes(self.data)
        self.machine = patch('n2m.rgbds.platform.machine', return_value='AMD64')
        self.machine.start()
        self.addCleanup(self.machine.stop)

    def install(self):
        return install(self.root, self.cache, True, 'windows-x86_64')

    def test_offline_install_and_verified_reuse_with_spaces(self):
        with patch('n2m.rgbds.urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            self.install()
            self.install()
        self.assertTrue((self.cache / 'bin/rgbasm.exe').exists())

    def test_offline_miss(self):
        (self.cache / 'package').unlink()
        with self.assertRaisesRegex(ValueError, 'offline cache miss'):
            self.install()

    def test_corrupt_archive_rejected_online_and_offline(self):
        (self.cache / 'package').write_bytes(b'corrupt')
        for offline in (True, False):
            with self.assertRaisesRegex(ValueError, 'cache integrity'):
                install(self.root, self.cache, offline, 'windows-x86_64')

    def test_corrupt_executable(self):
        self.install()
        (self.cache / 'bin/rgbasm.exe').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'installed tool integrity'):
            self.install()

    def test_missing_installed_tool(self):
        self.install()
        (self.cache / 'bin/rgblink.exe').unlink()
        with self.assertRaisesRegex(ValueError, 'missing installed tool'):
            self.install()

    def test_download_integrity_before_write(self):
        with patch('n2m.rgbds.urllib.request.urlopen', return_value=io.BytesIO(b'wrong')):
            with self.assertRaisesRegex(ValueError, 'download integrity'):
                fetch(self.pin['packages']['windows-x86_64'], self.cache / 'new', False)
        self.assertFalse((self.cache / 'new').exists())

    def test_corrupt_notice(self):
        item = {'url': 'https://invalid.example/license', 'sha256': hashlib.sha256(b'notice').hexdigest()}
        path = self.cache / 'notice'
        path.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'cache integrity'):
            fetch(item, path, True)

    def test_literal_comparison_and_mutations(self):
        expected = {'size': 4, 'padding': 255, 'regions': [{'offset': 1, 'hex': '42'}], 'symbols': {'Here': '00:0001'}}
        compare(bytes([255, 66, 255, 255]), '00:0001 Here', expected)
        for binary, symbols in [(bytes([255, 67, 255, 255]), '00:0001 Here'),
                                (bytes([255, 66, 255, 255]), '00:0002 Here'),
                                (bytes([255, 66, 255]), '00:0001 Here')]:
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                compare(binary, symbols, expected)

    def run_failed(self, result):
        args = SimpleNamespace(offline=True, expected=None)
        with patch('n2m.rgbds.install', return_value=(self.pin, {'rgbasm': Path('fake-rgbasm')}, {})), patch('n2m.rgbds.subprocess.run') as run:
            if isinstance(result, Exception):
                run.side_effect = result
            else:
                run.return_value = result
            report = oracle(self.root, self.root / 'workdir/builds/run', args, {})
        self.assertEqual(report['status'], 'FAIL')
        return report

    def test_wrong_version_is_not_conformance(self):
        report = self.run_failed(SimpleNamespace(returncode=0, stdout='rgbasm v0.0.0'))
        self.assertIn('version mismatch', report['error'])

    def test_raw_failure_is_not_success(self):
        report = self.run_failed(SimpleNamespace(returncode=7, stdout='rgbasm v1.0.3'))
        self.assertIn('exited 7', report['error'])
        self.assertTrue(any(p.endswith('.exit.json') for p in report['artifacts']))

    def test_timeout_retains_output(self):
        report = self.run_failed(subprocess.TimeoutExpired(['fake'], 60, output=b'last diagnostic'))
        self.assertIn('timed out', report['error'])
        logs = [self.root / p for p in report['artifacts'] if p.endswith('.log')]
        self.assertEqual(logs[0].read_text(), 'last diagnostic')


if __name__ == '__main__':
    unittest.main()
