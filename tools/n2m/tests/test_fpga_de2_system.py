"""The DE2-115 system image: its port set, its readout and its carried image's CRC.

Nothing here launches Quartus. The seven-segment decode is read out of the RTL and
checked against the polarity and index the board specification records from the
vendor manual, the registry is checked against the board's own I/O standard
record, and the fitted-result checks are exercised with original fixtures and the
mutation that proves each still refuses.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from tools.n2m import fpga, fpga_de2_system as system, fpga_rom_image, fpga_vga_dac

ROOT = Path(__file__).resolve().parents[3]
PROOF = ROOT / "src/fpga/de2_115/de2_system_proof.sv"
DIGIT = ROOT / "src/fpga/de2_115/de2_hex_digit.sv"
# Segment index to position, from wiki/src/de2-115-board.md#seven-segment-displays.
POSITIONS = ("top", "upper right", "lower right", "bottom", "lower left", "upper left", "middle")
# The lit segments of each hexadecimal glyph, as positions rather than as a mask,
# so the table below states the shape and not a restatement of the RTL's constant.
GLYPHS = {
    0x0: "top upper-right lower-right bottom lower-left upper-left",
    0x1: "upper-right lower-right",
    0x8: "top upper-right lower-right bottom lower-left upper-left middle",
}
SEGMENT_BITS = {"top": 0, "upper-right": 1, "lower-right": 2, "bottom": 3,
                "lower-left": 4, "upper-left": 5, "middle": 6}


def scratch():
    directory = ROOT / "workdir/fpga-de2-system-tests"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class ReadoutTests(unittest.TestCase):
    def test_the_decoder_lights_the_named_segments_and_drives_them_low(self):
        """Each glyph's lit set is the board's segment indices, inverted at the pin."""
        text = DIGIT.read_text(encoding="utf-8")
        for value, lit in GLYPHS.items():
            mask = sum(1 << SEGMENT_BITS[name] for name in lit.split())
            with self.subTest(value=value):
                self.assertIn(f"4'h{value:x}: lit = 7'h{mask:02x};", text)
        # One place states the polarity, and it is the manual's: low lights up.
        self.assertIn("assign segments_n = ~lit;", text)
        self.assertEqual(len(POSITIONS), system.SEGMENTS)

    def test_every_switch_position_selects_a_defined_view(self):
        """Three switch bits and eight stated selections, so no position is undefined."""
        text = PROOF.read_text(encoding="utf-8")
        selections = re.findall(r"(?m)^\s+3'd(\d): view_value = ", text)
        self.assertEqual(selections, [str(index) for index in range(8)])
        # The four identity views are the whole 128-bit constant, in order.
        for index, (high, low) in enumerate(((127, 96), (95, 64), (63, 32), (31, 0))):
            self.assertIn(f"3'd{index}: view_value = BUILD_ID[{high}:{low}];", text)
        self.assertIn(f"3'd4: view_value = {system.CRC_PARAMETER};", text)
        # The two counter views are system-domain, so the readout register adds
        # no crossing from the pixel domain it is not clocked in.
        self.assertIn("3'd5: view_value = dot_count[31:0];", text)
        self.assertIn("3'd6: view_value = epoch;", text)
        self.assertNotIn("view_value = display_sequence", text)
        self.assertNotIn("view_value = display_epoch", text)

    def test_the_most_significant_digit_takes_the_most_significant_nibble(self):
        """Digit d shows nibble d, so HEX7 carries bits 31 to 28."""
        text = PROOF.read_text(encoding="utf-8")
        for digit in range(system.DIGITS):
            high, low = digit * 4 + 3, digit * 4
            with self.subTest(digit=digit):
                self.assertIn(f"de2_hex_digit u_hex{digit} (.value(view_q[{high}:{low}])", text)


class TerminationTests(unittest.TestCase):
    def test_each_absent_interface_is_driven_to_its_inactive_value(self):
        """A board someone programs leaves no input of the composition floating."""
        text = PROOF.read_text(encoding="utf-8")
        # The UART line's idle mark, so no noise can begin a frame.
        self.assertIn(".uart_rx(1'b1), .uart_tx(),", text)
        # The menu-return button released: this image has no library to return to.
        self.assertIn(".key1_n(1'b1),", text)
        # No storage, so nothing is initialized and no request is ever accepted.
        self.assertIn(".sdram_initialized(1'b0)", text)
        self.assertIn(".sdram_request_ready(1'b0)", text)
        self.assertIn(".sdram_response_valid(1'b0), .sdram_response_data('0)", text)
        # No SDRAM pin is placed, so the board's devices meet reserved inputs.
        self.assertFalse([port for port in system.PLACED if port.startswith("DRAM_")])


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.target = fpga.target_definition(ROOT, "de2-system")

    def test_the_target_places_this_board_s_control_picture_and_readout_pins(self):
        self.assertEqual(set(self.target["pins"]), system.PLACED)
        self.assertEqual(set(self.target["virtual_pins"]), system.VIRTUAL)
        self.assertEqual(len(system.HEX_PORTS), system.DIGITS * system.SEGMENTS)
        self.assertEqual(len(system.PLACED), 100)

    def test_the_readout_declares_both_voltages_this_board_supplies_for_it(self):
        """The seven-segment group is not one standard, and the registry says so."""
        standards = {port: self.target["io_standards"][port] for port in system.HEX_PORTS}
        self.assertEqual(set(standards.values()), {"2.5 V", "3.3-V LVTTL"})
        # The vendor fixes HEX7[6] at 3.3 V where its six siblings depend on JP6,
        # whose default is also 3.3 V, so the whole digit declares one standard.
        self.assertEqual(standards["hex7_n[6]"], "3.3-V LVTTL")
        # HEX0 and HEX3 are the two digits whose pins cross a supply boundary in
        # the vendor table; both sides default to the same voltage on HEX0 and not
        # on HEX3, which is why each pin carries its own record.
        self.assertEqual({standards[f"hex0_n[{bit}]"] for bit in range(7)}, {"2.5 V"})
        self.assertEqual({standards[f"hex3_n[{bit}]"] for bit in range(7)},
                         {"2.5 V", "3.3-V LVTTL"})

    def test_each_readout_pin_states_the_output_settings_its_own_standard_needs(self):
        """Cyclone IV E wants a slew rate on 2.5 V and only drive strength on 3.3 V."""
        with tempfile.TemporaryDirectory(dir=scratch()) as folder:
            folder = Path(folder)
            (folder / "preload.json").write_text(json.dumps({"image_crc32": 0x1234abcd}))
            fpga.prepare(ROOT, folder, self.target, build_id="f" * 32)
            qsf = (folder / "design.qsf").read_text(encoding="utf-8")
        for port in ("hex0_n[0]", "hex7_n[6]", "vga_clk"):
            word = fpga.tcl_word(port)
            self.assertIn(f'set_instance_assignment -name CURRENT_STRENGTH_NEW "8MA" -to {word}', qsf)
        # The 2.5 V digits state a slew rate; the 3.3-V LVTTL ones must not.
        self.assertIn(f'set_instance_assignment -name SLEW_RATE 1 -to {fpga.tcl_word("hex0_n[0]")}', qsf)
        self.assertNotIn(f'set_instance_assignment -name SLEW_RATE 1 -to {fpga.tcl_word("hex7_n[6]")}', qsf)
        self.assertEqual(sum(1 for line in qsf.splitlines() if line.startswith("set_instance_assignment -name SLEW_RATE")),
                         sum(1 for port in system.DRIVE_PORTS if self.target["io_standards"][port] == "2.5 V"))
        # This image drives no bus of its own, so every pin it leaves is an input.
        self.assertIn('set_global_assignment -name RESERVE_ALL_UNUSED_PINS "AS INPUT TRI-STATED"', qsf)

    def test_a_readout_pin_the_board_record_does_not_name_refuses_the_build(self):
        """Moving one readout pin off this board's record names it, before any tool.

        This is mutated in memory rather than registered, because every consumer
        that walks the registry reads each target's definition, so a target that
        cannot be defined would fail the Questa compile gate's own enumeration
        instead of the build it is the control for.
        """
        registry = ROOT / "src/fpga/de2_115/targets.json"
        original = registry.read_text(encoding="utf-8")
        text = json.loads(original)
        text["targets"]["de2-system"]["pins"]["hex7_n[6]"] = "PIN_AA13"
        self.assertNotIn("PIN_AA13", [pin for pins in text["board"]["io_standards"].values() for pin in pins])
        try:
            registry.write_text(json.dumps(text, indent=2) + "\n", encoding="utf-8")
            fpga.board_registries.cache_clear() if hasattr(fpga.board_registries, "cache_clear") else None
            with self.assertRaises(ValueError) as raised:
                fpga.target_definition(ROOT, "de2-system")
        finally:
            registry.write_text(original, encoding="utf-8")
            fpga.board_registries.cache_clear() if hasattr(fpga.board_registries, "cache_clear") else None
        self.assertIn("hex7_n[6]", str(raised.exception))
        self.assertIn("no recorded I/O standard", str(raised.exception))

    def test_the_negative_control_understates_the_readout_s_endpoint_count(self):
        """de2-system-invalid is definable and fails on the builder's own check.

        The readout is 56 pins and the two status outputs, so the constrained
        endpoint count is the figure most easily left stale when a pin is added or
        dropped. The control declares one fewer, so the generated collection check
        fails by name and a passing de2-system fit is evidence that every readout
        pin is constrained rather than an absent check.
        """
        invalid = fpga.target_definition(ROOT, "de2-system-invalid")
        self.assertEqual(invalid["pins"], self.target["pins"])
        self.assertEqual(invalid["sources"], self.target["sources"])
        good, bad = (entry["timing"]["output_delays"][0]["count"]
                     for entry in (self.target, invalid))
        self.assertEqual((good, bad), (len(system.HEX_PORTS) + 2, len(system.HEX_PORTS) + 1))
        self.assertIn('error "checked endpoint count mismatch: ports_0"',
                      fpga.checked_constraints(invalid))

    def test_a_missing_or_moved_board_port_refuses_before_any_tool_runs(self):
        for change in ({"hex3_n[3]": None}, {"vga_clk": None}, {"sw_view[2]": None}):
            target = dict(self.target, pins={port: pin for port, pin in self.target["pins"].items()
                                             if port not in change})
            with self.subTest(change=sorted(change)):
                with self.assertRaises(ValueError):
                    system.validate(target)
        with self.assertRaises(ValueError):
            system.validate(dict(self.target, virtual_pins=[*system.VIRTUAL, "paused_extra"]))

    def test_the_carried_rom_reaches_the_store_instance_inside_the_composition(self):
        """The ROM store is several levels below this top, and the QSF names it."""
        self.assertEqual(fpga_rom_image.rom_path(system.TOP), "u_system|u_stores|rom")
        self.assertEqual(fpga_rom_image.store_init_files(self.target),
                         {"rom": fpga_rom_image.MIF_NAME})


class CarriedCrcTests(unittest.TestCase):
    """The displayed CRC is the packaged image's, in the project and as compiled."""

    VALUE = 0x89abcdef

    def attempt(self, folder, *, crc=VALUE, macro=None, compiled=None):
        folder = Path(folder)
        (folder / "preload.json").write_text(json.dumps({"image_crc32": crc}))
        line = macro if macro is not None else system.assignments(folder)[0]
        (folder / "design.qsf").write_text("set_global_assignment -name DEVICE EP4CE115F29C7\n" + line + "\n")
        report = (folder / "output")
        report.mkdir(exist_ok=True)
        bits = f"{crc if compiled is None else compiled:032b}"
        (report / "design.map.rpt").write_text(
            f"; {system.CRC_PARAMETER} ; {bits} ; Unsigned Binary ;\n")
        return folder

    def test_the_project_and_the_compiled_constant_are_the_packaged_image_s_crc(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as folder:
            folder = self.attempt(folder)
            self.assertEqual(system.verify_rom_crc(folder), f"{self.VALUE:08x}")

    def test_a_project_macro_naming_another_value_refuses(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as folder:
            folder = self.attempt(folder, macro=f'set_global_assignment -name VERILOG_MACRO "{system.CRC_MACRO}=32\'h00000000"')
            with self.assertRaises(ValueError):
                system.verify_rom_crc(folder)

    def test_a_compiled_constant_naming_another_value_refuses(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as folder:
            folder = self.attempt(folder, compiled=self.VALUE ^ 1)
            with self.assertRaises(ValueError):
                system.verify_rom_crc(folder)

    def test_a_duplicated_macro_refuses(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as folder:
            folder = self.attempt(folder)
            qsf = folder / "design.qsf"
            qsf.write_text(qsf.read_text() + system.assignments(folder)[0] + "\n")
            with self.assertRaises(ValueError):
                system.verify_rom_crc(folder)

    def test_a_record_without_a_thirty_two_bit_crc_refuses(self):
        for value in (-1, 1 << 32, "89abcdef"):
            with tempfile.TemporaryDirectory(dir=scratch()) as folder:
                (Path(folder) / "preload.json").write_text(json.dumps({"image_crc32": value}))
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        system.image_crc(folder)


class ChainTests(unittest.TestCase):
    def test_every_asynchronous_control_input_has_its_own_checked_chain(self):
        """Twelve control inputs, each named to the filter instance that samples it."""
        ports = [port for _, port, _, _ in system.CHAINS]
        self.assertEqual(sorted(ports), sorted(port for port in system.CONTROL_PORTS
                                               if port != "board_reset_n"))
        self.assertEqual(len(set(name for name, _, _, _ in system.CHAINS)), len(system.CHAINS))
        for name, port, first, second in system.CHAINS:
            with self.subTest(chain=name):
                self.assertTrue(first.endswith(second.split("|")[-1].replace("sync", "meta"))
                                or "button_meta" in first)
                self.assertEqual(first.split("|")[0], second.split("|")[0])
        # The reset is not a chain here: the reset control owns its own.
        self.assertNotIn("board_reset_n", ports)

    def test_the_composed_collections_name_this_image_s_hierarchy(self):
        """Every shared pixel-path string is rewritten one level down, and only there."""
        text = system.constraints(fpga.tcl_word)
        self.assertIn(system.BRIDGE_PREFIX, text)
        self.assertNotIn("{u_bridge|", text)
        self.assertEqual(system.hierarchy("u_bridge|u_scan|hs_out"), "u_system|u_bridge|u_scan|hs_out")
        # The DAC's eight-bit profile, not the DE10-Lite's four-bit ladder.
        self.assertEqual(fpga_vga_dac.CHANNEL_BITS, 8)
        for port in fpga_vga_dac.DAC.ports:
            self.assertIn(port, system.DRIVE_PORTS)


if __name__ == "__main__":
    unittest.main()
