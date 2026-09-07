"""The composed proof must not broaden the existing CDC exceptions."""
import unittest

from tools.n2m import fpga, fpga_v05, fpga_vga


class V05ConstraintsTests(unittest.TestCase):
    def test_only_six_first_data_stages_are_excepted(self):
        text = fpga_v05.constraints(fpga.tcl_word)
        paths = [line for line in text.splitlines() if line.startswith("set_false_path")]
        self.assertEqual(paths, [f"set_false_path -from $launch_{name} -to $first_{name}"
                                for name in ("pix_ready_sys", "sys_ready_pix", "ack_sys",
                                             "req_pix", "blank_pix", "blank_seen_sys")])
        self.assertIn("u_clocking|u_reset|pix_release", text)
        self.assertIn("u_clocking|u_reset|sys_release", text)
        self.assertNotIn('get_ports [list "reset_pix"]', text)
        self.assertNotIn('get_ports [list "reset_sys"]', text)
        self.assertNotIn("|clrn", text)
        self.assertNotIn("set_clock_groups", text)
        self.assertIn("u_system|u_bridge|offer_epoch", text)
        self.assertIn("u_system|u_bridge|captured_epoch", text)
