"""Library packing, catalogue layout, verification and refusal against the fake endpoint."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m.cli import main
from n2m.doctor import select_uart
from n2m.host import library
from n2m.host.client import Client
from n2m.host.transport import session
from n2m.interface_codec import unpack_record
from n2m.records import atomic_json, file_hash
from sw.package import package
from test_host import DEVICE, ROOT, Endpoint


def fixture_image(title, seed):
    image = bytearray((index * seed + index // 256) % 256 for index in range(32768))
    image[256:336] = bytes([255]) * 80
    return package({'image': image, 'entry': 512}, title, 1)


def mbc1_image(title, seed):
    """A 64 KiB image with the title in its header; the packager is not involved (its MBC1 profile is the toolchain's)."""
    image = bytearray((index * seed + index // 512) % 256 for index in range(65536))
    image[0x134:0x144] = title.encode('ascii').ljust(16, b'\0')
    return bytes(image)


MBC1_PROFILE = {'dmg-mbc1-v1': abi.PROFILE_MBC1_ID}


class CorruptingEndpoint(Endpoint):
    """Stores every line faithfully except one byte at ``corrupt`` (device address)."""
    def __init__(self, corrupt):
        super().__init__()
        self.corrupt = corrupt

    def write(self, packet):
        result = super().write(packet)
        name, payload, _seq = self.requests[-1]
        if name == 'SDRAM_WRITE':
            address = unpack_record('sdram_write', payload[:4])['address']
            if address <= self.corrupt < address + len(payload) - 4:
                line_address = self.corrupt - (self.corrupt - address) % 16
                line = bytearray(self.sdram[line_address])
                line[self.corrupt - line_address] ^= 0x80
                self.sdram[line_address] = bytes(line)
        return result


class LoaderEndpoint(Endpoint):
    """Models the loader's menu return: LIBRARY_CONTROL = 1 swaps in the menu.

    The swap reports ``copy_busy`` and STATE LOADING for ``busy_reads`` status
    reads, then result OK with the loader profile live. The console keeps its
    prior host state (MAS_loader_profile.md select register step 6): a host
    pause survives the swap until RUN, so only a RUNNING console resumes.
    A stuck endpoint (``busy_reads`` None) never clears ``copy_busy``.
    """
    def __init__(self, busy_reads=2, result=abi.LIBRARY_RESULT_OK):
        super().__init__()
        self.busy_reads = busy_reads
        self.swap_result = result
        self.swapping = False
        self.result_byte = abi.LIBRARY_RESULT_NONE
        self.status_reads = 0
        self.state_before_swap = self.state

    def host_write(self, address, value):
        if address == abi.HOST_REG_LIBRARY_CONTROL and value == abi.LIBRARY_CONTROL_RETURN:
            self.swapping, self.status_reads = True, 0
            self.state_before_swap = self.state
            self.state, self.valid = abi.STATE_LOADING, 0

    def library_status(self):
        if not self.swapping:
            return (self.result_byte << 8) | 0x00FF0000 | abi.LIBRARY_STATUS_SDRAM_READY
        self.status_reads += 1
        if self.busy_reads is None or self.status_reads <= self.busy_reads:
            return 0x00FF0000 | abi.LIBRARY_STATUS_COPY_BUSY | abi.LIBRARY_STATUS_SDRAM_READY
        self.swapping, self.result_byte = False, self.swap_result
        if self.swap_result == abi.LIBRARY_RESULT_OK:
            self.state, self.valid, self.profile = self.state_before_swap, 1, abi.PROFILE_LOADER_ID
        return (self.result_byte << 8) | (abi.LIBRARY_MENU_INDEX << 16) | abi.LIBRARY_STATUS_SDRAM_READY | abi.LIBRARY_STATUS_WINDOW_READY


class LibraryTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'workdir/builds/host-library-unit'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='lib ', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.tag = 'host-library-' + self.folder.name.rsplit(' ', 1)[-1].lower().replace('_', '-')

    def manifest(self, name, title, seed):
        folder = self.folder / f'sw/build/{name}/runs/{seed:012x}'
        folder.mkdir(parents=True)
        rom = folder / 'image.gb'
        rom.write_bytes(fixture_image(title, seed))
        relative = rom.relative_to(ROOT).as_posix()
        record = {'status': 'PASS', 'attempt': folder.name, 'profile': abi.PROFILE_NAME, 'entry': 512,
                  'rom': relative, 'artifacts': {relative: file_hash(rom)},
                  'inputs': {name: file_hash(ROOT / name) for name in
                             ('cfg/interfaces.json', 'tools/n2m/generated_interfaces.py')}}
        path = folder / 'result.json'
        atomic_json(path, record)
        return path

    def fake_session(self, endpoint):
        def opened(folder, args, state_root):
            return session(folder, args, self.folder / 'state',
                           discover=lambda folder, args: select_uart([DEVICE], args), opener=lambda port: endpoint)
        return opened

    def test_catalogue_entry_and_table_layout(self):
        image = fixture_image('LAYOUT FIXTURE', 3)
        entry = library.image_entry(image, abi.PROFILE_DIRECT_ID)
        raw = library.pack_entry(entry)
        crc = zlib.crc32(image)
        self.assertEqual(raw[:8], bytes([1, abi.PROFILE_DIRECT_ID, 0x00, 0x80]) + crc.to_bytes(4, 'little'))
        self.assertEqual(raw[8:24], b'LAYOUT FIXTURE\0\0')
        self.assertEqual(raw[24:], bytes(8))
        self.assertEqual(library.pack_entry({'valid': 1, 'profile': 1, 'length': 32768, 'crc32': 0x11223344,
                                             'title': b'ABC'}),
                         bytes.fromhex('01 01 00 80 44 33 22 11') + b'ABC' + bytes(13) + bytes(8))
        table = library.build_catalogue({0: entry, 16: entry})
        self.assertEqual(len(table), 1024)
        self.assertEqual(table[0:32], raw)
        self.assertEqual(table[32:512], bytes(480))
        self.assertEqual(table[512:544], raw)
        self.assertEqual(table[544:], bytes(480))
        rows = library.parse_catalogue(table)
        self.assertEqual((rows[0]['valid'], rows[0]['crc32'], rows[16]['title']), (1, crc, b'LAYOUT FIXTURE\0\0'))
        self.assertEqual(rows[5], {**library.EMPTY_ENTRY, 'reserved_zero': True})
        self.assertEqual((library.slot_address(0), library.slot_address(15), library.slot_address(16)),
                         (0, 0x78000, 0x80000))
        self.assertEqual(library.CATALOGUE_ADDRESS, 0x88000)
        for bad in (-1, abi.LIBRARY_CATALOGUE_ENTRIES, '0'):
            with self.assertRaises(ValueError):
                library.slot_address(bad)
        with self.assertRaises(ValueError):
            library.image_entry(image[:-1], 1)
        with self.assertRaises(ValueError):
            library.profile_id('dmg-mbc1')

    def test_a_64_kib_mbc1_entry_carries_its_length_in_the_high_byte_and_fills_two_slots(self):
        image = mbc1_image('BANKED GAME', 4)
        entry = library.image_entry(image, abi.PROFILE_MBC1_ID)
        self.assertEqual((entry['length'], entry['crc32'], entry['title']), (65536, zlib.crc32(image), b'BANKED GAME' + bytes(5)))
        raw = library.pack_entry(entry)
        # Bytes 2-3 hold length bits 15:0 (zero for 65536), byte 24 bits 23:16; the rest stays reserved zero.
        self.assertEqual(raw[:4], bytes([1, abi.PROFILE_MBC1_ID, 0x00, 0x00]))
        self.assertEqual(raw[abi.CATALOGUE_ENTRY_LENGTH_HIGH_OFFSET], 1)
        self.assertEqual(raw[abi.CATALOGUE_ENTRY_RESERVED_OFFSET:], bytes(7))
        self.assertEqual(library.unpack_entry(raw)['length'], 65536)
        # A 32 KiB entry packs exactly as before: length_high is the old reserved zero.
        small = library.pack_entry(library.image_entry(fixture_image('SMALL', 3), abi.PROFILE_DIRECT_ID))
        self.assertEqual(small[abi.CATALOGUE_ENTRY_LENGTH_HIGH_OFFSET:], bytes(8))
        self.assertEqual(library.unpack_entry(small)['length'], abi.LIBRARY_SLOT_BYTES)
        # Each profile takes exactly its own length.
        for bad_image, profile in ((image, abi.PROFILE_DIRECT_ID), (image, abi.PROFILE_LOADER_ID),
                                   (fixture_image('X', 3), abi.PROFILE_MBC1_ID), (image[:-1], abi.PROFILE_MBC1_ID)):
            with self.assertRaisesRegex(ValueError, 'must be exactly'):
                library.image_entry(bad_image, profile)
        with self.assertRaisesRegex(ValueError, 'profile ID 9'):
            library.image_entry(image, 9)
        self.assertEqual((library.image_slots(32768), library.image_slots(65536)), (1, 2))
        self.assertEqual(list(library.slot_range(14, 65536)), [14, 15])
        self.assertEqual(list(library.slot_range(16, 32768)), [16])
        for index, length in ((15, 65536), (16, 65536)):
            with self.assertRaisesRegex(ValueError, 'would spill past'):
                library.slot_range(index, length)

    def test_load_places_a_64_kib_image_in_two_slots(self):
        games = [(fixture_image('GAME 0', 3), abi.PROFILE_NAME), (mbc1_image('BANKED GAME', 4), 'dmg-mbc1-v1'),
                 (fixture_image('GAME 3', 5), abi.PROFILE_NAME)]
        menu = (fixture_image('MENU', 101), abi.PROFILE_NAME)
        endpoint = Endpoint()
        with patch.dict(library.PROFILE_IDS, MBC1_PROFILE):
            result = library.load_library(Client(endpoint), games, menu)
        self.assertEqual((result['status'], result['images']), ('PASS', 4))
        self.assertEqual([(row['index'], row['length']) for row in result['slots']], [(0, 32768), (1, 65536), (3, 32768), (16, 32768)])
        stored = b''.join(endpoint.sdram[0x8000 + line * 16] for line in range(4096))
        self.assertEqual(stored, games[1][0])
        self.assertEqual(b''.join(endpoint.sdram[0x18000 + line * 16] for line in range(2048)), games[2][0])
        rows = library.parse_catalogue(b''.join(endpoint.sdram[0x88000 + line * 16] for line in range(64)))
        self.assertEqual([row['valid'] for row in rows], [1, 1, 0, 1] + [0] * 12 + [1])
        self.assertEqual((rows[1]['profile'], rows[1]['length'], rows[1]['crc32']), (abi.PROFILE_MBC1_ID, 65536, zlib.crc32(games[1][0])))
        self.assertEqual(rows[2], {**library.EMPTY_ENTRY, 'reserved_zero': True})
        # Sixteen slots in total: eight 64 KiB images fit, a ninth image does not, and a 64 KiB image cannot start in slot 15.
        eight = [(mbc1_image(f'BANK {i}', 6 + i), 'dmg-mbc1-v1') for i in range(8)]
        with patch.dict(library.PROFILE_IDS, MBC1_PROFILE):
            self.assertEqual(sorted(library.plan_slots(eight)), list(range(0, 16, 2)))
            with self.assertRaisesRegex(ValueError, 'at most 16 slots'):
                library.plan_slots(eight + [games[0]])
            with self.assertRaisesRegex(ValueError, 'would spill past slot 15'):
                library.plan_slots(eight[:7] + [games[0], eight[7]])

    def test_blank_header_title_takes_the_fallback_and_a_named_header_keeps_its_own(self):
        blank = bytearray(fixture_image('X', 5))
        blank[0x134:0x144] = bytes(16)
        entry = library.image_entry(bytes(blank), abi.PROFILE_DIRECT_ID, b'PINNED TITLE')
        self.assertEqual(entry['title'], b'PINNED TITLE\0\0\0\0')
        self.assertEqual(entry['crc32'], zlib.crc32(bytes(blank)))
        self.assertEqual(library.image_entry(bytes(blank), abi.PROFILE_DIRECT_ID)['title'], bytes(16))
        named = fixture_image('OWN TITLE', 5)
        self.assertEqual(library.image_entry(named, abi.PROFILE_DIRECT_ID, b'PINNED TITLE')['title'], b'OWN TITLE'.ljust(16, b'\0'))
        with self.assertRaisesRegex(ValueError, r'1\.\.16 bytes'):
            library.image_entry(bytes(blank), abi.PROFILE_DIRECT_ID, b'')

    def test_layout_values_come_from_the_generated_table(self):
        self.assertEqual((library.SLOT_BYTES, library.GAME_SLOTS, library.MENU_INDEX, library.IMAGE_COUNT,
                          library.CATALOGUE_ADDRESS, library.ENTRY_BYTES, library.VALID),
                         (abi.LIBRARY_SLOT_BYTES, abi.LIBRARY_SLOTS, abi.LIBRARY_MENU_INDEX, abi.LIBRARY_CATALOGUE_ENTRIES,
                          abi.LIBRARY_CATALOGUE_ADDRESS, abi.LIBRARY_ENTRY_BYTES, abi.LIBRARY_CATALOGUE_VALID))
        self.assertEqual((library.ENTRY_BYTES, library.TITLE_BYTES), (abi.CATALOGUE_ENTRY_BYTES, 16))
        self.assertEqual(library.IMAGE_COUNT, library.GAME_SLOTS + 1)
        self.assertEqual(library.CATALOGUE_ADDRESS, abi.LIBRARY_MENU_INDEX * abi.LIBRARY_SLOT_BYTES + abi.LIBRARY_SLOT_BYTES)
        self.assertEqual(library.CATALOGUE_ADDRESS % abi.LIBRARY_WINDOW_BYTES, 0)
        # The module names no library number of its own: the generated table owns them.
        source = (ROOT / 'tools/n2m/host/library.py').read_text()
        self.assertEqual(re.findall(r'\b(?:32768|0x8000|0x80000|0x88000|557056|abi\.PROFILE_ROM_BYTES)\b', source), [])
        # RETURN_STATUS_READS bounds `--wait`; it is not a layout number.
        self.assertEqual(re.findall(r'^[A-Z_]+ = \d+$', source, re.MULTILINE),
                         ['EMPTY = 0', 'CATALOGUE_BYTES = 1024', 'RETURN_STATUS_READS = 64'])
        # Entry field offsets follow the generated record.
        image = fixture_image('OFFSETS', 9)
        raw = library.pack_entry(library.image_entry(image, abi.PROFILE_LOADER_ID))
        self.assertEqual(raw[abi.CATALOGUE_ENTRY_VALID_OFFSET], abi.LIBRARY_CATALOGUE_VALID)
        self.assertEqual(raw[abi.CATALOGUE_ENTRY_PROFILE_OFFSET], abi.PROFILE_LOADER_ID)
        self.assertEqual(int.from_bytes(raw[abi.CATALOGUE_ENTRY_LENGTH_OFFSET:abi.CATALOGUE_ENTRY_CRC32_OFFSET], 'little'),
                         abi.LIBRARY_SLOT_BYTES)
        self.assertEqual(int.from_bytes(raw[abi.CATALOGUE_ENTRY_CRC32_OFFSET:abi.CATALOGUE_ENTRY_TITLE_LOW_OFFSET], 'little'),
                         zlib.crc32(image))
        self.assertEqual(raw[abi.CATALOGUE_ENTRY_TITLE_LOW_OFFSET:abi.CATALOGUE_ENTRY_LENGTH_HIGH_OFFSET], b'OFFSETS' + bytes(9))
        self.assertEqual(raw[abi.CATALOGUE_ENTRY_LENGTH_HIGH_OFFSET:], bytes(8))
        self.assertEqual(library.unpack_entry(raw)['profile'], abi.PROFILE_LOADER_ID)

    def test_menu_entry_profile_follows_the_package_profile(self):
        self.assertEqual(library.profile_id(abi.PROFILE_NAME), abi.PROFILE_DIRECT_ID)
        self.assertEqual(library.profile_id(library.LOADER_PROFILE_NAME), abi.PROFILE_LOADER_ID)
        self.assertEqual(library.PROFILE_IDS, {'dmg-direct-v1': 1, 'dmg-loader-v1': 2})
        game = (fixture_image('GAME', 21), abi.PROFILE_NAME)
        for name, expected in ((library.LOADER_PROFILE_NAME, abi.PROFILE_LOADER_ID), (abi.PROFILE_NAME, abi.PROFILE_DIRECT_ID)):
            with self.subTest(profile=name):
                endpoint = Endpoint()
                result = library.load_library(Client(endpoint), [game], (fixture_image('MENU', 23), name))
                self.assertEqual(result['status'], 'PASS')
                self.assertEqual([row['profile'] for row in result['slots']], [abi.PROFILE_DIRECT_ID, expected])
                catalogue = b''.join(endpoint.sdram[abi.LIBRARY_CATALOGUE_ADDRESS + line * 16] for line in range(64))
                rows = library.parse_catalogue(catalogue)
                self.assertEqual(rows[abi.LIBRARY_MENU_INDEX]['profile'], expected)
                self.assertEqual(rows[0]['profile'], abi.PROFILE_DIRECT_ID)
                self.assertEqual(rows[abi.LIBRARY_MENU_INDEX]['valid'], abi.LIBRARY_CATALOGUE_VALID)

    def test_load_writes_slots_menu_and_catalogue_then_verifies(self):
        images = [(fixture_image(f'GAME {i}', 3 + 2 * i), abi.PROFILE_NAME) for i in range(3)]
        menu = (fixture_image('MENU', 101), abi.PROFILE_NAME)
        endpoint = Endpoint()
        events = []
        result = library.load_library(Client(endpoint), images, menu, progress=events.append)
        self.assertEqual((result['status'], result['mismatch_count'], result['images']), ('PASS', 0, 4))
        names = [name for name, _p, _s in endpoint.requests if name.startswith('SDRAM')]
        # Fifteen lines per write command: ceil(2048/15) per image, ceil(64/15) for the catalogue.
        writes = 4 * 137 + 5
        self.assertEqual(names[:writes], ['SDRAM_WRITE'] * writes)
        self.assertEqual(set(names[writes:]), {'SDRAM_READ'})
        for index, (image, _profile) in enumerate(images + [menu]):
            base = 0x80000 if index == 3 else index * 0x8000
            stored = b''.join(endpoint.sdram[base + line * 16] for line in range(2048))
            self.assertEqual(stored, image)
        catalogue = b''.join(endpoint.sdram[0x88000 + line * 16] for line in range(64))
        rows = library.parse_catalogue(catalogue)
        self.assertEqual([row['valid'] for row in rows], [1, 1, 1] + [0] * 13 + [1])
        self.assertEqual(rows[16]['crc32'], zlib.crc32(menu[0]))
        self.assertEqual(rows[1]['title'], b'GAME 1' + bytes(10))
        self.assertEqual([row['name'] for row in result['slots']], ['slot 0', 'slot 1', 'slot 2', 'menu'])
        self.assertTrue(all(row['crc32_match'] and row['status'] == 'PASS' for row in result['slots']))
        self.assertEqual(result['slots'][2]['crc32'], f"{zlib.crc32(images[2][0]):08x}")
        self.assertEqual(result['catalogue'], {'address': 0x88000, 'bytes': 1024, 'status': 'PASS', 'first_mismatch': None})
        self.assertEqual(events[0], {'stage': 'write', 'name': 'slot 0', 'completed': 0, 'total': 2048})
        self.assertIn({'stage': 'read', 'name': 'catalogue', 'completed': 64, 'total': 64}, events)
        text = library.format_table(result['slots'], verified=True)
        self.assertIn('index  name    valid  profile  length  crc32     title   readback  status', text)
        self.assertIn('menu', text.splitlines()[-1])
        with self.assertRaises(ValueError):
            library.load_library(Client(Endpoint()), [], None)
        with self.assertRaises(ValueError):
            library.load_library(Client(Endpoint()), images * 6, None)

    def test_corrupted_slot_and_wrong_crc_are_named_and_fail(self):
        images = [(fixture_image(f'GAME {i}', 5 + i), abi.PROFILE_NAME) for i in range(2)]
        result = library.load_library(Client(CorruptingEndpoint(0x8000 + 0x1234)), images, None)
        self.assertEqual((result['status'], result['mismatches']), ('FAIL', ['slot 1 (GAME 1)']))
        self.assertEqual((result['slots'][1]['status'], result['slots'][1]['first_mismatch'], result['slots'][1]['crc32_match']),
                         ('FAIL', 0x1234, False))
        self.assertEqual((result['slots'][0]['status'], result['catalogue']['status']), ('PASS', 'PASS'))
        # A wrong crc32 in the stored catalogue: the copy engine would refuse the slot.
        result = library.load_library(Client(CorruptingEndpoint(0x88000 + 32 + 4)), images, None)
        self.assertEqual((result['status'], result['mismatches']), ('FAIL', ['catalogue']))
        self.assertEqual(result['catalogue']['first_mismatch'], 36)

    def test_cli_load_and_status_through_fake_session(self):
        manifests = [str(self.manifest(f'game{i}', f'GAME {i}', 7 + i)) for i in range(2)]
        menu = str(self.manifest('menu', 'MENU', 99))
        endpoint = Endpoint()
        with patch('n2m.host.command.session', self.fake_session(endpoint)), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'library', 'load', *manifests, '--menu', menu,
                                   '--uart-port', 'COM92', '--tag', self.tag, '--json'], ROOT), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual((report['status'], report['action'], report['result']['status']), ('PASS', 'library-load', 'PASS'))
        self.assertEqual(set(report['packages']), {'slot 0', 'slot 1', 'menu'})
        self.assertEqual(report['packages']['menu']['rom_sha256'], file_hash(Path(menu).parent / 'image.gb'))
        with patch('n2m.host.command.session', self.fake_session(endpoint)), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'library', 'status', '--uart-port', 'COM92', '--tag', self.tag, '--json'], ROOT), 0)
        report = json.loads(stdout.getvalue())
        rows = report['result']['catalogue']
        self.assertEqual(len(rows), 17)
        self.assertEqual([(row['name'], row['valid'], row['title']) for row in rows if row['valid']],
                         [('slot 0', 1, 'GAME 0'), ('slot 1', 1, 'GAME 1'), ('menu', 1, 'MENU')])
        self.assertEqual(rows[1]['crc32'], f"{zlib.crc32(fixture_image('GAME 1', 8)):08x}")
        self.assertEqual(report['result']['library_status'],
                         {'word': 0x00FF0020, 'a000': 0x20, 'a002': 0, 'a003': 0xFF, 'bank': 0,
                          'flags': ['sdram_ready'], 'result': 'NONE'})
        with patch('n2m.host.command.session', self.fake_session(endpoint)), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'library', 'status', '--uart-port', 'COM92', '--tag', self.tag], ROOT), 0)
        self.assertIn('16     menu     1      1        32768', stdout.getvalue())
        # A corrupted slot fails the command, names the slot and keeps the table.
        corrupt = CorruptingEndpoint(0x100)
        with patch('n2m.host.command.session', self.fake_session(corrupt)), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'library', 'load', *manifests, '--uart-port', 'COM92', '--tag', self.tag, '--json'], ROOT), 1)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report['error'], 'library readback mismatch: slot 0 (GAME 0)')
        self.assertEqual(report['result']['slots'][0]['status'], 'FAIL')
        self.assertEqual(report['result']['slots'][1]['status'], 'PASS')

    def test_cli_refuses_foreign_images_before_the_port_opens(self):
        good = str(self.manifest('game', 'GAME', 11))
        loose = self.folder / 'loose.gb'
        loose.write_bytes(fixture_image('LOOSE', 12))
        stale = self.manifest('stale', 'STALE', 13)
        record = json.loads(stale.read_text())
        atomic_json(stale, {**record, 'profile': 'dmg-mbc1'})
        for argv in ([str(loose)], [good, str(loose)], [good, '--menu', str(loose)], [str(stale)], [good] * 17):
            with self.subTest(argv=argv), patch('n2m.host.command.session') as opener, redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(['host', 'library', 'load', *argv, '--uart-port', 'COM92', '--tag', self.tag, '--json'], ROOT), 1)
                self.assertEqual(json.loads(stdout.getvalue())['status'], 'FAIL')
            opener.assert_not_called()

    def test_titles_print_without_control_bytes(self):
        self.assertEqual(library.title_text(b'GAME \x1b[2J\x07\xff1\0\0'), 'GAME ?[2J??1')
        raw = library.pack_entry({'valid': 1, 'profile': 1, 'length': 32768, 'crc32': 0, 'title': b'\x1b]0;x\x07'})
        row = library.describe(3, library.unpack_entry(raw))
        self.assertEqual(row['title'], '?]0;x?')
        self.assertNotIn('\x1b', library.format_table([row]))

    def test_library_status_word_fields(self):
        self.assertEqual(library.decode_library_status(0x2A030201),
                         {'word': 0x2A030201, 'a000': 0x01, 'a002': 0x02, 'a003': 0x03, 'bank': 0x2A,
                          'flags': [], 'result': 'INVALID_SLOT'})
        busy = abi.LIBRARY_STATUS_COPY_BUSY | abi.LIBRARY_STATUS_SDRAM_READY | abi.LIBRARY_STATUS_KEY1_PENDING
        decoded = library.decode_library_status((abi.LIBRARY_RESULT_CRC_MISMATCH << 8) | busy | (63 << 24))
        self.assertEqual((decoded['flags'], decoded['result'], decoded['bank']),
                         (['copy_busy', 'sdram_ready', 'key1_pending'], 'CRC_MISMATCH', 63))
        self.assertEqual(library.decode_library_status(0x0700)['result'], 'UNKNOWN')

    def test_return_sends_the_whitelisted_control_write_and_reports_the_swap(self):
        endpoint = LoaderEndpoint(busy_reads=2)
        endpoint.state, endpoint.valid, endpoint.profile = abi.STATE_RUNNING, 1, abi.PROFILE_DIRECT_ID
        result = library.return_to_menu(Client(endpoint), wait=True)
        # Exactly the generated LIBRARY_CONTROL write with the RETURN value; the whitelist masks the rest.
        self.assertEqual(endpoint.host_writes, [(abi.HOST_REG_LIBRARY_CONTROL, abi.LIBRARY_CONTROL_RETURN)])
        self.assertEqual(abi.HOST_REG_LIBRARY_CONTROL, 0x100A0)
        self.assertEqual(abi.HOST_WRITE_MASK_LIBRARY_CONTROL, abi.LIBRARY_CONTROL_RETURN)
        names = [name for name, _p, _s in endpoint.requests]
        self.assertEqual(names, ['READ_HOST'] * 3 + ['WRITE_HOST'] + ['READ_HOST'] * 3 + ['READ_HOST'] * 3)
        self.assertEqual((result['before']['state_name'], result['before']['PROFILE']), ('RUNNING', abi.PROFILE_DIRECT_ID))
        self.assertEqual((result['status_reads'], result['settled']), (3, True))
        self.assertEqual((result['library_status']['result'], result['library_status']['flags'], result['library_status']['a003']),
                         ('OK', ['window_ready', 'sdram_ready'], abi.LIBRARY_MENU_INDEX))
        self.assertEqual(result['endpoint'], {'STATE': abi.STATE_RUNNING, 'state_name': 'RUNNING',
                                              'PROFILE': abi.PROFILE_LOADER_ID, 'IMAGE_VALID': 1})
        self.assertIn('dot', result['control'])
        text = library.format_return(result)
        self.assertIn('result OK flags window_ready,sdram_ready', text)
        self.assertIn('endpoint RUNNING profile 2 image_valid 1 after 3 status read(s)', text)
        # Without --wait one status read is taken and a busy swap is reported, not failed.
        endpoint = LoaderEndpoint(busy_reads=2)
        result = library.return_to_menu(Client(endpoint))
        self.assertEqual((result['status_reads'], result['settled'], result['library_status']['flags']),
                         (1, False, ['copy_busy', 'sdram_ready']))
        self.assertEqual(result['endpoint']['state_name'], 'LOADING')

    def test_return_is_refused_while_loading_and_a_bad_state_reply_is_named(self):
        endpoint = LoaderEndpoint()
        endpoint.state = abi.STATE_LOADING
        with self.assertRaisesRegex(ValueError, 'refused: endpoint is LOADING'):
            library.return_to_menu(Client(endpoint))
        self.assertEqual([name for name, _p, _s in endpoint.requests], ['READ_HOST'] * 3)
        self.assertEqual(endpoint.host_writes, [])
        # The endpoint enters LOADING between the state read and the write: the BAD_STATE reply is named.
        racing = LoaderEndpoint()
        original = racing.write
        def write(packet):
            if len(racing.requests) == 3:
                racing.state = abi.STATE_LOADING
            return original(packet)
        racing.write = write
        with self.assertRaisesRegex(ValueError, 'rejected by the endpoint: BAD_STATE'):
            library.return_to_menu(Client(racing))
        self.assertEqual([name for name, _p, _s in racing.requests][-1], 'WRITE_HOST')
        self.assertEqual(racing.host_writes, [])
        # A swap that never clears copy_busy fails --wait after the bounded number of reads.
        stuck = LoaderEndpoint(busy_reads=None)
        with self.assertRaisesRegex(ValueError, f'did not settle within {library.RETURN_STATUS_READS} status reads'):
            library.return_to_menu(Client(stuck), wait=True)
        status_reads = [payload for name, payload, _s in stuck.requests
                        if name == 'READ_HOST' and unpack_record('read_host', payload)['address'] == abi.HOST_REG_LIBRARY_STATUS]
        self.assertEqual(len(status_reads), library.RETURN_STATUS_READS)

    def test_cli_return_through_fake_session(self):
        endpoint = LoaderEndpoint(busy_reads=1)
        with patch('n2m.host.command.session', self.fake_session(endpoint)), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'library', 'return', '--wait', '--uart-port', 'COM92', '--tag', self.tag, '--json'], ROOT), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual((report['status'], report['action']), ('PASS', 'library-return'))
        self.assertEqual((report['result']['settled'], report['result']['status_reads']), (True, 2))
        self.assertEqual(report['result']['library_status']['result'], 'OK')
        # A host-paused console stays PAUSED through a healthy return (contract step 6); it is not a failed return.
        self.assertEqual((report['result']['before']['state_name'], report['result']['endpoint']['state_name']), ('PAUSED', 'PAUSED'))
        self.assertEqual((report['result']['endpoint']['PROFILE'], report['result']['endpoint']['IMAGE_VALID']), (abi.PROFILE_LOADER_ID, 1))
        self.assertEqual(endpoint.host_writes, [(abi.HOST_REG_LIBRARY_CONTROL, abi.LIBRARY_CONTROL_RETURN)])
        running = LoaderEndpoint(busy_reads=0)
        running.state = abi.STATE_RUNNING
        with patch('n2m.host.command.session', self.fake_session(running)), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'library', 'return', '--uart-port', 'COM92', '--tag', self.tag], ROOT), 0)
        self.assertIn('library return: result OK flags window_ready,sdram_ready bank 0; endpoint RUNNING profile 2 image_valid 1',
                      stdout.getvalue())
        loading = LoaderEndpoint()
        loading.state = abi.STATE_LOADING
        with patch('n2m.host.command.session', self.fake_session(loading)), redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['host', 'library', 'return', '--uart-port', 'COM92', '--tag', self.tag, '--json'], ROOT), 1)
        report = json.loads(stdout.getvalue())
        self.assertEqual((report['status'], report['error']),
                         ('FAIL', 'library return refused: endpoint is LOADING, not PAUSED or RUNNING'))
        self.assertEqual(loading.host_writes, [])


if __name__ == '__main__':
    unittest.main()
