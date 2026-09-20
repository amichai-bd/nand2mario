"""The DE2-115 video DAC: the bit alignment, the output profile and the DAC pins.

Nothing here launches Quartus. The bit alignment is read out of the RTL and
checked against its stated requirement, the output profile is checked against the
rule the scan implements, and the fitted-result checks are exercised with original
fixtures and the mutation that proves each still refuses.
"""
import re
import tempfile
import unittest
from pathlib import Path

from tools.n2m import fpga, fpga_pll, fpga_vga, fpga_vga_dac as dac

ROOT = Path(__file__).resolve().parents[3]
PROOF = ROOT / "src/fpga/de2_115/de2_vga_proof.sv"
# The four-level shade table n2m_vga_scan drives, lightest first.
NIBBLES = (0xf, 0xa, 0x5, 0x0)


def scratch():
    directory = ROOT / "workdir/fpga-vga-dac-tests"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class BitAlignmentTests(unittest.TestCase):
    def test_repeating_the_nibble_is_the_only_map_that_keeps_both_ends_and_the_steps(self):
        """b(0)=0, b(15)=255 and equal steps force b(v) = 17v, which is {v, v}."""
        repeat = [(value << 4) | value for value in range(16)]
        self.assertEqual(repeat, [17 * value for value in range(16)])
        self.assertEqual((repeat[0], repeat[15]), (0x00, 0xff))
        steps = {repeat[i + 1] - repeat[i] for i in range(15)}
        self.assertEqual(steps, {17})
        # 255/15 is exactly 17, so no code needs rounding.
        self.assertEqual(repeat, [round(value * 255 / 15) for value in range(16)])
        # The four shades land on exact thirds of full scale.
        self.assertEqual([repeat[n] for n in NIBBLES], [0xff, 0xaa, 0x55, 0x00])

    def test_the_named_alternatives_lose_white_black_or_the_grey_scale(self):
        """Each near miss breaks one of the three requirements, and by how much."""
        alternatives = {"zero-filled": [value << 4 for value in range(16)],
                        "right-aligned": list(range(16)),
                        "one-filled": [(value << 4) | 0xf for value in range(16)]}
        # White capped at 240/255, white capped at 15/255, black lifted to 15/255.
        self.assertEqual([table[15] for table in alternatives.values()], [0xf0, 0x0f, 0xff])
        self.assertEqual([table[0] for table in alternatives.values()], [0x00, 0x00, 0x0f])
        for name, table in alternatives.items():
            with self.subTest(alternative=name):
                self.assertNotEqual((table[0], table[15]), (0x00, 0xff))

    def test_the_rtl_states_that_map_and_holds_the_dac_controls_at_their_values(self):
        """The fixture's board side is exactly the documented alignment and levels."""
        text = PROOF.read_text(encoding="utf-8")
        for channel, source in zip(dac.CHANNELS, ("red", "green", "blue")):
            self.assertIn(f"assign {channel} = {{{source}, {source}}};", text)
        self.assertIn(f"assign {dac.CLOCK_PORT} = ~clk_pix;", text)
        for port, value in dac.CONTROLS.items():
            self.assertIn(f"assign {port} = 1'b{value};", text)

    def test_the_channel_width_is_the_boards_and_every_pin_takes_its_own_replica(self):
        ports, registers = dac.DAC.ports, dac.DAC.registers
        self.assertEqual(len(ports), 3 * dac.CHANNEL_BITS + len(dac.SYNC))
        self.assertEqual(ports[-2:], list(dac.SYNC))
        self.assertEqual(len(set(registers)), len(registers))
        for index, port in enumerate(ports[:-2]):
            bit = int(re.fullmatch(r"\w+\[(\d)\]", port)[1])
            self.assertIn(f"gray_out[{bit % 2}]", registers[index])
        self.assertEqual(registers[-2:], ("u_bridge|u_scan|hs_out", "u_bridge|u_scan|vs_out"))
        # Twelve physical copies of each grayscale bit for twenty four RGB pins,
        # against the resistor ladder's six for twelve.
        self.assertEqual(len([r for r in registers if "gray_out[0]" in r]), 12)
        self.assertEqual(len(fpga_vga.LADDER.registers), 14)

    def test_the_registered_target_declares_that_profile_and_only_recorded_pins(self):
        definition = fpga.target_definition(ROOT, "de2-vga")
        self.assertEqual(definition["top"], dac.TOP)
        self.assertTrue(dac.dac_target(definition))
        self.assertEqual(set(definition["pins"]) - {"clk_reference"}, set(dac.DRIVE_PORTS))
        self.assertEqual(set(definition["io_standards"].values()), {"3.3-V LVTTL"})
        # The VGA pins live in the registry as machine-readable assignments and
        # their provenance lives only on the board page.
        self.assertEqual(len(definition["pins"]), 30)


