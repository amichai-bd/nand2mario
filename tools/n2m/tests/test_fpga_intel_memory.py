"""Original report fragments exercise the physical RAM checker, not hardware."""
import unittest

from n2m.fpga_intel_memory import verify_netlist, SYS_CLOCK, PIX_CLOCK


def fixture():
    chunks = []
    for owner, depth, width, starts in (("byte_ram", 160, 8, [0]),
                                       ("pair_ram", 80, 16, [0]),
                                       ("lanes_ram", 64, 32, [0, 16]),
                                       ("frame_ram", 23040, 2, [0, 0, 0, 1, 1, 1])):
        dual = owner == "frame_ram"
        for index, first in enumerate(starts):
            name = f"{owner}|ram|auto_generated|ram_block{index}"
            bits = 1 if dual else min(width, 16)
            data = ",".join(rf"\a_wdata[{bit}]~input0 " for bit in reversed(range(first, first + bits)))
            lanes = [0] if width == 8 else ([0, 0] if width == 16 else [first // 8 + 1, first // 8])
            mask = "1'b1" if dual else "{" + ",".join(rf"\a_byte_enable[{bit}]~input0 " for bit in lanes) + "}"
            ports = {"clk0": SYS_CLOCK, "clk1": PIX_CLOCK if dual else "gnd", "clr0": "gnd", "clr1": "gnd",
                     "portbwe": "gnd", "portbbyteenamasks": "1'b1", "portadatain": "{" + data + "}", "portabyteenamasks": mask}
            chunks.append(f"fiftyfivenm_ram_block \\{name} (" + ",".join(f".{key}({value})" for key, value in ports.items()) + ");")
            params = {"operation_mode": "bidir_dual_port", "ram_block_type": "M9K", "power_up_uninitialized": "true",
                      "mixed_port_feed_through_mode": "dont_care" if dual else "old", "port_a_first_bit_number": str(first),
                      "port_b_address_clock": "clock1" if dual else "clock0", "port_b_read_enable_clock": "clock1" if dual else "clock0"}
            for port in ("a", "b"):
                params.update({f"port_{port}_logical_ram_depth": str(depth), f"port_{port}_logical_ram_width": str(width),
                               f"port_{port}_data_out_clock": "none", f"port_{port}_address_clear": "none",
                               f"port_{port}_data_out_clear": "none", f"port_{port}_read_during_write_mode": "new_data_with_nbe_read"})
            chunks += [f'defparam \\{name} .{key} = "{value}";' for key, value in params.items()]
    return "\n".join(chunks)


class IntelFitTests(unittest.TestCase):
    def test_physical_shapes_and_mutations(self):
        original = fixture()
        self.assertEqual(len(verify_netlist(original)), 10)
        mutations = [
            original.replace("fiftyfivenm_ram_block", "unsupported_ram_block", 1),
            original.replace(SYS_CLOCK, PIX_CLOCK, 1),
            original.replace('.port_b_address_clock = "clock1"', '.port_b_address_clock = "clock0"', 1),
            original.replace('.port_b_read_enable_clock = "clock1"', '.port_b_read_enable_clock = "clock0"', 1),
            original.replace('.port_a_data_out_clock = "none"', '.port_a_data_out_clock = "clock0"', 1),
            original.replace('.port_b_data_out_clock = "none"', '.port_b_data_out_clock = "clock1"', 1),
            original.replace('.power_up_uninitialized = "true"', '.power_up_uninitialized = "false"', 1),
            original.replace('.mixed_port_feed_through_mode = "dont_care"', '.mixed_port_feed_through_mode = "old"', 1),
            original.replace(".portbwe(gnd)", ".portbwe(vcc)", 1),
            original.replace(".clr0(gnd)", ".clr0(vcc)", 1),
            original.replace(r"\a_byte_enable[3]~input0", r"\a_byte_enable[2]~input0", 1),
            original.replace(r"\a_wdata[31]~input0", r"\a_wdata[30]~input0", 1),
            original + '\ndefparam \\byte_ram|ram|auto_generated|ram_block0 .init_file = "image.mif";',
        ]
        for index, changed in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                verify_netlist(changed)


if __name__ == "__main__":
    unittest.main()
