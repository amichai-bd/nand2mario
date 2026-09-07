"""The composed proof must not broaden the existing CDC exceptions."""
import unittest
from unittest.mock import patch

from tools.n2m import fpga, fpga_v05, fpga_vga


class V05ConstraintsTests(unittest.TestCase):
    def test_only_six_first_data_stages_are_excepted(self):
        text = fpga_v05.constraints(fpga.tcl_word)
        paths = [line for line in text.splitlines() if line.startswith("set_false_path")]
        self.assertEqual(paths, [f"set_false_path -from $launch_{name} -to $first_{name}"
                                for name in ("pix_ready_sys", "sys_ready_pix", "ack_sys",
                                             "req_pix", "blank_pix", "blank_seen_sys")])
        self.assertIn('get_ports [list "reset_pix"]', text)
        self.assertIn('get_ports [list "reset_sys"]', text)
        self.assertNotIn("u_clocking", text)
        self.assertNotIn("|clrn", text)
        self.assertNotIn("set_clock_groups", text)
        self.assertIn("u_system|u_bridge|offer_epoch", text)
        self.assertIn("u_system|u_bridge|captured_epoch", text)

    def test_changed_upstream_launch_is_rejected(self):
        original = fpga_vga.constraints(fpga.tcl_word, lcd=True)
        with patch.object(fpga_vga, "constraints", return_value=original.replace("pix_release", "renamed")):
            with self.assertRaisesRegex(ValueError, "readiness constraint profile changed"):
                fpga_v05.constraints(fpga.tcl_word)
