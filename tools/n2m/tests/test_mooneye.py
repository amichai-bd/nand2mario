"""Locked fixture boundaries; no network or simulator needed by these tests."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import mooneye, preload
from n2m import mooneye_wsl

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('mooneye_check', ROOT/'src/dv/mooneye/check.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class MooneyeTests(unittest.TestCase):
    def setUp(self):
        base = ROOT/'workdir/builds/mooneye-unit'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_linked_whole_signature_only(self):
        record = dict(pc_before=0x4a81, pc_after=0x4a82, opcode=0x40, opcode_length=1,
                      b=3, c=5, d=8, e=13, h=21, l=34)
        self.assertTrue(checker.completion(record))
        self.assertFalse(checker.completion(dict(record, pc_before=0x200)))
        self.assertFalse(checker.completion(dict(record, opcode=0x76)))
        for field in ('b', 'c', 'd', 'e', 'h', 'l'):
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, 'REGISTERS'):
                checker.completion(dict(record, **{field: 0x42}))
        with self.assertRaisesRegex(AssertionError, 'INSTRUCTION'):
            checker.completion(dict(record, pc_after=0x4a83))

    def test_locked_image_cannot_be_replaced(self):
        with self.assertRaisesRegex(ValueError, 'IMAGE_HASH'):
            mooneye.validate_image(ROOT, bytes(32768), '01:4a81 quit@serial_dump')
        with self.assertRaisesRegex(ValueError, 'IMAGE_HASH'):
            mooneye.validate_image(ROOT, bytes(32768), '01:4a81 quit@serial_dump', backend='wsl')

    def test_wsl_host_pin_and_changed_inputs(self):
        identity = {'backend': 'wsl', 'tools': {}, 'files': {}}
        lock = {'wsl_host': {'sha256': mooneye_wsl.identity_hash(identity)}}
        with patch.dict('os.environ', {'N2M_MOONEYE_BUILD_HOST': 'wsl'}), \
             patch.object(mooneye, 'pins', return_value=lock), \
             patch.object(mooneye_wsl, 'identity', return_value=identity):
            self.assertEqual(mooneye.tool_identity(ROOT, self.path), identity)
            mooneye.verify_tools(identity)
            with self.assertRaisesRegex(ValueError, 'HOST_CHANGED'):
                mooneye.verify_tools(dict(identity, files={'changed': '0'}))
            lock['wsl_host']['sha256'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'HOST_HASH'):
                mooneye.tool_identity(ROOT, self.path)

    def test_wsl_deadline_and_space_arguments(self):
        with patch.dict('os.environ', {'N2M_TEST_EXECUTION_DEADLINE': '1020'}), \
             patch.object(mooneye_wsl.time, 'time', return_value=1000), \
             patch.object(mooneye_wsl, 'linux_path', side_effect=lambda p: '/mnt/c/'+p.name):
            argv = mooneye_wsl.command(['/usr/bin/cmake', Path('with spaces')], Path('build dir'))
            self.assertEqual(argv, ['wsl.exe', '--cd', '/mnt/c/build dir', '--exec', 'timeout',
                                    '--kill-after=2', '15', '/usr/bin/cmake', '/mnt/c/with spaces'])
        with patch.dict('os.environ', {'N2M_TEST_EXECUTION_DEADLINE': '1004'}), \
             patch.object(mooneye_wsl.time, 'time', return_value=1000):
            with self.assertRaisesRegex(ValueError, 'BUILD_DEADLINE'):
                mooneye_wsl.timeout_seconds(110)

    def test_missing_and_unknown_build_host(self):
        with patch.dict('os.environ', {'N2M_MOONEYE_BUILD_HOST': 'other'}):
            with self.assertRaisesRegex(ValueError, 'BUILD_HOST'):
                mooneye.tool_identity(ROOT, self.path)
        with patch.object(mooneye_wsl.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'MISSING_TOOL'):
                mooneye_wsl.snapshot()

    def test_archive_escape_and_symlink_rejected(self):
        for index, entry in enumerate(('../escape', '/escape', 'link')):
            archive = self.path/f'{index}.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                info = zipfile.ZipInfo(entry)
                if entry == 'link':
                    info.external_attr = 0o120777 << 16
                output.writestr(info, 'data')
            with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, 'ARCHIVE_PATH'):
                mooneye.extract(archive, self.path/'out')
        self.assertFalse((self.path/'escape').exists())

    def test_cached_download_mismatch_is_not_redownloaded(self):
        path = self.path/'cache.zip'
        path.write_bytes(b'changed')
        with patch('urllib.request.urlopen') as opening:
            with self.assertRaisesRegex(ValueError, 'MOONEYE_HASH'):
                mooneye.download({'sha256': '0'*64}, path)
            opening.assert_not_called()

    def test_named_fixture_has_no_unknown_fallback(self):
        from sw.package import package
        image = package({'image': bytes([255])*32768, 'entry': 0x200}, 'ORIGINAL', 1)
        import hashlib
        record = preload.prepare(image, hashlib.sha256(image).hexdigest(), self.path)
        self.assertNotIn('fixture', record)
        (self.path/'program.gb').write_bytes(image)
        import json
        record['fixture'] = 'unreviewed'
        (self.path/'preload.json').write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'unknown preload fixture'):
            preload.verify(self.path)
