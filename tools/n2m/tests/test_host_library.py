"""Library packing, catalogue layout, verification and refusal against the fake endpoint."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
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


class CorruptingEndpoint(Endpoint):
    """Stores every line faithfully except one byte at ``corrupt`` (device address)."""
    def __init__(self, corrupt):
        super().__init__()
        self.corrupt = corrupt

    def write(self, packet):
        result = super().write(packet)
        name, payload, _seq = self.requests[-1]
        if name == 'SDRAM_WRITE':
            address = unpack_record('sdram_write', payload)['address']
            if address <= self.corrupt < address + 16:
                line = bytearray(self.sdram[address])
                line[self.corrupt - address] ^= 0x80
                self.sdram[address] = bytes(line)
        return result


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
        for bad in (-1, 17, '0'):
            with self.assertRaises(ValueError):
                library.slot_address(bad)
        with self.assertRaises(ValueError):
            library.image_entry(image[:-1], 1)
        with self.assertRaises(ValueError):
            library.profile_id('dmg-mbc1')

    def test_load_writes_slots_menu_and_catalogue_then_verifies(self):
        images = [(fixture_image(f'GAME {i}', 3 + 2 * i), abi.PROFILE_NAME) for i in range(3)]
        menu = (fixture_image('MENU', 101), abi.PROFILE_NAME)
        endpoint = Endpoint()
        events = []
        result = library.load_library(Client(endpoint), images, menu, progress=events.append)
        self.assertEqual((result['status'], result['mismatch_count'], result['images']), ('PASS', 0, 4))
        names = [name for name, _p, _s in endpoint.requests if name.startswith('SDRAM')]
        writes = 4 * 2048 + 64
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
        self.assertNotIn('library_status', report['result'])
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

    def test_library_status_word_fields(self):
        self.assertEqual(library.decode_library_status(0x2A030201),
                         {'word': 0x2A030201, 'a000': 0x01, 'a002': 0x02, 'a003': 0x03, 'bank': 0x2A})


if __name__ == '__main__':
    unittest.main()
