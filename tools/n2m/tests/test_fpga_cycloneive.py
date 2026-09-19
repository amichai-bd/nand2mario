"""Cyclone IV E clocking evidence: what the family changes, and what it still checks.

The point of this family is reuse, so most of these tests show the shared ALTPLL
checks accepting the same abstract fixtures the MAX 10 tests use. The rest pin
down the four facts that are genuinely this family's, each with the mutation that
proves the check still refuses the other family's value.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.n2m import fpga, fpga_clocking, fpga_lock, fpga_pll, fpga_pll_cycloneive as ce
from tools.n2m.tests import test_fpga_clocking as clocking_fixtures
from tools.n2m.tests import test_fpga_parallel as parallel_fixtures
from tools.n2m.tests import vendor_support

ROOT = Path(__file__).resolve().parents[3]
TOP = "de2_clocking_proof"
PIXEL_INSTANCE, SYSTEM_INSTANCE = ce.FIT_INSTANCES


def scratch():
    directory = ROOT / "workdir/fpga-cycloneive-tests"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def generated_module(folder, name, family, **overrides):
    """One generated ALTPLL wrapper in the shape the parameter check accepts."""
    values = {"clk0_divide_by": "125", "clk0_multiply_by": "63", "clk0_duty_cycle": "50",
              "clk0_phase_shift": '"0"', "inclk0_input_frequency": "20000",
              "intended_device_family": '"' + family + '"', "operation_mode": '"NORMAL"',
              "compensate_clock": '"CLK0"', "self_reset_on_loss_lock": '"OFF"',
              "port_areset": '"PORT_USED"', "port_locked": '"PORT_USED"', **overrides}
    body = "".join(f"\taltpll_component.{key} = {value},\n" for key, value in values.items())
    (folder / (name + ".v")).write_text(f"module {name} (inclk0, areset, c0, locked);\n{body}endmodule\n",
                                        encoding="utf-8")


def generated_pair(folder, family):
    """Both generated instances of the contract definition, for this family."""
    generated_module(folder, "n2m_pixel_pll", family)
    generated_module(folder, "n2m_system_pll", family, clk0_divide_by="2", clk0_multiply_by="1",
                     bandwidth_type='"LOW"')
    return folder


class DispatchTests(unittest.TestCase):
    def test_the_family_resolves_to_this_module(self):
        self.assertIs(fpga_clocking.implementation("Cyclone IV E"), ce)
        self.assertEqual(fpga_clocking.IMPLEMENTATIONS["Cyclone IV E"], "fpga_pll_cycloneive")

    def test_adding_a_third_family_did_not_make_the_dispatch_permissive(self):
        """A family without an implementation still refuses, spelling included."""
        for family in ("Cyclone IV", "Cyclone IV GX", "cyclone iv e", "Cyclone IV E ", "", None):
            with self.subTest(family=family), self.assertRaises(ValueError) as error:
                fpga_clocking.implementation(family)
            self.assertIn("no clocking evidence implementation for FPGA family", str(error.exception))

    def test_only_the_contract_definition_is_accepted(self):
        ce.validate(ce.DEFINITION)
        single = {k: v for k, v in ce.DEFINITION.items() if k != "system_divide"}
        for bad in (single, {**ce.DEFINITION, "multiply": 64}, {**ce.DEFINITION, "system_divide": 3}, {}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ce.validate(bad)

    def test_the_registered_targets_resolve_and_declare_the_boards_corners(self):
        board = json.loads((ROOT / "src/fpga/de2_115/targets.json").read_text(encoding="utf-8"))["board"]
        for name in ("de2-clocking", "de2-clocking-invalid"):
            with self.subTest(target=name):
                definition = fpga.target_definition(ROOT, name)
                self.assertEqual(definition["family"], ce.FAMILY)
                self.assertEqual(definition["top"], TOP)
                self.assertEqual(definition["timing_corners"], board["timing_corners"])
                self.assertEqual(ce.lock_event_count(definition), 2)
                self.assertEqual(ce.timed_clocks(definition),
                                 ("clk_reference", ce.SYSTEM_CLOCK, ce.PIXEL_CLOCK))
                self.assertEqual(ce.corner_slacks(definition, board["timing_corners"][0]), [])

    def test_the_broken_companion_names_another_familys_clock(self):
        """The negative control is a wrong endpoint, not a weakened check."""
        good = fpga.target_definition(ROOT, "de2-clocking")["timing"]["output_delays"]
        bad = fpga.target_definition(ROOT, "de2-clocking-invalid")["timing"]["output_delays"]
        self.assertEqual(good[0]["clock"], ce.SYSTEM_CLOCK)
        self.assertNotEqual(bad[0]["clock"], ce.SYSTEM_CLOCK)
        self.assertIn("cyclonev_pll", bad[0]["clock"])
        self.assertEqual(good[1:], bad[1:])

    def test_an_unsupported_top_is_refused(self):
        self.assertEqual(ce.SUPPORTED_TOPS, (TOP,))
        for top in ("clocking_proof", "nano_clocking_proof", "de2_smoke"):
            with self.subTest(top=top):
                with self.assertRaises(ValueError):
                    ce.lock_event_count({"top": top})
                with self.assertRaises(ValueError):
                    ce.verify_lock_event(None, "", top, parallel=True)


class GenerationTests(unittest.TestCase):
    """The generator and the generated HDL state this family, not the other one."""

    IDENTITY = {"generator": {"path": "/quartus/bin/qmegawiz"}}

    def test_the_generator_is_told_this_family(self):
        command = ce.generation_command(self.IDENTITY, ce.DEFINITION)
        self.assertIn("INTENDED_DEVICE_FAMILY=Cyclone IV E", command)
        self.assertIn("INTENDED_DEVICE_FAMILY=MAX 10",
                      fpga_pll.generation_command(self.IDENTITY, ce.DEFINITION))
        # Everything else is ALTPLL's, so the two commands differ in that one word.
        mine = [word for word in command if not word.startswith("INTENDED_DEVICE_FAMILY=")]
        theirs = [word for word in fpga_pll.generation_command(self.IDENTITY, ce.DEFINITION)
                  if not word.startswith("INTENDED_DEVICE_FAMILY=")]
        self.assertEqual(mine, theirs)

    def generated(self, family):
        return generated_pair(Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch()))), family)

    def test_the_generated_hdl_must_state_this_family(self):
        ce.verify(self.generated("Cyclone IV E"))

    def test_the_other_familys_generated_hdl_is_refused_both_ways(self):
        """The family string is checked, not swept into a family-neutral match."""
        with self.assertRaisesRegex(ValueError, "intended_device_family"):
            ce.verify(self.generated("MAX 10"))
        with self.assertRaisesRegex(ValueError, "intended_device_family"):
            fpga_pll.verify(self.generated("Cyclone IV E"), ce.DEFINITION)
        # And each family accepts its own, from the same shared checker.
        fpga_pll.verify(self.generated("MAX 10"), ce.DEFINITION)

    def test_the_fingerprint_names_this_familys_atom_model(self):
        self.assertEqual(ce.ATOM_MODEL, "eda/sim_lib/cycloneive_atoms.v")
        self.assertNotEqual(ce.ATOM_MODEL, fpga_pll.ATOM_MODEL)
        root = Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch())))
        vendor_support.installation(root)
        vendor_support.ledger(self, root / "ledger.json")
        quartus = root / "quartus"
        for relative in ("bin/qmegawiz", "libraries/megafunctions/xml_info/altpll_info.xml",
                         "libraries/megafunctions/altpll.tdf", "libraries/megafunctions/xml_info/altpll_rules.xml",
                         "libraries/megafunctions/xml_info/altpll_wiz_map.xml",
                         "eda/sim_lib/altera_primitives.v", "eda/sim_lib/cycloneive_atoms.v",
                         "eda/sim_lib/fiftyfivenm_atoms.v"):
            path = quartus / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative, encoding="utf-8")
        with patch.object(fpga_pll, "generator", return_value=quartus / "bin/qmegawiz"):
            mine = ce.identity(quartus / "bin")
            theirs = fpga_pll.identity(quartus / "bin")
        self.assertTrue(mine["atom_model"]["path"].endswith("cycloneive_atoms.v"))
        self.assertEqual(mine["atom_model"]["source"], "quartus/" + ce.ATOM_MODEL)
        self.assertTrue(theirs["atom_model"]["path"].endswith("fiftyfivenm_atoms.v"))
        self.assertEqual(theirs["atom_model"]["source"], "quartus/" + fpga_pll.ATOM_MODEL)
        self.assertNotEqual(mine["atom_model"]["sha256"], theirs["atom_model"]["sha256"])
        # The ledger records each family's atom model as its own accepted source.
        recorded = json.loads((root / "ledger.json").read_text(encoding="utf-8"))
        sources = recorded["installations"]["linux"]["sources"]
        self.assertEqual(sources["quartus/" + ce.ATOM_MODEL], mine["atom_model"]["sha256"])
        self.assertEqual(sources["quartus/" + fpga_pll.ATOM_MODEL], theirs["atom_model"]["sha256"])
        # Every other dependency is the same installed file for both families.
        for name in ("generator", "definition", "primitive", "register_model", "rules", "wizard"):
            with self.subTest(dependency=name):
                self.assertEqual({k: mine[name][k] for k in ("path", "sha256", "source")},
                                 {k: theirs[name][k] for k in ("path", "sha256", "source")})
        # A family whose atom model is not installed refuses instead of substituting one.
        (quartus / "eda/sim_lib/cycloneive_atoms.v").unlink()
        with patch.object(fpga_pll, "generator", return_value=quartus / "bin/qmegawiz"):
            with self.assertRaises(ValueError):
                ce.identity(quartus / "bin")


class FitEvidenceTests(unittest.TestCase):
    """The parallel fit and clock inventory checks are shared, and they are exact."""

    def folder(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch())))
        output = folder / "output"
        output.mkdir()
        (output / "design.fit.rpt").write_text(clocking_fixtures.parallel_fit(), encoding=ce.FIT_ENCODING)
        (output / "design.sta.rpt").write_text(clocking_fixtures.parallel_sta(), encoding="utf-8")
        (output / "design.fit.summary").write_text("Total PLLs : 2 / 4 ( 50 % )\n", encoding="utf-8")
        for name in ce.required_reports():
            path = output / name
            if name.startswith("chain_"):
                chain, check = name.removeprefix("chain_").removesuffix(".rpt").rsplit("_", 1)
                path.write_text(f"Report Timing: Found 1 {check} paths (0 violated).  Worst case slack is 0.500\n"
                                f"u_reset|{chain}[0] -> u_reset|{chain}[1]\n", encoding="utf-8")
            else:
                path.write_text("synthetic report\n", encoding="utf-8")
        return folder

    def target(self):
        return {"pll": ce.DEFINITION, "timing": {"reference_ns": "20.000"}, "top": TOP}

    def test_the_shared_parallel_fit_check_is_what_this_family_uses(self):
        folder = self.folder()
        ce.verify_fit(folder, self.target())
        self.assertIs(ce.FIT_ENCODING, fpga_clocking.FIT_ENCODING)

    def test_a_different_solved_counter_or_rate_still_fails(self):
        for wrong, message in ((("25.2 MHz", "25.1 MHz"), "rate"), (("; 63 ;", "; 64 ;"), "M value"),
                               (("Dedicated Pin", "Global Clock"), "Inclk0")):
            with self.subTest(message=message):
                folder = self.folder()
                path = folder / "output/design.fit.rpt"
                text = path.read_text(encoding=ce.FIT_ENCODING).replace(*wrong)
                path.write_text(text, encoding=ce.FIT_ENCODING)
                with self.assertRaises(ValueError):
                    ce.verify_fit(folder, self.target())

    def test_the_reset_chain_reports_are_the_family_neutral_inventory(self):
        self.assertEqual(tuple(ce.CHAINS), tuple(fpga_clocking.CHAINS))
        self.assertEqual(ce.required_reports(), fpga_clocking.required_reports())
        fpga_clocking.verify_reports(self.folder(), "reset chain")


class LockEvidenceTests(unittest.TestCase):
    """One abstract topology, two families: only the atom names differ."""

    def fixture(self, primitives=ce.PRIMITIVES):
        return parallel_fixtures.fixture(primitives)

    def verify(self, text, checks, primitives=ce.PRIMITIVES):
        return fpga_lock.verify_parallel(text, checks, TOP, primitives=primitives)

    def test_this_familys_atoms_carry_the_same_lock_qualification(self):
        text, checks = self.fixture()
        self.assertIn("cycloneive_pll", text)
        self.assertNotIn("fiftyfivenm", text)
        result = self.verify(text, checks)
        self.assertEqual(result["truth_cases"], 32)
        self.assertEqual(result["endpoints"][0], fpga_lock.ROW)
        self.assertEqual(result["sampling_clock"], ce.SYSTEM_NET)

    def test_the_max10_table_still_refuses_this_familys_netlist(self):
        """The table is what makes the check family-specific; it did not go neutral."""
        text, checks = self.fixture()
        with self.assertRaisesRegex(ValueError, "unsupported vendor primitive type"):
            self.verify(text, checks, primitives=fpga_lock.MAX10)
        max10_text, max10_checks = self.fixture(fpga_lock.MAX10)
        with self.assertRaises(ValueError):
            self.verify(max10_text, max10_checks)
        self.assertEqual(fpga_lock.verify_parallel(max10_text, max10_checks, "clocking_proof")["truth_cases"], 32)

    def test_a_primitive_this_family_has_not_declared_fails(self):
        text, checks = self.fixture()
        for atom in ("cycloneive_ram_block", "cyclonev_lcell_comb", "fiftyfivenm_adcblock"):
            with self.subTest(atom=atom), self.assertRaises(ValueError):
                self.verify(text + f"\n{atom} \\extra (.portadataout(\\spare ));", checks)

    def test_the_single_pll_checker_is_not_reachable_with_this_familys_atoms(self):
        with self.assertRaises(ValueError):
            ce.verify_lock_event(None, "", TOP, parallel=False)
        with self.assertRaisesRegex(ValueError, "MAX 10 primitives only"):
            fpga_pll.verify_lock_event(None, "", "clocking_proof", parallel=False, primitives=ce.PRIMITIVES)

    def test_the_delay_annotation_is_recognized_and_bounded(self):
        """Cyclone IV E's EDA netlist opens with one $sdf_annotate; MAX 10's has none."""
        text, checks = self.fixture()
        annotation = 'initial $sdf_annotate("design_v.sdo");'
        self.assertEqual(self.verify(annotation + "\n" + text, checks)["truth_cases"], 32)
        for bad in (annotation + "\n" + annotation,
                    'initial $sdf_annotate("design_v.txt");',
                    'initial $readmemh("design_v.sdo", memory);',
                    'initial $sdf_annotate("design_v.sdo", top);'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.verify(bad + "\n" + text, checks)


class CompensationDiagnosticTests(unittest.TestCase):
    """The one extra caution: exactly one line, a known PLL, and this target's own pin."""

    LINE = ('Critical Warning (176598): PLL "{pll}" input clock inclk[0] is not fully compensated '
            'because it is fed by a remote clock pin "Pin_{pin}" File: /repo/src/fpga/de2_115/'
            'de2_clocking_proof.sv Line: 16')

    def folder(self, pin="Y2", family=ce.FAMILY):
        """An attempt folder with this target's project file and its generated HDL.

        The shared explainer re-verifies the generated pair before it accepts the
        merge refusal, so the folder carries both.
        """
        folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch())))
        (folder / "design.qsf").write_text(
            f'set_global_assignment -name FAMILY "{family}"\n'
            f'set_location_assignment PIN_{pin} -to "clk_reference"\n', encoding="utf-8")
        return generated_pair(folder, family)

    def test_one_caution_on_this_targets_own_pin_is_explained(self):
        for pll in ce.FIT_INSTANCES:
            with self.subTest(pll=pll):
                line = self.LINE.format(pll=pll, pin="Y2")
                explained = ce.explained_diagnostics(line + "\n", self.folder(), ce.DEFINITION)
                self.assertEqual([item["code"] for item in explained], ["176598"])
                self.assertEqual(explained[0]["text"], line)
                self.assertIn("dedicated clock input", explained[0]["reason"])
                # The explanation is what lets the builder accept the line at all.
                self.assertEqual([item["text"] for item in fpga.diagnostics(line + "\n", explained)], [line])

    def test_a_different_pin_pll_or_count_stays_unexplained(self):
        good = self.LINE.format(pll=PIXEL_INSTANCE, pin="Y2")
        for text, note in ((self.LINE.format(pll=PIXEL_INSTANCE, pin="AG14"), "another pin"),
                           (self.LINE.format(pll="u_other|pll1", pin="Y2"), "an unknown PLL"),
                           (good + "\n" + self.LINE.format(pll=SYSTEM_INSTANCE, pin="Y2"), "two lines"),
                           (good.replace("remote clock pin", "switchover clock pin"), "another cause")):
            with self.subTest(note=note), self.assertRaises(ValueError):
                ce.explained_diagnostics(text + "\n", self.folder(), ce.DEFINITION)

    def test_max10_still_refuses_the_same_caution(self):
        """MAX 10 feeds both its PLLs locally, so the line is not explained there."""
        line = self.LINE.format(pll=PIXEL_INSTANCE, pin="P11")
        folder = self.folder(pin="P11", family="MAX 10")
        explained = fpga_pll.explained_diagnostics(line + "\n", folder, ce.DEFINITION)
        self.assertEqual(explained, [])
        with self.assertRaisesRegex(ValueError, "unexplained Quartus diagnostic"):
            fpga.diagnostics(line + "\n", explained)


if __name__ == "__main__":
    unittest.main()
