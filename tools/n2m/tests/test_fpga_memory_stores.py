"""Original fit fragments check rejection of broken storage evidence."""
import unittest
from pathlib import Path
import tempfile

from n2m.fpga_memory_stores import verify_netlist, verify


def fixture():
    chunks = []
    for owner, depth, starts in (("rom", 32768, list(range(8)) * 4),
                                 ("wram", 8192, range(8)), ("vram", 8192, range(8)),
                                 ("hram", 127, [0]), ("oam_low", 80, [0]),
                                 ("oam_high", 80, [0]), ("wave_ram", 16, [0])):
        for index, bit in enumerate(starts):
            name = f"{owner}|ram|auto_generated|ram_block{index}"
            ports = {"clk0": r"\clk_sys~inputclkctrl_outclk", "clk1": "gnd",
                     "clr0": "gnd", "clr1": "gnd", "portbwe": "gnd",
                     "portabyteenamasks": "1'b1", "portbbyteenamasks": "1'b1",
                     "portaaddrstall": "gnd", "portbaddrstall": "gnd"}
            chunks.append(f"fiftyfivenm_ram_block \\{name} (" + ",".join(f".{key}({value})" for key, value in ports.items()) + ");")
            params = {"operation_mode": "bidir_dual_port", "ram_block_type": "M9K",
                      "power_up_uninitialized": "true", "mixed_port_feed_through_mode": "old",
                      "port_b_address_clock": "clock0", "port_b_read_enable_clock": "clock0"}
            for port in ("a", "b"):
                params.update({f"port_{port}_logical_ram_depth": str(depth), f"port_{port}_logical_ram_width": "8",
                               f"port_{port}_data_out_clock": "none", f"port_{port}_address_clear": "none",
                               f"port_{port}_data_out_clear": "none", f"port_{port}_read_during_write_mode": "new_data_with_nbe_read",
                               f"port_{port}_data_width": "1" if depth >= 8192 else "18",
                               f"port_{port}_first_address": "0", f"port_{port}_first_bit_number": str(bit),
                               f"port_{port}_last_address": "8191" if depth >= 8192 else ("15" if depth == 16 else "127")})
            chunks += [f'defparam \\{name} .{key} = "{value}";' for key, value in params.items()]
    return "\n".join(chunks)


class StoreFitTests(unittest.TestCase):
    def test_logical_rows_and_missing_capacity(self):
        lines = []
        for owner, depth, blocks in (("rom", 32768, 32), ("wram", 8192, 8), ("vram", 8192, 8),
                                     ("hram", 127, 1), ("oam_low", 80, 1), ("oam_high", 80, 1), ("wave_ram", 16, 1)):
            fields = [f"n2m_intel_ram:{owner}|altsyncram:ram|ALTSYNCRAM", "M9K", "True Dual Port", "Single Clock",
                      str(depth), "8", str(depth), "8", "yes", "no", "yes", "no", str(depth * 8),
                      str(depth), "8", str(depth), "8", str(depth * 8), str(blocks), "None", "location",
                      "Old data", "New data with NBE Read", "New data with NBE Read"]
            lines.append("; " + " ; ".join(fields) + " ;")
        lines.append("; Total block memory bits ; 395,640 / 1,677,312 ;")
        original = "\n".join(lines)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "output").mkdir()
            (folder / "simulation/questa").mkdir(parents=True)
            (folder / "simulation/questa/design.vo").write_text(fixture())
            report = folder / "output/design.fit.rpt"
            report.write_text(original)
            self.assertEqual(len(verify(folder)["physical_atoms"]), 52)
            for changed in (original.replace("395,640", "262,144"),
                            original.replace("yes ; no ; yes ; no", "yes ; yes ; yes ; no", 1),
                            original.replace("32 ; None", "31 ; None", 1),
                            original + "\n" + lines[0], "\n".join(lines[1:])):
                report.write_text(changed)
                with self.assertRaises(ValueError):
                    verify(folder)

    def test_exact_inventory_and_mutations(self):
        original = fixture()
        self.assertEqual(len(verify_netlist(original)), 52)
        mutations = [
            original.replace("fiftyfivenm_ram_block", "other_ram_block", 1),
            original.replace("rom|ram|", "unowned|ram|"),
            original.replace("clk_sys~inputclkctrl_outclk", "other_clock", 1),
            original.replace('.port_b_read_enable_clock = "clock0"', '.port_b_read_enable_clock = "clock1"', 1),
            original.replace('.port_b_address_clock = "clock0"', '.port_b_address_clock = "clock1"', 1),
            original.replace('.port_a_data_out_clock = "none"', '.port_a_data_out_clock = "clock0"', 1),
            original.replace('.port_a_logical_ram_depth = "32768"', '.port_a_logical_ram_depth = "8192"', 1),
            original.replace('.port_a_first_bit_number = "0"', '.port_a_first_bit_number = "1"', 1),
            original.replace('.power_up_uninitialized = "true"', '.power_up_uninitialized = "false"', 1),
            original.replace(".portabyteenamasks(1'b1)", ".portabyteenamasks(1'b0)", 1),
            original.replace(".portbwe(gnd)", ".portbwe(vcc)", 1),
            original.replace(".clr0(gnd)", ".clr0(vcc)", 1),
            original + '\ndefparam \\rom|ram|auto_generated|ram_block0 .init_file = "image.mif";',
            original + '\ndefparam \\rom|ram|auto_generated|ram_block0 .ram_block_type = "M9K";',
        ]
        for index, changed in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                verify_netlist(changed)
