"""Flash library image assembly against the contract's flash words; registry validation; builder records."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import flash_library, fpga, fpga_flash, generated_interfaces as abi
from n2m.host import library
from n2m.records import file_hash
from sw.package import package

ROOT = Path(__file__).resolve().parents[3]
SLOT_WORDS = library.SLOT_BYTES // 4
CATALOGUE_WORD = 0x22800
DATA_BASE = 0x00800


def fixture_image(title, seed):
    image = bytearray((index * seed + index // 256) % 256 for index in range(library.SLOT_BYTES))
    image[256:336] = bytes([255]) * 80
    return package({'image': image, 'entry': 512}, title, 1)


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.images = {0: (fixture_image('FIRST GAME', 3), abi.PROFILE_NAME),
                       5: (fixture_image('SIXTH GAME', 7), abi.PROFILE_NAME),
                       library.MENU_INDEX: (fixture_image('GAME MENU', 11), library.LOADER_PROFILE_NAME)}
        self.assembled = flash_library.assemble(self.images)
        self.words = self.assembled['words']

    def test_contract_word_mapping(self):
        self.assertEqual(flash_library.flash_word(0), DATA_BASE)
        self.assertEqual(flash_library.flash_word(library.CATALOGUE_ADDRESS), CATALOGUE_WORD)
        self.assertEqual(flash_library.avalon_word(library.CATALOGUE_ADDRESS), CATALOGUE_WORD - DATA_BASE)
        for index in range(library.IMAGE_COUNT):
            self.assertEqual(flash_library.flash_word(library.slot_address(index)), DATA_BASE + index * SLOT_WORDS)
        self.assertEqual(flash_library.USER_WORDS, 0x2E7FF - DATA_BASE + 1)

    def test_slot_words_are_little_endian_at_the_contract_addresses(self):
        for index, (image, _profile) in self.images.items():
            base = index * SLOT_WORDS
            self.assertEqual(self.words[base], int.from_bytes(image[:4], 'little'))
            self.assertEqual(self.words[base + SLOT_WORDS - 1], int.from_bytes(image[-4:], 'little'))
            self.assertEqual(self.words[base + 0x134 // 4], int.from_bytes(image[0x134:0x138], 'little'))
            self.assertTrue(all(base + k in self.words for k in range(SLOT_WORDS)))
        # Empty slots and the reserved range are absent: they read erased.
        for index in set(range(library.IMAGE_COUNT)) - set(self.images):
            self.assertFalse(any(index * SLOT_WORDS + k in self.words for k in (0, SLOT_WORDS - 1, 0x1000)))
        self.assertFalse(any(word in self.words for word in (CATALOGUE_WORD - DATA_BASE + 256, flash_library.USER_WORDS - 1)))
        self.assertEqual(len(self.words), 3 * SLOT_WORDS + 256)

    def test_catalogue_words_are_the_host_loader_catalogue(self):
        entries = {index: library.image_entry(image, library.profile_id(profile)) for index, (image, profile) in self.images.items()}
        expected = library.build_catalogue(entries)
        self.assertEqual(self.assembled['catalogue'], expected)
        base = CATALOGUE_WORD - DATA_BASE
        for k in range(256):
            self.assertEqual(self.words[base + k], int.from_bytes(expected[4 * k:4 * k + 4], 'little'))
        menu = library.parse_catalogue(expected)[library.MENU_INDEX]
        self.assertEqual((menu['valid'], menu['length'], menu['profile']), (library.VALID, library.SLOT_BYTES, abi.PROFILE_LOADER_ID))
        self.assertEqual(menu['crc32'], zlib.crc32(self.images[library.MENU_INDEX][0]))
        rows = {row['index']: row for row in self.assembled['rows']}
        self.assertEqual(rows[5]['flash_word'], f'0x{DATA_BASE + 5 * SLOT_WORDS:05X}')
        self.assertEqual(rows[library.MENU_INDEX]['title'], 'GAME MENU')

    def test_assembly_refuses_bad_images(self):
        with self.assertRaisesRegex(ValueError, 'requires the menu image'):
            flash_library.assemble({0: self.images[0]})
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            flash_library.assemble({**self.images, 1: (self.images[0][0][:-1], abi.PROFILE_NAME)})
        with self.assertRaisesRegex(ValueError, 'refuses images of profile'):
            flash_library.assemble({**self.images, 1: (self.images[0][0], 'unknown-profile')})
        with self.assertRaisesRegex(ValueError, r'0\.\.16'):
            flash_library.assemble({**self.images, 17: self.images[0]})

    def test_intel_hex_is_byte_addressed_at_four_times_the_avalon_word(self):
        text = flash_library.intel_hex(self.words)
        lines = text.splitlines()
        self.assertEqual(lines[0], ':020000040000FA')
        self.assertEqual(lines[1], ':10000000' + self.images[0][0][:16].hex().upper() + lines[1][-2:])
        self.assertEqual(lines[-1], ':00000001FF')
        for line in lines:
            body = bytes.fromhex(line[1:])
            self.assertEqual(sum(body) & 0xFF, 0, line)
            self.assertEqual(len(body), body[0] + 5, line)
            self.assertIn(body[3], (0, 1, 4))
        parsed = flash_library.parse_intel_hex(text)
        # The whole user range is defined; words the library leaves out are erased.
        self.assertEqual(len(parsed), flash_library.USER_BYTES)
        self.assertEqual(len(lines), flash_library.USER_BYTES // 16 + 12 + 1)
        for index, (image, _profile) in self.images.items():
            base = index * library.SLOT_BYTES
            self.assertEqual(bytes(parsed[base + b] for b in range(len(image))), image)
            self.assertEqual(parsed[base], image[0])
            self.assertEqual(parsed[base + library.SLOT_BYTES - 1], image[-1])
        for b, byte in enumerate(self.assembled['catalogue']):
            self.assertEqual(parsed[4 * (CATALOGUE_WORD - DATA_BASE) + b], byte)
        for address in (library.SLOT_BYTES, 2 * library.SLOT_BYTES - 1, library.CATALOGUE_ADDRESS + 1024,
                        flash_library.USER_BYTES - 1):
            self.assertEqual(parsed[address], 0xFF)
        self.assertEqual(lines[1 + library.SLOT_BYTES // 16], ':108000' + '00' + 'FF' * 16 + '80')
        # Extended linear address records precede the first record of each 64 KiB segment.
        segments = [int(line[9:13], 16) for line in lines if line[7:9] == '04']
        self.assertEqual(segments, list(range(12)))
        with self.assertRaisesRegex(ValueError, 'exceed the user range'):
            flash_library.intel_hex({flash_library.USER_WORDS: 0})
        short = flash_library.intel_hex({1: 0x11223344}, count=2)
        self.assertEqual(short.splitlines(), [':020000040000FA', ':08000000FFFFFFFF4433221152', ':00000001FF'])
        with self.assertRaisesRegex(ValueError, 'checksum'):
            flash_library.parse_intel_hex(text.replace(lines[1], lines[1][:-2] + '00', 1))
        with self.assertRaisesRegex(ValueError, 'without an end record'):
            flash_library.parse_intel_hex('\n'.join(lines[:-1]) + '\n')

    def test_verilog_hex_uses_the_readmemh_word_records(self):
        text = flash_library.verilog_hex(self.words)
        lines = text.splitlines()
        self.assertEqual(lines[0], f'@00000 {self.words[0]:08X}')
        self.assertEqual(lines[-1], f'@{CATALOGUE_WORD - DATA_BASE + 255:05X} {self.words[CATALOGUE_WORD - DATA_BASE + 255]:08X}')
        self.assertEqual(flash_library.parse_verilog_hex(text), self.words)
        with self.assertRaisesRegex(ValueError, 'malformed word record'):
            flash_library.parse_verilog_hex('@0 1\n')
        user = flash_library.words_to_bytes(self.words)
        self.assertEqual(len(user), flash_library.USER_BYTES)
        self.assertEqual(user[:library.SLOT_BYTES], self.images[0][0])
        self.assertEqual(user[library.SLOT_BYTES:2 * library.SLOT_BYTES], b'\xFF' * library.SLOT_BYTES)
        self.assertEqual(user[-4:], b'\xFF' * 4)

    def test_pof_word_transform_reverses_each_word(self):
        self.assertEqual(flash_library.pof_words(bytes.fromhex('01000000')), bytes.fromhex('00000080'))
        self.assertEqual(flash_library.pof_words(bytes.fromhex('00000080')), bytes.fromhex('01000000'))
        self.assertEqual(flash_library.pof_words(bytes.fromhex('44332211')), bytes.fromhex('8844CC22'))
        self.assertEqual(flash_library.pof_words(b'\xFF' * 8), b'\xFF' * 8)
        image = flash_library.words_to_bytes(self.words)
        self.assertEqual(flash_library.pof_words(flash_library.pof_words(image)), image)

    def test_write_records_both_files_and_the_catalogue(self):
        with tempfile.TemporaryDirectory() as folder:
            hashes = flash_library.write(folder, self.assembled)
            self.assertEqual(set(hashes), {'library.hex', 'library.dat', 'catalogue.bin'})
            for name, sha in hashes.items():
                self.assertEqual(file_hash(Path(folder) / name), sha)
            self.assertEqual((Path(folder) / 'catalogue.bin').read_bytes(), self.assembled['catalogue'])
            self.assertEqual(flash_library.parse_verilog_hex((Path(folder) / 'library.dat').read_text()), self.words)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='flash registry ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / flash_library.REGISTRY).parent.mkdir(parents=True)
        (self.root / flash_library.SW_REGISTRY).parent.mkdir(parents=True)
        self.packages = {'springtrail': {'profile': abi.PROFILE_NAME}, 'stackdrop': {'profile': abi.PROFILE_NAME},
                         'menu': {'profile': library.LOADER_PROFILE_NAME}, 'objects': {}}
        (self.root / flash_library.SW_REGISTRY).write_text(json.dumps({'schema_version': 2, 'targets': self.packages}))

    def registry(self, **fields):
        data = {'schema_version': 1, 'slots': {'0': 'springtrail', '1': 'stackdrop'}, 'menu': 'menu', **fields}
        (self.root / flash_library.REGISTRY).write_text(json.dumps(data))
        return flash_library.load_registry(self.root)

    def test_registry_names_slots_and_the_menu(self):
        registry = self.registry()
        self.assertEqual(registry['slots'], {0: 'springtrail', 1: 'stackdrop'})
        self.assertEqual(registry['menu'], 'menu')
        self.assertEqual(registry['sha256'], file_hash(self.root / flash_library.REGISTRY))

    def test_registry_refusals(self):
        cases = ((dict(schema_version=2), 'schema'), (dict(slots={}), 'schema'), (dict(extra=1), 'schema'),
                 (dict(slots={'16': 'springtrail'}), r'0\.\.15'), (dict(slots={'01': 'springtrail'}), r'0\.\.15'),
                 (dict(slots={'0': 'objects'}), 'no packaged software target'),
                 (dict(slots={'0': 'missing'}), 'no packaged software target'),
                 (dict(slots={'0': 'Bad Name'}), 'invalid flash library package name'),
                 (dict(menu='springtrail'), 'menu image must run in dmg-loader-v1'),
                 (dict(slots={'0': 'springtrail', '3': 'springtrail'}), 'only one flash library slot'),
                 (dict(slots={'0': 'menu'}), 'only one flash library slot'))
        for fields, message in cases:
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, message):
                    self.registry(**fields)

    def test_checked_in_registry_is_valid_and_lists_our_games(self):
        registry = flash_library.load_registry(ROOT)
        self.assertEqual(registry['slots'], {0: 'springtrail', 1: 'stackdrop', 2: 'v05'})
        self.assertEqual(registry['menu'], 'menu')


class BuilderTests(unittest.TestCase):
    def test_flash_targets_require_the_pof_and_the_library_files(self):
        flash = {'top': 'flash_proof', 'sources': [fpga_flash.READER]}
        self.assertIn('design.pof', fpga.required_reports(flash))
        self.assertNotIn('design.pof', fpga.required_reports({'top': 'smoke', 'sources': []}))
        self.assertEqual(fpga.required_reports({'top': 'smoke', 'sources': []}), fpga.REQUIRED_REPORTS)
        self.assertEqual(fpga_flash.reader_path('flash_proof'), 'u_reader')

    def test_sw_library_stage_assembles_the_registered_packages(self):
        parent = ROOT / 'workdir/builds'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='flash-library-unit-', dir=parent) as build:
            build = Path(build)
            report = flash_library.library_stage(ROOT, build, SimpleNamespace(rebuild=False), {'commit': 'test'})
            self.assertEqual(report['status'], 'PASS', report.get('error'))
            summary = report['library']
            self.assertEqual([row['index'] for row in summary['images']], [0, 1, 2, 16])
            self.assertEqual([row['title'] for row in summary['images']], ['SPRINGTRAIL', 'STACKDROP', 'V05 BUTTONS', 'GAME MENU'])
            self.assertEqual(summary['images'][3]['profile'], abi.PROFILE_LOADER_ID)
            self.assertEqual(summary['catalogue_flash_word'], '0x22800')
            self.assertEqual(summary['defined_words'], 4 * SLOT_WORDS + 256)
            for name in ('library.hex', 'library.dat', 'catalogue.bin'):
                path = ROOT / summary['files'][name]['path']
                self.assertTrue(path.is_file())
                self.assertEqual(file_hash(path), summary['files'][name]['sha256'])
                self.assertIn(summary['files'][name]['path'], report['artifacts'])
            words = flash_library.parse_verilog_hex((ROOT / summary['files']['library.dat']['path']).read_text())
            parsed = flash_library.parse_intel_hex((ROOT / summary['files']['library.hex']['path']).read_text())
            self.assertEqual(parsed, dict(enumerate(flash_library.words_to_bytes(words))))
            for row in summary['images']:
                image = (ROOT / row['result']).parent.joinpath('image.gb').read_bytes()
                self.assertEqual(file_hash((ROOT / row['result']).parent / 'image.gb'), row['image_sha256'])
                base = row['index'] * library.SLOT_BYTES
                self.assertEqual(bytes(parsed[base + b] for b in range(library.SLOT_BYTES)), image)
                self.assertEqual(row['crc32'], f'{zlib.crc32(image):08x}')
            mirror = json.loads((build / 'sw/library/result.json').read_text())
            self.assertEqual(mirror['attempt'], report['attempt'])


if __name__ == '__main__':
    unittest.main()