def netlist(controls=None, clock=None):
    """An original output-buffer fixture in the shape the netlist check reads."""
    levels = {"vga_blank_n": "vcc", "vga_sync_n": "gnd", **(controls or {})}
    body = ""
    for port, level in levels.items():
        body += f"cycloneive_io_obuf \\{port}~output (\n\t.i({level}),\n\t.oe(vcc),\n\t.o(o{port}));\n"
    driver = "!" + fpga_vga.PIXEL_NET if clock is None else clock
    body += f"cycloneive_io_obuf \\{dac.CLOCK_PORT}~output (\n\t.i({driver}),\n\t.oe(vcc),\n\t.o(oclk));\n"
    return body


class FittedPinTests(unittest.TestCase):
    def folder(self, temp, text):
        folder = Path(temp)
        (folder / "simulation/questa").mkdir(parents=True)
        (folder / "simulation/questa/design.vo").write_text(text, encoding="utf-8")
        return folder

    def test_each_control_pin_must_carry_its_documented_level(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temp:
            folder = self.folder(temp, netlist())
            result = dac.verify_controls(folder)
            self.assertEqual(result["control_levels"], {"vga_blank_n": "vcc", "vga_sync_n": "gnd"})
            self.assertEqual(result["clock_driver"], "!" + fpga_vga.PIXEL_NET)
        for controls in ({"vga_blank_n": "gnd"}, {"vga_sync_n": "vcc"}, {"vga_blank_n": "othernet"}):
            with tempfile.TemporaryDirectory(dir=scratch()) as temp, self.subTest(controls=controls):
                folder = self.folder(temp, netlist(controls=controls))
                with self.assertRaisesRegex(ValueError, "documented level"):
                    dac.verify_controls(folder)

    def test_the_clock_pin_must_carry_the_inverted_pixel_clock(self):
        # A constant, the uninverted clock, and the system clock instead.
        for clock in ("gnd", "vcc", fpga_vga.PIXEL_NET, "!" + fpga_pll.SYSTEM_NET):
            with tempfile.TemporaryDirectory(dir=scratch()) as temp, self.subTest(clock=clock):
                folder = self.folder(temp, netlist(clock=clock))
                with self.assertRaisesRegex(ValueError, "inverted pixel clock"):
                    dac.verify_controls(folder)

    def test_a_missing_buffer_fails_rather_than_passing_unchecked(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temp:
            text = netlist().replace("\\vga_sync_n~output", "\\other_pin~output")
            with self.assertRaisesRegex(ValueError, "missing fitted output buffer"):
                dac.verify_controls(self.folder(temp, text))
        with tempfile.TemporaryDirectory(dir=scratch()) as temp:
            text = netlist().replace(f"\\{dac.CLOCK_PORT}~output", "\\other_pin~output")
            with self.assertRaisesRegex(ValueError, "inverted pixel clock"):
                dac.verify_controls(self.folder(temp, text))


STUCK = ('Warning (13024): Output pins are stuck at VCC or GND\n'
         '    Warning (13410): Pin "vga_blank_n" is stuck at VCC File: {source} Line: 20\n'
         '    Warning (13410): Pin "vga_sync_n" is stuck at GND File: {source} Line: 20\n')
ROUTING = ('Warning (15064): PLL "{pll}" output port clk[0] feeds output pin "{pin}~output" via '
           'non-dedicated routing -- jitter performance depends on switching rate of other design '
           'elements. Use PLL dedicated clock outputs to ensure jitter performance File: {file} '
           'Line: 51\n')


class DiagnosticBoundTests(unittest.TestCase):
    def attempt(self, temp):
        """An attempt folder with the project file and generated PLL the checks read."""
        folder = Path(temp)
        source = (ROOT / "src/fpga/de2_115/de2_vga_proof.sv").resolve().as_posix()
        (folder / "design.qsf").write_text(
            f'set_global_assignment -name SYSTEMVERILOG_FILE "{source}"\n', encoding="utf-8")
        (folder / "db").mkdir()
        (folder / "db/n2m_pixel_pll_altpll.v").write_text("", encoding="utf-8")
        return folder, source, (folder / "db/n2m_pixel_pll_altpll.v").resolve().as_posix()

    def test_the_stuck_pin_lines_are_bounded_to_that_pin_set_level_and_source(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temp:
            folder, source, _ = self.attempt(temp)
            text = STUCK.format(source=source)
            self.assertEqual([item["code"] for item in dac.stuck_diagnostics(text, folder)],
                             ["13024", "13410", "13410"])
            for before, after in (('"vga_blank_n" is stuck at VCC', '"vga_blank_n" is stuck at GND'),
                                  ('"vga_sync_n"', '"vga_hs"'),
                                  ('File: ' + source, 'File: /elsewhere/de2_vga_proof.sv'),
                                  ('Warning (13024)', 'Warning (13025)')):
                with self.subTest(change=before):
                    with self.assertRaisesRegex(ValueError, "constant identity/count differs"):
                        dac.stuck_diagnostics(text.replace(before, after, 1), folder)
            # A third stuck pin, and a missing one, both fail.
            extra = text + '    Warning (13410): Pin "vga_hs" is stuck at GND File: ' + source + ' Line: 20\n'
            with self.assertRaises(ValueError):
                dac.stuck_diagnostics(extra, folder)
            with self.assertRaises(ValueError):
                dac.stuck_diagnostics("\n".join(text.splitlines()[:2]) + "\n", folder)

    def test_the_routed_clock_line_is_bounded_to_that_pll_pin_and_generated_file(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temp:
            folder, _, generated = self.attempt(temp)
            pll = fpga_pll.MERGE_PAIR[0]
            text = ROUTING.format(pll=pll, pin=dac.CLOCK_PORT, file=generated)
            self.assertEqual([item["code"] for item in dac.clock_routing_diagnostics(text, folder, pll)],
                             ["15064"])
            for before, after in ((pll, fpga_pll.MERGE_PAIR[1]),
                                  ('"' + dac.CLOCK_PORT + '~output"', '"vga_hs~output"'),
                                  ("File: " + generated, "File: /elsewhere/n2m_pixel_pll_altpll.v"),
                                  ("clk[0]", "clk[1]")):
                with self.subTest(change=before):
                    with self.assertRaisesRegex(ValueError, "routing diagnostic identity/count differs"):
                        dac.clock_routing_diagnostics(text.replace(before, after, 1), folder, pll)
            with self.assertRaises(ValueError):
                dac.clock_routing_diagnostics(text * 2, folder, pll)
            with self.assertRaises(ValueError):
                dac.clock_routing_diagnostics("", folder, pll)


class PinClockTests(unittest.TestCase):
    def test_the_dac_clock_is_the_inverted_pixel_clock_at_its_own_port(self):
        definition = fpga.target_definition(ROOT, "de2-vga")
        clocks = fpga_pll.pin_clocks(definition)
        self.assertEqual(clocks, {dac.CLOCK_NAME: (dac.CLOCK_PORT, fpga_pll.PIXEL_CLOCK, 125 / 63)})
        inventory = fpga_pll.clock_inventory(definition, 20.0)
        self.assertEqual(inventory[dac.CLOCK_NAME],
                         ("Generated", 20.0 * 125 / 63, ["", "1", "1"], fpga_pll.PIXEL_CLOCK))
        # Every VGA target on the resistor-ladder board declares no pin clock, so
        # it accepts no output port without an output delay.
        ladder = fpga.target_definition(ROOT, "vga-nominal")
        self.assertEqual(fpga_pll.pin_clocks(ladder), {})
        self.assertFalse(fpga.accepted_clock_port_entry("no_output_delay", 1, ladder, ""))

    def test_the_clock_port_is_the_one_accepted_output_without_an_output_delay(self):
        definition = fpga.target_definition(ROOT, "de2-vga")
        row = (f"; {dac.CLOCK_PORT} ; No output delay was set on output port."
               " This port has clock assignments. ;")
        self.assertTrue(fpga.accepted_clock_port_entry("no_output_delay", 1, definition, row))
        self.assertFalse(fpga.accepted_clock_port_entry("no_output_delay", 2, definition, row))
        self.assertFalse(fpga.accepted_clock_port_entry("no_clock", 1, definition, row))
        self.assertFalse(fpga.accepted_clock_port_entry(
            "no_output_delay", 1, definition, row.replace(dac.CLOCK_PORT, "vga_hs")))


if __name__ == "__main__":
    unittest.main()
