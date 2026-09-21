"""Every registered target's constraints select ports that target declares.

Quartus does not fail a filter matching no port; it ignores the constraint and
prints `Warning (332174)`. So a constraint that never applies looks like a
passing design until the builder refuses the warning, minutes into a fit, and a
suppressed warning would look like a passing design for good. `controls.sdc` was
shared by two tops, one of which declares KEY1 and the SDRAM ports and one of
which declares neither, and no host could build `controls-board`
([#904](https://github.com/amichai-bd/nand2mario/issues/904)).

Nothing measured that. A MAX 10 fit costs minutes and a tool no hosted runner
has, the target is in no CI workflow, and a
[regression subset](../../../wiki/tools/n2m/SPEC.md#regression-subsets) takes
catalogue simulation targets only, so no subset can hold an FPGA target at all.
The mismatch is decidable from the two registries and the constraint files, which
is what this unit reads, for every registered target rather than for named ones.
"""
import copy
import unittest
from unittest.mock import patch

from tools.n2m import fpga
from tools.n2m.tests.test_fpga_adc import ROOT, registered_targets

# The pair the shared file split into. `v05_controls_proof` declares KEY1 and the
# eleven SDRAM ports; `controls_proof` declares none of them.
SHARED = "src/fpga/de10_lite/v05_controls.sdc"
SDRAM_PORTS = ["DRAM_CLK", "DRAM_DQ[*]", "DRAM_ADDR[*]", "DRAM_BA[*]", "DRAM_CAS_N",
               "DRAM_CKE", "DRAM_CS_N", "DRAM_DQML", "DRAM_DQMH", "DRAM_RAS_N", "DRAM_WE_N"]


def declared_ports(target):
    """The ports this target places: its pins and its virtual pins."""
    return [*target["pins"], *target["virtual_pins"]]


class SdcPortFilterTests(unittest.TestCase):
    def test_every_registered_target_constrains_only_its_own_ports(self):
        """No registered target names a port it does not declare, on any board.

        The sweep is every target of every registry in `fpga.REGISTRIES`, so a
        fourth board is covered when its registry joins that tuple.
        """
        for name, target in registered_targets():
            ports = declared_ports(target)
            for constraint in target["constraints"]:
                text = (ROOT / constraint).read_text(encoding="utf-8")
                with self.subTest(target=name, constraints=constraint):
                    # A file selecting no port would pass vacuously, so require one.
                    self.assertTrue(fpga.sdc_port_filters(text))
                    self.assertEqual(fpga.unmatched_sdc_ports(text, ports), [])

    def test_the_split_file_is_one_the_controls_proof_cannot_carry(self):
        """Why the pair has two files: the difference is twelve ports, not a preference.

        Read from the live file, so re-pointing `controls-board` at it fails here
        rather than in a fit.
        """
        targets = dict(registered_targets())
        text = (ROOT / SHARED).read_text(encoding="utf-8")
        self.assertEqual(targets["v05-controls-board"]["constraints"], [SHARED])
        self.assertEqual(fpga.unmatched_sdc_ports(text, declared_ports(targets["v05-controls-board"])), [])
        self.assertEqual(fpga.unmatched_sdc_ports(text, declared_ports(targets["controls-board"])),
                         ["key1_n", *SDRAM_PORTS])

    def test_the_builder_refuses_the_mismatch_before_running_a_tool(self):
        """`target_definition` names the target's top and the ports it lacks."""
        entries = copy.deepcopy(fpga.board_registries(ROOT))
        path, board, raw = entries["controls-board"]
        entries["controls-board"] = (path, board, {**raw, "constraints": [SHARED]})
        with patch.object(fpga, "board_registries", return_value=entries):
            with self.assertRaisesRegex(ValueError, r"constraints name ports controls_proof does not declare.*key1_n"):
                fpga.target_definition(ROOT, "controls-board")
            # The definition the registry actually holds still resolves.
            self.assertEqual(fpga.target_definition(ROOT, "v05-controls-board")["constraints"], [SHARED])


class SdcPortFilterSyntaxTests(unittest.TestCase):
    def test_a_name_matches_a_declared_port_through_either_wildcard(self):
        """`*` in a filter and `[*]` in a virtual pin both stand for a real port."""
        ports = ["buttons_n[0]", "buttons_n[3]", "DRAM_ADDR[0]", "DRAM_ADDR[12]",
                 "oam_request.read", "display_sequence[*]"]
        for name in ("buttons_n*", "buttons_n[0]", "DRAM_ADDR[*]", "oam_request*",
                     "oam_request.read", "display_sequence[7]"):
            with self.subTest(name=name):
                self.assertEqual(fpga.unmatched_sdc_ports(f"create_clock -period 1 [get_ports {{{name}}}]", ports), [])
        # A bit outside the declared range is a filter matching no port as well.
        for name in ("DRAM_ADDR[13]", "buttons_n", "oam_response.valid"):
            with self.subTest(name=name):
                self.assertEqual(fpga.unmatched_sdc_ports(f"create_clock -period 1 [get_ports {{{name}}}]", ports), [name])

    def test_filters_are_collected_once_in_first_use_order(self):
        text = ("# comment [get_ports ignored]\n"
                "create_clock -name c -period 20.000 [get_ports clk]\n"
                "set_input_delay -clock c -max 1.0 [get_ports {rst clk}]\n")
        self.assertEqual(fpga.sdc_port_filters(text), ["clk", "rst"])

    def test_an_option_or_an_unreadable_filter_is_refused(self):
        """`-nowarn` would hide the ignored constraint instead of correcting it."""
        for line, message in (
                ("set_input_delay -clock c -max 1.0 [get_ports -nowarn key1_n]", "get_ports option: -nowarn"),
                ("set_input_delay -clock c -max 1.0 [get_ports -nowarn {key1_n rst}]", "get_ports option: -nowarn"),
                ("set_input_delay -clock c -max 1.0 [get_ports [list key1_n]]", "get_ports filter syntax"),
                ("set_input_delay -clock c -max 1.0 [get_ports]", "get_ports filter syntax")):
            with self.subTest(line=line):
                with self.assertRaisesRegex(ValueError, message):
                    fpga.sdc_port_filters(line)


if __name__ == "__main__":
    unittest.main()
