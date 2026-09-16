"""Flash library image assembly against the contract's flash words; registry validation; builder records."""
import json
from pathlib import Path
import sys
import hashlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import flash_library, fpga, fpga_flash, generated_interfaces as abi
from n2m.host import external, library
from n2m.records import file_hash
from sw.package import package

ROOT = Path(__file__).resolve().parents[3]
SLOT_WORDS = library.SLOT_BYTES // 4
CATALOGUE_WORD = 0x22800
DATA_BASE = 0x00800
EXTERNALS = {3: 'libbet', 4: 'airaki', 5: 'gb-wordyl', 6: 'max-pirate', 7: 'alien-invasion', 8: 'square-fall',
             9: 'unstoppable-knight', 10: 'postbot'}
# The 64 KiB MBC1 pin: slot 10 and its continuation slot 11 (two-slot rule).
BANKED_EXTERNALS = {10: 'postbot'}
# Header titles of the pinned images as `title_text` prints them (bytes 0x134-0x143; the 0x80
# CGB flag at 0x143 keeps the zero padding before it, all printed `?`) and the pinned display
# titles that stand in for the two blank headers.
EXTERNAL_TITLES = {3: 'LIBBET' + '?' * 10, 4: 'AIRAKI1     ????', 5: 'GB-WORDYL' + '?' * 7,
                   6: 'MAXPIRATE', 7: 'ALIEN INVASION', 8: 'SQUARE FALL', 9: 'KNIGHT' + '?' * 10, 10: 'POSTBOT'}


