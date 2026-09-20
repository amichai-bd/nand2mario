"""A carried ROM image is declared once, checked by the packager and fitted whole."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import fpga, fpga_rom_image
from sw.expressions import AssemblyError
from sw.package import package

ROOT = Path(__file__).resolve().parents[3]
TARGET = {"top": "n2m_memory_stores", "family": "MAX 10", "sources": [], "rom_image": "springtrail"}


def image(entry=0x200, fill=0xC9):
    """A valid direct-profile image the packager accepts, built by the packager."""
    body = bytearray([fill]) * 32768
    body[0x100:0x150] = bytes([0xFF]) * 0x50
    return package({"image": bytes(body), "entry": entry}, "ROM IMAGE TEST", 1)


def netlist(planes, instance="rom", init_file=fpga_rom_image.MIF_NAME):
    """A netlist fragment stating the given block contents as Quartus writes them."""
    lines = []
    for index, bits in enumerate(planes):
        name = f"{instance}|ram|auto_generated|ram_block{index}"
        lines.append(f'defparam \\{name} .init_file = "{init_file}";')
        for word in range(4):
            chunk = bits[len(bits) - (word + 1) * 2048:len(bits) - word * 2048]
            lines.append(f"defparam \\{name} .mem_init{word} = 2048'h{int(chunk, 2):0512X};")
    return "\n".join(lines)


class DeclarationTests(unittest.TestCase):
    def test_registered_target_declares_one_package_and_names_it_on_the_store(self):
        target = fpga.target_definition(ROOT, "memory-stores-preloaded")
        self.assertEqual(target["rom_image"], "springtrail")
        self.assertEqual(fpga_rom_image.assignments(target), [
            'set_global_assignment -name INTERNAL_FLASH_UPDATE_MODE "Single Comp Image with ERAM"',
            'set_parameter -name INIT_FILE "preload-rom.mif" -to "rom"'])
        # The same target without the declaration is the existing one, so nothing
        # else in its project files can move.
        plain = fpga.target_definition(ROOT, "memory-stores")
        self.assertEqual({key: value for key, value in target.items() if key != "rom_image"}, plain)
        self.assertIsNone(fpga_rom_image.declared(plain))
        self.assertEqual(fpga_rom_image.store_init_files(plain), {})
        self.assertEqual(fpga_rom_image.store_init_files(target), {"rom": "preload-rom.mif"})

    def test_a_board_without_internal_configuration_flash_states_no_mode(self):
        self.assertEqual(fpga_rom_image.assignments({**TARGET, "family": "Cyclone IV E"}),
                         ['set_parameter -name INIT_FILE "preload-rom.mif" -to "rom"'])
        self.assertIsNone(fpga_rom_image.configuration_mode("Cyclone IV E"))

    def test_refuses_an_unusable_declaration_by_name(self):
        for change in ({"rom_image": "Springtrail"}, {"rom_image": ""}, {"rom_image": 7},
                       {"rom_image": "no-such-package"}, {"rom_image": "menu"},
                       {"rom_image": "linker-banked"}, {"top": "n2m_uart_presence_store"},
                       {"sources": ["src/rtl/storage/n2m_flash_reader.sv"]}):
            with self.subTest(**change), self.assertRaises(ValueError):
                fpga_rom_image.validate(ROOT, {**TARGET, **change})
        fpga_rom_image.validate(ROOT, TARGET)

    def test_unregistered_top_has_no_store_path(self):
        with self.assertRaises(ValueError):
            fpga_rom_image.rom_path("n2m_uart_presence_store")


class PackagerTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/rom-image-unit"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.image = image()
        self.digest = hashlib.sha256(self.image).hexdigest()

    def test_records_the_carried_image_with_its_digest(self):
        record = fpga_rom_image.write(self.folder, self.image, self.digest)
        self.assertEqual(record["image_sha256"], self.digest)
        self.assertEqual(record["image_bytes"], 32768)
        self.assertEqual(record["init_file"], "preload-rom.mif")
        self.assertEqual(record["profile"], "dmg-direct-v1")
        self.assertEqual((self.folder / "program.gb").read_bytes(), self.image)
        self.assertEqual(hashlib.sha256((self.folder / "preload-rom.mif").read_bytes()).hexdigest(),
                         record["files"]["preload-rom.mif"])
        # The record is the same file the simulation preload loads.
        self.assertEqual(json.loads((self.folder / "preload.json").read_text())["image_sha256"], self.digest)

    def test_a_bad_length_or_checksum_refuses_the_build(self):
        short = self.image[:-1]
        for bytes_, digest in ((short, hashlib.sha256(short).hexdigest()), (self.image, "0" * 64),
                              (self.image + b"\0", self.digest)):
            with self.subTest(length=len(bytes_)), self.assertRaises(ValueError):
                fpga_rom_image.write(self.folder, bytes_, digest)
            self.assertEqual(list(self.folder.iterdir()), [])
        broken = bytearray(self.image)
        broken[0x14D] ^= 0xFF
        broken = bytes(broken)
        with self.assertRaises(AssemblyError):
            fpga_rom_image.write(self.folder, broken, hashlib.sha256(broken).hexdigest())
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_only_the_carried_profile_is_accepted(self):
        with self.assertRaises(ValueError):
            fpga_rom_image.write(self.folder, self.image, self.digest, profile="dmg-loader-v1")

    def test_the_zero_fill_diagnostic_states_the_declared_length(self):
        fpga_rom_image.write(self.folder, self.image, self.digest)
        path = (self.folder / "preload-rom.mif").resolve().as_posix()
        text = ("Info: something\n"
                f'Warning (113028): 32768 out of 65536 addresses are uninitialized. The Quartus Prime software '
                f'will initialize them to "0". There are 1 warnings found, and 1 warnings are reported. '
                f'File: {path} Line: 1\n'
                f"    Warning (113027): Addresses ranging from 32768 to 65535 are not initialized "
                f"File: {path} Line: 1\n")
        explained = fpga_rom_image.explained_diagnostics(text, self.folder)
        self.assertEqual([item["code"] for item in explained], ["113028", "113027"])
        for changed in (text.replace("32768 out", "16384 out"), text.replace("from 32768", "from 16384"),
                        text.replace("65535", "65534"), text + text.splitlines()[2] + "\n",
                        "\n".join(text.splitlines()[:2]) + "\n"):
            with self.subTest(changed=changed[:40]), self.assertRaises(ValueError):
                fpga_rom_image.explained_diagnostics(changed, self.folder)


class PowerUpTests(unittest.TestCase):
    """The parameters the wrapper passed, for both states, in one attempt."""

    HEAD = ('--altsyncram BYTE_SIZE=8 {init}NUMWORDS_A={words} '
            'POWER_UP_UNINITIALIZED="{power_up}" RAM_BLOCK_TYPE="M9K" address_a\nSUBDESIGN x\n')

    def megafunctions(self, shapes):
        folder = Path(tempfile.mkdtemp(dir=self.base))
        (folder / "db").mkdir()
        for name, (init, power_up, words) in shapes.items():
            head = self.HEAD.format(init=f'INIT_FILE="{init}" ' if init else "",
                                    power_up=power_up, words=words)
            (folder / "db" / name).write_text(head, encoding="utf-8")
        return folder

    def setUp(self):
        base = ROOT / "workdir/builds/rom-image-unit"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.base = self.temp.name

    def test_the_carrying_store_powers_up_holding_it_and_the_others_do_not(self):
        folder = self.megafunctions({"altsyncram_aaa1.tdf": ("preload-rom.mif", "FALSE", 65536),
                                     "altsyncram_bbb1.tdf": (None, "TRUE", 8192),
                                     "altsyncram_ccc1.tdf": (None, "TRUE", 127)})
        evidence = fpga_rom_image.verify_megafunction(folder)
        self.assertEqual(list(evidence["carrying"]), ["altsyncram_aaa1.tdf"])
        self.assertEqual(sorted(evidence["uninitialized"]), ["altsyncram_bbb1.tdf", "altsyncram_ccc1.tdf"])

    def test_the_cache_requires_the_generated_megafunctions_it_reads_back(self):
        folder = self.megafunctions({"altsyncram_aaa1.tdf": ("preload-rom.mif", "FALSE", 65536),
                                     "altsyncram_bbb1.tdf": (None, "TRUE", 8192)})
        for name in fpga_rom_image.PREPARED:
            (folder / name).write_bytes(b"")
        paths = fpga_rom_image.cache_paths(folder)
        self.assertEqual([path.relative_to(folder).as_posix() for path in paths],
                         list(fpga_rom_image.PREPARED)
                         + ["db/altsyncram_aaa1.tdf", "db/altsyncram_bbb1.tdf"])
        self.assertTrue(all(path.is_file() for path in paths))

    def test_either_state_stated_wrongly_refuses(self):
        for shapes in (
                # The carrying store still suppresses its power-up initialization.
                {"a.tdf": ("preload-rom.mif", "TRUE", 65536), "b.tdf": (None, "TRUE", 8192)},
                # A store declaring no image lost its uninitialized power-up.
                {"a.tdf": ("preload-rom.mif", "FALSE", 65536), "b.tdf": (None, "FALSE", 8192)},
                # No store, or two stores, name the image.
                {"a.tdf": (None, "TRUE", 65536), "b.tdf": (None, "TRUE", 8192)},
                {"a.tdf": ("preload-rom.mif", "FALSE", 65536), "b.tdf": ("preload-rom.mif", "FALSE", 8192)},
                # Nothing witnesses the uninitialized state.
                {"a.tdf": ("preload-rom.mif", "FALSE", 65536)}):
            names = {f"altsyncram_{name}": value for name, value in shapes.items()}
            with self.subTest(shapes=sorted(names)), self.assertRaises(ValueError):
                fpga_rom_image.verify_megafunction(self.megafunctions(names))


class FittedContentTests(unittest.TestCase):
    def test_the_fitted_blocks_hold_the_declared_image(self):
        carried = image(fill=0x5A)
        planes = fpga_rom_image.bit_planes(carried)
        self.assertEqual(len(planes), 64)
        self.assertEqual({len(plane) for plane in planes}, {8192})
        evidence = fpga_rom_image.verify_contents(netlist(planes), carried, "rom")
        self.assertEqual(evidence["blocks"], 64)

    def test_a_different_altered_or_incomplete_image_is_refused(self):
        carried = image(fill=0x5A)
        planes = fpga_rom_image.bit_planes(carried)
        for text, held in ((netlist(planes), image(fill=0xC9)),
                           (netlist(planes[:-1]), carried),
                           (netlist(planes, instance="wram"), carried),
                           ("", carried)):
            with self.subTest(blocks=text.count("init_file")), self.assertRaises(ValueError):
                fpga_rom_image.verify_contents(text, held, "rom")
        shifted = fpga_rom_image.bit_planes(b"\0" + carried[:-1])
        with self.assertRaises(ValueError):
            fpga_rom_image.verify_contents(netlist(shifted), carried, "rom")

    def test_incomplete_or_malformed_block_words_are_refused(self):
        for words in ({"mem_init0": "2048'h" + "0" * 512},
                      {"mem_init1": "2048'h" + "0" * 512, "mem_init2": "2048'h" + "0" * 512,
                       "mem_init3": "2048'h" + "0" * 512, "mem_init4": "2048'h" + "0" * 512},
                      {f"mem_init{index}": "2048'h" + "0" * 511 for index in range(4)},
                      {f"mem_init{index}": "0" * 512 for index in range(4)}):
            with self.subTest(words=sorted(words)), self.assertRaises(ValueError):
                fpga_rom_image.block_contents(words)


if __name__ == "__main__":
    unittest.main()
