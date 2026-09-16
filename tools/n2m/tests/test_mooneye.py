"""Locked fixture boundaries; no network or simulator needed by these tests."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
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

    def test_named_selections_and_completion_offsets(self):
        known = mooneye.selections(ROOT)
        self.assertEqual(set(known), {'mooneye-reg-f', 'mooneye-rom-512kb'})
        reg_f, rom = known['mooneye-reg-f'], known['mooneye-rom-512kb']
        self.assertEqual((reg_f['profile'], reg_f['image_bytes'], reg_f['completion_bank'], reg_f['completion_address']),
                         ('dmg-direct-v1', 32768, 1, 0x4a81))
        self.assertEqual((rom['profile'], rom['image_bytes'], rom['completion_bank'], rom['completion_address'], rom['completion_opcode']),
                         ('dmg-mbc1-v1', 65536, 1, 0x4847, 0x40))
        self.assertEqual(mooneye.completion_offset(reg_f), 0x4a81)
        self.assertEqual(mooneye.completion_offset(rom), 0x4847)
        # Banks above 1 live above the switched window in the image file.
        self.assertEqual(mooneye.completion_offset(dict(completion_bank=2, completion_address=0x4010)), 0x8010)
        self.assertEqual(mooneye.completion_offset(dict(completion_bank=3, completion_address=0x7fff)), 0xffff)
        self.assertEqual(mooneye.PROFILE_HEADERS['dmg-mbc1-v1'], bytes([1, 1, 0]))

    def test_unknown_fixture_and_unpinned_host_are_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, 'MOONEYE_FIXTURE'):
            mooneye.validate_image(ROOT, bytes(65536), '', fixture='mooneye-bits-bank1')
        # The Windows hash of the MBC1 selection is unpinned; the Ubuntu host hash is pinned.
        with self.assertRaisesRegex(ValueError, 'MOONEYE_HOST_UNPINNED'):
            mooneye.validate_image(ROOT, bytes(65536), '', fixture='mooneye-rom-512kb')
        with self.assertRaisesRegex(ValueError, 'MOONEYE_IMAGE_HASH'):
            mooneye.validate_image(ROOT, bytes(65536), '', fixture='mooneye-rom-512kb', backend='wsl')
        with self.assertRaisesRegex(ValueError, 'MOONEYE_IMAGE_HASH'):
            mooneye.validate_image(ROOT, bytes(32768), '', fixture='mooneye-rom-512kb', backend='wsl')

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
             patch.object(mooneye_wsl, 'native', return_value=False), \
             patch.object(mooneye_wsl, 'linux_path', side_effect=lambda p: '/mnt/c/'+p.name):
            argv = mooneye_wsl.command(['/usr/bin/cmake', Path('with spaces')], Path('build dir'))
            self.assertEqual(argv, ['wsl.exe', '--cd', '/mnt/c/build dir', '--exec', 'timeout',
                                    '--kill-after=2', '15', '/usr/bin/cmake', '/mnt/c/with spaces'])
        with patch.dict('os.environ', {'N2M_TEST_EXECUTION_DEADLINE': '1004'}), \
             patch.object(mooneye_wsl.time, 'time', return_value=1000):
            with self.assertRaisesRegex(ValueError, 'BUILD_DEADLINE'):
                mooneye_wsl.timeout_seconds(110)

    def test_native_linux_host_runs_the_locked_tools_without_wsl_exe(self):
        identity = {'backend': 'wsl', 'tools': {}, 'files': {}}
        lock = {'wsl_host': {'sha256': mooneye_wsl.identity_hash(identity)}}
        with patch.object(mooneye_wsl, 'native', return_value=True), \
             patch.object(mooneye_wsl, 'snapshot', return_value=identity) as snapshot, \
             patch.object(mooneye_wsl.subprocess, 'check_output', side_effect=AssertionError('wsl.exe')):
            self.assertEqual(mooneye_wsl.identity(), identity)
            snapshot.assert_called_once()
            self.assertEqual(mooneye_wsl.linux_path(Path('/tmp/with space')), '/tmp/with space')
            argv = mooneye_wsl.command(['/usr/bin/cmake', Path('with spaces')], Path('build dir'))
            self.assertEqual(argv, ['timeout', '--kill-after=2', '110', '/usr/bin/cmake', 'with spaces'])
            # On Linux the locked Ubuntu host is the default backend and no installation is needed.
            with patch.dict('os.environ', {}, clear=False), patch.object(mooneye.os, 'name', 'posix'), \
                 patch.object(mooneye, 'pins', return_value=lock):
                mooneye.os.environ.pop('N2M_MOONEYE_BUILD_HOST', None)
                self.assertEqual(mooneye.tool_identity(ROOT), identity)
        with patch.dict('os.environ', {'N2M_MOONEYE_BUILD_HOST': 'windows'}):
            with self.assertRaisesRegex(ValueError, 'requires the Questa installation'):
                mooneye.tool_identity(ROOT)

    def test_missing_and_unknown_build_host(self):
        with patch.dict('os.environ', {'N2M_MOONEYE_BUILD_HOST': 'other'}):
            with self.assertRaisesRegex(ValueError, 'BUILD_HOST'):
                mooneye.tool_identity(ROOT, self.path)
        with patch.object(mooneye_wsl.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'MISSING_TOOL'):
                mooneye_wsl.snapshot()

    def test_linux_timeout_retains_raw_exit_and_timeout_status(self):
        identity = {'backend': 'wsl', 'tools': {name: '/usr/bin/'+name for name in ('cmake', 'make', 'gcc', 'ar')}}
        with patch.object(mooneye, 'verify_tools'), patch.object(mooneye, 'download'), \
             patch.object(mooneye, 'extract'), patch.object(mooneye, 'checked'), \
             patch.object(mooneye.shutil, 'copyfile'), \
             patch.object(mooneye_wsl, 'command', side_effect=lambda argv, cwd: argv), \
             patch.object(mooneye.subprocess, 'run', return_value=Mock(stdout='timeout', returncode=124)):
            with self.assertRaisesRegex(ValueError, 'MOONEYE_BUILD_TIMEOUT mooneye-configure'):
                mooneye.prepare(ROOT, self.path, identity)
        record = json.loads((self.path/'mooneye-build-commands.json').read_text())
        self.assertEqual(record[0]['exit_code'], 124)
        self.assertTrue(record[0]['timed_out'])

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