def external_image(title, seed, cartridge=0, rom_size=0, size=library.SLOT_BYTES):
    """A locally generated image with the given header title and cartridge bytes; never a downloaded game."""
    image = bytearray((index * seed + index // 128) % 256 for index in range(size))
    image[0x134:0x144] = bytes(title).ljust(16, b'\0')
    image[0x147], image[0x148] = cartridge, rom_size
    return bytes(image)


MBC1_PROFILE = {'dmg-mbc1-v1': abi.PROFILE_MBC1_ID}


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

    def test_a_64_kib_image_fills_two_slots_with_one_entry(self):
        banked = external_image(b'BANKED GAME', 13, cartridge=1, rom_size=1, size=abi.MBC1_ROM_BYTES)
        images = {**self.images, 6: (banked, 'dmg-mbc1-v1')}
        with patch.dict(library.PROFILE_IDS, MBC1_PROFILE):
            assembled = flash_library.assemble(images)
        words = assembled['words']
        base = 6 * SLOT_WORDS
        self.assertEqual(words[base], int.from_bytes(banked[:4], 'little'))
        self.assertEqual(words[base + 2 * SLOT_WORDS - 1], int.from_bytes(banked[-4:], 'little'))
        self.assertEqual(len(words), 5 * SLOT_WORDS + 256)
        rows = library.parse_catalogue(assembled['catalogue'])
        self.assertEqual((rows[6]['valid'], rows[6]['profile'], rows[6]['length'], rows[6]['crc32']),
                         (library.VALID, abi.PROFILE_MBC1_ID, abi.MBC1_ROM_BYTES, zlib.crc32(banked)))
        self.assertEqual(rows[7], {**library.EMPTY_ENTRY, 'reserved_zero': True})
        self.assertEqual({row['index'] for row in assembled['rows']}, {0, 5, 6, library.MENU_INDEX})
        parsed = flash_library.parse_intel_hex(flash_library.intel_hex(words))
        self.assertEqual(bytes(parsed[6 * library.SLOT_BYTES + b] for b in range(abi.MBC1_ROM_BYTES)), banked)
        # The 32 KiB entries and their words are the ones the all-32 KiB library produces.
        self.assertEqual(assembled['catalogue'][:6 * 32], self.assembled['catalogue'][:6 * 32])
        self.assertEqual({k: v for k, v in words.items() if k < 6 * SLOT_WORDS}, {k: v for k, v in self.words.items() if k < 6 * SLOT_WORDS})
        with patch.dict(library.PROFILE_IDS, MBC1_PROFILE):
            with self.assertRaisesRegex(ValueError, 'slot 6 is filled by both slot 5 and slot 6'):
                flash_library.assemble({**images, 5: (banked, 'dmg-mbc1-v1')})
            with self.assertRaisesRegex(ValueError, 'would spill past slot 15'):
                flash_library.assemble({**self.images, 15: (banked, 'dmg-mbc1-v1')})
            with self.assertRaisesRegex(ValueError, 'must be exactly 65536 bytes'):
                flash_library.assemble({**self.images, 1: (self.images[0][0], 'dmg-mbc1-v1')})
        with self.assertRaisesRegex(ValueError, 'must be exactly 32768 bytes'):
            flash_library.assemble({**self.images, 1: (banked, abi.PROFILE_NAME)})

    def test_assembly_refuses_bad_images(self):
        with self.assertRaisesRegex(ValueError, 'requires the menu image'):
            flash_library.assemble({0: self.images[0]})
        with self.assertRaisesRegex(ValueError, 'must be exactly 32768 bytes'):
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
        (self.root / external.PIN_FILE).parent.mkdir(parents=True)
        self.pin = {'url': 'https://example.invalid/game.gb', 'sha256': '0' * 64, 'size': library.SLOT_BYTES, 'license': 'MIT'}
        self.pins = {'game': dict(self.pin), 'other': dict(self.pin, url='https://example.invalid/other.gb', license='Zlib'),
                     'small': dict(self.pin, size=16384), 'nolicense': {k: v for k, v in self.pin.items() if k != 'license'},
                     'banked': dict(self.pin, size=abi.MBC1_ROM_BYTES, url='https://example.invalid/banked.gb')}
        (self.root / external.PIN_FILE).write_text(json.dumps({'external_roms': {'images': self.pins}}))

    def registry(self, **fields):
        data = {'schema_version': 1, 'slots': {'0': 'springtrail', '1': 'stackdrop'}, 'menu': 'menu', **fields}
        (self.root / flash_library.REGISTRY).write_text(json.dumps(data))
        return flash_library.load_registry(self.root)

    def test_registry_names_slots_and_the_menu(self):
        registry = self.registry()
        self.assertEqual(registry['slots'], {0: 'springtrail', 1: 'stackdrop'})
        self.assertEqual(registry['menu'], 'menu')
        self.assertEqual(registry['externals'], {})
        self.assertEqual(registry['sha256'], file_hash(self.root / flash_library.REGISTRY))

    def test_registry_resolves_external_slots_through_the_pin_table(self):
        registry = self.registry(slots={'0': 'springtrail', '3': 'external:game', '9': 'external:other'})
        self.assertEqual(registry['slots'], {0: 'springtrail', 3: 'external:game', 9: 'external:other'})
        self.assertEqual(registry['externals'], {
            3: {'pin': 'game', 'licence': 'MIT', 'source': 'https://example.invalid/game.gb', 'sha256': '0' * 64},
            9: {'pin': 'other', 'licence': 'Zlib', 'source': 'https://example.invalid/other.gb', 'sha256': '0' * 64}})
        self.assertEqual(flash_library.slot_source('external:game'), ('external', 'game'))
        self.assertEqual(flash_library.slot_source('springtrail'), ('package', 'springtrail'))

    def test_a_64_kib_external_pin_needs_the_next_slot_free(self):
        registry = self.registry(slots={'0': 'springtrail', '3': 'external:banked', '5': 'external:game'})
        self.assertEqual(sorted(registry['externals']), [3, 5])
        registry = self.registry(slots={'14': 'external:banked'})
        self.assertEqual(sorted(registry['externals']), [14])
        cases = ((dict(slots={'3': 'external:banked', '4': 'external:game'}), 'banked at slot 3 also fills slot 4, which is registered'),
                 (dict(slots={'3': 'external:banked', '4': 'springtrail'}), 'also fills slot 4'),
                 (dict(slots={'15': 'external:banked'}), 'would spill past slot 15'))
        for fields, message in cases:
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, message):
                    self.registry(**fields)

    def test_external_registry_refusals(self):
        cases = ((dict(slots={'0': 'external:missing'}), 'names no pinned external image: missing'),
                 (dict(slots={'0': 'external:small'}), 'pinned at 16384 bytes, not 32768 or 65536'),
                 (dict(slots={'0': 'external:nolicense'}), 'missing license'),
                 (dict(slots={'0': 'external:Bad Name'}), 'invalid external image name'),
                 (dict(slots={'0': 'external:'}), 'invalid external image name'),
                 (dict(slots={'0': 'external:game', '1': 'external:game'}), 'only one flash library slot'),
                 (dict(menu='external:game'), 'menu image must be a packaged software target'))
        for fields, message in cases:
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, message):
                    self.registry(**fields)

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

    def test_checked_in_registry_lists_our_games_and_the_eight_homebrew_games_that_ran_here(self):
        registry = flash_library.load_registry(ROOT)
        self.assertEqual(registry['slots'], {0: 'springtrail', 1: 'stackdrop', 2: 'v05',
                                             **{index: 'external:' + name for index, name in EXTERNALS.items()}})
        self.assertEqual(registry['menu'], 'menu')
        self.assertEqual(sorted(registry['externals']), sorted(EXTERNALS))
        pins = json.loads((ROOT / external.PIN_FILE).read_text())['external_roms']['images']
        for index, name in EXTERNALS.items():
            self.assertEqual(registry['externals'][index],
                             {'pin': name, 'licence': pins[name]['license'], 'source': pins[name]['url'], 'sha256': pins[name]['sha256']})
        # The two images that never enable the LCD stay out; the 64 KiB MBC1 pin fills slots
        # 10-11, so slot 11 is not registered; the two blank-header images carry a display title.
        self.assertEqual(sorted(set(pins) - set(EXTERNALS.values())), ['rex-run', 'wyrmhole'])
        self.assertEqual({name: pins[name].get('profile', 'dmg-direct-v1') for name in EXTERNALS.values()},
                         {name: 'dmg-mbc1-v1' if name in BANKED_EXTERNALS.values() else 'dmg-direct-v1' for name in EXTERNALS.values()})
        self.assertEqual({index: pins[name]['size'] for index, name in EXTERNALS.items()},
                         {index: abi.MBC1_ROM_BYTES if index in BANKED_EXTERNALS else library.SLOT_BYTES for index in EXTERNALS})
        self.assertNotIn(11, registry['slots'])
        self.assertEqual({name: pins[name].get('title') for name in ('alien-invasion', 'square-fall')},
                         {'alien-invasion': 'ALIEN INVASION', 'square-fall': 'SQUARE FALL'})


class ExternalImageTests(unittest.TestCase):
    """External slots resolved offline against a fake pin table and fake cached files; no network."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='flash external ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.images = {'named': external_image(b'NAMED GAME', 3), 'blank': external_image(b'', 5),
                       'cgb': external_image(b'CGB' + bytes(12) + b'\x80', 7), 'mapper': external_image(b'MBC', 9, cartridge=1),
                       'control': external_image(b'\x01BAD', 11), 'unnamed-blank': external_image(b'', 13),
                       'banked': external_image(b'BANKED GAME', 15, cartridge=1, rom_size=1, size=abi.MBC1_ROM_BYTES),
                       'banked-ram': external_image(b'BANKED RAM', 17, cartridge=3, rom_size=1, size=abi.MBC1_ROM_BYTES),
                       'banked-ram-only': external_image(b'BANKED RAM2', 23, cartridge=2, rom_size=1, size=abi.MBC1_ROM_BYTES),
                       'banked-rom-only': external_image(b'NO MAPPER', 19, size=abi.MBC1_ROM_BYTES),
                       'banked-small-header': external_image(b'SMALL HEADER', 21, cartridge=1, size=abi.MBC1_ROM_BYTES)}
        self.pins = {name: {'url': f'https://example.invalid/{name}.gb', 'sha256': hashlib.sha256(image).hexdigest(),
                            'size': len(image), 'license': 'MIT'} for name, image in self.images.items()}
        self.pins['blank']['title'] = 'BLANK TITLE'
        self.pins['banked']['profile'] = 'dmg-mbc1-v1'
        self.pins['bad-title'] = dict(self.pins['blank'], title='lower case')
        self.pins['uncached'] = dict(self.pins['named'])
        self.pins['wrong-hash'] = dict(self.pins['named'], sha256='1' * 64)
        (self.root / external.PIN_FILE).parent.mkdir(parents=True)
        (self.root / external.PIN_FILE).write_text(json.dumps({'external_roms': {'images': self.pins}}))
        for name, image in list(self.images.items()) + [('wrong-hash', self.images['named']), ('bad-title', self.images['blank'])]:
            folder = self.root / external.CACHE / name
            folder.mkdir(parents=True)
            (folder / 'image.gb').write_bytes(image)

    def test_cached_images_resolve_offline_with_their_header_titles(self):
        with patch('n2m.host.external.urllib.request.urlopen', side_effect=AssertionError('offline')):
            image, profile, record = flash_library.external_image(self.root, 'named', offline=True)
            self.assertEqual((image, profile), (self.images['named'], abi.PROFILE_NAME))
            self.assertEqual((record['pin'], record['license'], record['title']), ('named', 'MIT', None))
            entry = library.image_entry(image, abi.PROFILE_DIRECT_ID, record['title'])
            self.assertEqual(entry['title'], b'NAMED GAME'.ljust(16, b'\0'))
            image, _profile, record = flash_library.external_image(self.root, 'cgb', offline=True)
            self.assertEqual(library.image_entry(image, abi.PROFILE_DIRECT_ID, record['title'])['title'], image[0x134:0x144])
        # A 64 KiB image with the MBC1 (no RAM) header runs in the MBC1 profile.
        # (The pin reader's own 64 KiB acceptance belongs to the toolchain slice; the header check is exercised directly.)
        self.assertEqual(flash_library.check_external_header(self.images['banked'], 'banked'), 'dmg-mbc1-v1')
        self.assertEqual(library.image_entry(self.images['banked'], abi.PROFILE_MBC1_ID)['length'], abi.MBC1_ROM_BYTES)

    def test_blank_header_title_takes_the_pinned_display_title_only(self):
        image, _profile, record = flash_library.external_image(self.root, 'blank', offline=True)
        self.assertEqual(record['title'], b'BLANK TITLE')
        self.assertEqual(library.image_entry(image, abi.PROFILE_DIRECT_ID, record['title'])['title'], b'BLANK TITLE'.ljust(16, b'\0'))
        # A non-blank header is never overridden, and the fallback changes no other field.
        named = library.image_entry(self.images['named'], abi.PROFILE_DIRECT_ID, b'OVERRIDE')
        self.assertEqual(named, library.image_entry(self.images['named'], abi.PROFILE_DIRECT_ID))
        self.assertEqual(library.image_entry(image, abi.PROFILE_DIRECT_ID)['title'], bytes(16))
        with self.assertRaisesRegex(ValueError, r'1\.\.16 bytes'):
            library.image_entry(image, abi.PROFILE_DIRECT_ID, b'X' * 17)

    def test_external_refusals_name_the_image(self):
        cases = (('uncached', 'external image is not cached: uncached'), ('wrong-hash', 'hash mismatch: wrong-hash'),
                 ('mapper', 'mapper header 0x147/0x148 does not describe a 32768-byte dmg-direct-v1 cartridge'),
                 ('control', 'outside printable ASCII at 0x134'),
                 ('unnamed-blank', 'unnamed-blank has a blank header title and its pin has no title'),
                 ('bad-title', 'pin title must be'), ('unknown', 'unknown external image pin: unknown'))
        with patch('n2m.host.external.urllib.request.urlopen', side_effect=AssertionError('offline')):
            for name, message in cases:
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, message):
                        flash_library.external_image(self.root, name, offline=True)
        with self.assertRaisesRegex(ValueError, 'not a 32768- or 65536-byte image'):
            flash_library.check_external_header(self.images['named'][:-1], 'short')
        # MBC1 with cartridge RAM (types 0x02/0x03) is not carried: the profile has no RAM.
        for name in ('banked-rom-only', 'banked-small-header', 'banked-ram', 'banked-ram-only'):
            with self.assertRaisesRegex(ValueError, f'{name} header 0x147/0x148 does not describe a 65536-byte dmg-mbc1-v1 cartridge'):
                flash_library.check_external_header(self.images[name], name)

    def test_build_images_stages_external_slots_beside_the_packages(self):
        registry = {'slots': {0: 'springtrail', 3: 'external:named', 4: 'external:blank'}, 'menu': 'menu',
                    'externals': {3: {'pin': 'named', 'licence': 'MIT', 'source': self.pins['named']['url'], 'sha256': self.pins['named']['sha256']},
                                  4: {'pin': 'blank', 'licence': 'MIT', 'source': self.pins['blank']['url'], 'sha256': self.pins['blank']['sha256']}}}
        build = self.root / 'workdir/builds/unit'

        def fake_build(root, build, args, provenance):
            rom = build / 'sw/build' / args.target / 'runs/0/image.gb'
            rom.parent.mkdir(parents=True, exist_ok=True)
            rom.write_bytes(fixture_image(args.target.upper(), 17))
            relative = rom.relative_to(root).as_posix()
            profile = library.LOADER_PROFILE_NAME if args.target == 'menu' else abi.PROFILE_NAME
            return {'status': 'PASS', 'rom': relative, 'profile': profile, 'attempt': '0', 'fingerprint': 'f' * 8,
                    'artifacts': {relative: file_hash(rom)}}

        with patch('sw.rom_build.build_target', fake_build), \
                patch('n2m.host.external.urllib.request.urlopen', side_effect=AssertionError('offline')):
            images = flash_library.build_images(self.root, build, registry, {}, offline=True)
        self.assertEqual(sorted(images), [0, 3, 4, library.MENU_INDEX])
        self.assertEqual(images[3][:2], (self.images['named'], abi.PROFILE_NAME))
        self.assertEqual(images[3][2], {'kind': 'external', **registry['externals'][3], 'image_sha256': self.pins['named']['sha256'],
                                        'notices': [], 'fallback_title': None})
        self.assertEqual(images[4][2]['fallback_title'], b'BLANK TITLE')
        self.assertEqual(images[0][2]['kind'], 'package')
        assembled = flash_library.assemble(images)
        rows = {row['index']: row for row in assembled['rows']}
        self.assertEqual((rows[3]['title'], rows[4]['title'], rows[0]['title']), ('NAMED GAME', 'BLANK TITLE', 'SPRINGTRAIL'))
        self.assertEqual((rows[3]['licence'], rows[3]['source'], rows[3]['pin']), ('MIT', self.pins['named']['url'], 'named'))
        self.assertNotIn('fallback_title', rows[3])
        self.assertEqual(rows[4]['crc32'], f"{zlib.crc32(self.images['blank']):08x}")
        catalogue = library.parse_catalogue(assembled['catalogue'])
        self.assertEqual(catalogue[4]['title'], b'BLANK TITLE'.ljust(16, b'\0'))
        self.assertEqual(catalogue[3]['crc32'], zlib.crc32(self.images['named']))
        # Offline with one cache missing fails by name, before any package is touched.
        registry['slots'][5] = 'external:uncached'
        registry['externals'][5] = {'pin': 'uncached', 'licence': 'MIT', 'source': '', 'sha256': ''}
        with patch('sw.rom_build.build_target', fake_build), \
                patch('n2m.host.external.urllib.request.urlopen', side_effect=AssertionError('offline')):
            with self.assertRaisesRegex(ValueError, 'not cached: uncached'):
                flash_library.build_images(self.root, build, registry, {}, offline=True)

    def test_build_images_places_a_registered_64_kib_external_in_two_slots(self):
        registry = {'slots': {0: 'springtrail', 10: 'external:banked'}, 'menu': 'menu',
                    'externals': {10: {'pin': 'banked', 'licence': 'MIT', 'source': self.pins['banked']['url'],
                                       'sha256': self.pins['banked']['sha256']}}}
        build = self.root / 'workdir/builds/unit'

        def fake_build(root, build, args, provenance):
            rom = build / 'sw/build' / args.target / 'runs/0/image.gb'
            rom.parent.mkdir(parents=True, exist_ok=True)
            rom.write_bytes(fixture_image(args.target.upper(), 19))
            relative = rom.relative_to(root).as_posix()
            profile = library.LOADER_PROFILE_NAME if args.target == 'menu' else abi.PROFILE_NAME
            return {'status': 'PASS', 'rom': relative, 'profile': profile, 'attempt': '0', 'fingerprint': 'f' * 8,
                    'artifacts': {relative: file_hash(rom)}}

        with patch('sw.rom_build.build_target', fake_build), \
                patch('n2m.host.external.urllib.request.urlopen', side_effect=AssertionError('offline')):
            images = flash_library.build_images(self.root, build, registry, {}, offline=True)
        self.assertEqual(sorted(images), [0, 10, library.MENU_INDEX])
        self.assertEqual(images[10][:2], (self.images['banked'], 'dmg-mbc1-v1'))
        self.assertEqual(images[10][2]['image_sha256'], self.pins['banked']['sha256'])
        assembled = flash_library.assemble(images)
        words = assembled['words']
        # Slots 10 and 11 hold the image; slots 12-15 stay erased; the menu and catalogue follow.
        self.assertEqual(len(words), 4 * SLOT_WORDS + 256)
        self.assertEqual(words[10 * SLOT_WORDS], int.from_bytes(self.images['banked'][:4], 'little'))
        self.assertEqual(words[12 * SLOT_WORDS - 1], int.from_bytes(self.images['banked'][-4:], 'little'))
        self.assertNotIn(12 * SLOT_WORDS, words)
        parsed = flash_library.parse_intel_hex(flash_library.intel_hex(words))
        self.assertEqual(bytes(parsed[10 * library.SLOT_BYTES + b] for b in range(abi.MBC1_ROM_BYTES)), self.images['banked'])
        rows = {row['index']: row for row in assembled['rows']}
        self.assertEqual(sorted(rows), [0, 10, library.MENU_INDEX])
        self.assertEqual((rows[10]['title'], rows[10]['profile'], rows[10]['profile_name'], rows[10]['flash_word'], rows[10]['pin']),
                         ('BANKED GAME', abi.PROFILE_MBC1_ID, 'dmg-mbc1-v1', '0x14800', 'banked'))
        catalogue = library.parse_catalogue(assembled['catalogue'])
        self.assertEqual((catalogue[10]['valid'], catalogue[10]['profile'], catalogue[10]['length'], catalogue[10]['crc32']),
                         (library.VALID, abi.PROFILE_MBC1_ID, abi.MBC1_ROM_BYTES, zlib.crc32(self.images['banked'])))
        self.assertEqual(catalogue[11], {**library.EMPTY_ENTRY, 'reserved_zero': True})
        # A pin whose profile disagrees with its header is refused by name.
        self.pins['banked-ram']['profile'] = self.pins['banked-rom-only']['profile'] = 'dmg-mbc1-v1'
        (self.root / external.PIN_FILE).write_text(json.dumps({'external_roms': {'images': self.pins}}))
        with patch('n2m.host.external.urllib.request.urlopen', side_effect=AssertionError('offline')):
            with self.assertRaisesRegex(ValueError, 'banked-ram header 0x147/0x148 does not describe a 65536-byte dmg-mbc1-v1 cartridge'):
                flash_library.external_image(self.root, 'banked-ram', offline=True)
            with self.assertRaisesRegex(ValueError, 'banked-rom-only header 0x147/0x148 does not describe'):
                flash_library.external_image(self.root, 'banked-rom-only', offline=True)


class BuilderTests(unittest.TestCase):
    def test_flash_targets_require_the_pof_and_the_library_files(self):
        flash = {'top': 'flash_proof', 'sources': [fpga_flash.READER]}
        self.assertIn('design.pof', fpga.required_reports(flash))
        self.assertNotIn('design.pof', fpga.required_reports({'top': 'smoke', 'sources': []}))
        self.assertEqual(fpga.required_reports({'top': 'smoke', 'sources': []}), fpga.REQUIRED_REPORTS)
        self.assertEqual(fpga_flash.reader_path('flash_proof'), 'u_reader')

    def test_sw_library_stage_assembles_the_registered_packages_and_cached_externals(self):
        missing = [name for name in EXTERNALS.values() if not (ROOT / external.CACHE / name / 'image.gb').is_file()]
        if missing:
            self.skipTest(f'external images not cached (run `sw library` online once): {", ".join(missing)}')
        parent = ROOT / 'workdir/builds'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='flash-library-unit-', dir=parent) as build:
            build = Path(build)
            report = flash_library.library_stage(ROOT, build, SimpleNamespace(rebuild=False, offline=True), {'commit': 'test'})
            self.assertEqual(report['status'], 'PASS', report.get('error'))
            summary = report['library']
            self.assertEqual([row['index'] for row in summary['images']], [*range(11), 16])
            self.assertEqual([row['title'] for row in summary['images']],
                             ['SPRINGTRAIL', 'STACKDROP', 'V05 BUTTONS', *(EXTERNAL_TITLES[i] for i in range(3, 11)), 'GAME MENU'])
            self.assertEqual(summary['images'][11]['profile'], abi.PROFILE_LOADER_ID)
            self.assertEqual({row['profile'] for row in summary['images'][:10]}, {abi.PROFILE_DIRECT_ID})
            self.assertEqual((summary['images'][10]['profile'], summary['images'][10]['profile_name'], summary['images'][10]['flash_word']),
                             (abi.PROFILE_MBC1_ID, 'dmg-mbc1-v1', '0x14800'))
            self.assertEqual(summary['catalogue_flash_word'], '0x22800')
            # Ten 32 KiB slots, the two-slot PostBot image, the menu and the catalogue.
            self.assertEqual(summary['defined_words'], 13 * SLOT_WORDS + 256)
            pins = json.loads((ROOT / external.PIN_FILE).read_text())['external_roms']['images']
            for row in summary['images'][3:11]:
                pin = pins[EXTERNALS[row['index']]]
                self.assertEqual((row['kind'], row['pin'], row['licence'], row['source'], row['image_sha256']),
                                 ('external', EXTERNALS[row['index']], pin['license'], pin['url'], pin['sha256']))
            for name in ('library.hex', 'library.dat', 'catalogue.bin'):
                path = ROOT / summary['files'][name]['path']
                self.assertTrue(path.is_file())
                self.assertEqual(file_hash(path), summary['files'][name]['sha256'])
                self.assertIn(summary['files'][name]['path'], report['artifacts'])
            words = flash_library.parse_verilog_hex((ROOT / summary['files']['library.dat']['path']).read_text())
            parsed = flash_library.parse_intel_hex((ROOT / summary['files']['library.hex']['path']).read_text())
            self.assertEqual(parsed, dict(enumerate(flash_library.words_to_bytes(words))))
            for row in summary['images']:
                path = ((ROOT / row['result']).parent if row['kind'] == 'package'
                        else ROOT / external.CACHE / row['pin']) / 'image.gb'
                image = path.read_bytes()
                self.assertEqual(file_hash(path), row['image_sha256'])
                base = row['index'] * library.SLOT_BYTES
                self.assertEqual(bytes(parsed[base + b] for b in range(len(image))), image)
                self.assertEqual(row['crc32'], f'{zlib.crc32(image):08x}')
            self.assertEqual(len(images_by_index := {row['index']: row for row in summary['images']}), 12)
            self.assertEqual(images_by_index[10]['pin'], 'postbot')
            catalogue = library.parse_catalogue((ROOT / summary['files']['catalogue.bin']['path']).read_bytes())
            self.assertEqual((catalogue[10]['profile'], catalogue[10]['length'], catalogue[10]['title'][:7]),
                             (abi.PROFILE_MBC1_ID, abi.MBC1_ROM_BYTES, b'POSTBOT'))
            self.assertEqual(catalogue[11], {**library.EMPTY_ENTRY, 'reserved_zero': True})
            self.assertEqual([row['valid'] for row in catalogue], [library.VALID] * 11 + [0] * 5 + [library.VALID])
            mirror = json.loads((build / 'sw/library/result.json').read_text())
            self.assertEqual(mirror['attempt'], report['attempt'])


if __name__ == '__main__':
    unittest.main()
