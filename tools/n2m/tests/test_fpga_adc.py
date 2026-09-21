"""Sensitivity of the exact explained vendor-warning boundary, and the ADC host facts."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.n2m import (fpga, fpga_adc, fpga_clocking, fpga_flash, fpga_lock, fpga_lock_cyclonev,
                       fpga_pll)
from tools.n2m.hdl import dependencies
from tools.n2m.tests.fit_reports import no_clock_table
from tools.n2m.tests import vendor_support

CONTROL = "ip/altera/altera_modular_adc/control/"
FLASH_IP = "ip/altera/altera_onchip_flash/"
ROOT = Path(__file__).resolve().parents[3]
# The ADC backend itself: which designs compile it is the registry's statement,
# and `fpga_adc.TOPS` must name the same ones.
ADC_BACKEND = "src/rtl/input/n2m_adc_backend.sv"


_TARGETS = None


def registered_targets():
    """Every registered target's name and resolved definition, resolved once."""
    global _TARGETS
    if _TARGETS is None:
        resolved = []
        for registry in fpga.REGISTRIES:
            for name in json.loads((ROOT / registry).read_text(encoding="utf-8"))["targets"]:
                resolved.append((name, fpga.target_definition(ROOT, name)))
        _TARGETS = resolved
    return _TARGETS


class AdcDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path.cwd() / "workdir/adc-classifier-fixture"
        text = (Path(__file__).parent / "data/adc-unused-features.txt").read_text()
        self.text = text.replace("{folder}", self.folder.as_posix())
        self.digests = {name: hashlib.sha256(name.encode()).hexdigest() for name in fpga_adc.DIAGNOSTIC_CONTROL}
        self.sources = {name: vendor_support.accepted("/vendor/" + name, digest, CONTROL + name)
                        for name, digest in self.digests.items()}
        self.hashes = patch.object(fpga_adc, "file_hash", side_effect=lambda p: self.digests[p.name])
        self.hashes.start()
        self.addCleanup(self.hashes.stop)

    def classify(self, text=None):
        text = self.text if text is None else text
        explained = fpga_adc.explained_diagnostics(text, self.folder, self.sources)
        return fpga.diagnostics(text, explained)

    def test_exact_retained_vendor_inventory_visible(self):
        result = self.classify()
        self.assertEqual(len(result), 15)
        self.assertTrue(all(r["reason"] for r in result))

    def test_missing_duplicate_extra_or_wrong_instance_rejected(self):
        lines = self.text.splitlines()
        # A second 10036 naming one of the classified sources is inside this
        # classifier's own scope, so it refuses it by name; one naming any other
        # source is another owner's, and `classify` fails at the builder's gate.
        extra = lines[0].replace('(70)', '(71)').replace('sync_ctrl_state_nxt', 'sync_ctrl_state')
        cases = ["\n".join(lines[1:]), self.text + lines[-1] + "\n", self.text + extra + "\n",
                 self.text + 'Warning (10036): unrelated unused register\n',
                 self.text.replace('ts_avrg_fifo', 'product_memory'),
                 self.text.replace('q_b[11]', 'q_b[12]')]
        for text in cases:
            with self.subTest(text=text[-80:]), self.assertRaises(ValueError):
                self.classify(text)

    def test_other_warning_and_an_unrecorded_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexplained"):
            self.classify(self.text + 'Warning (15058): wrong clock mode\n')
        # The classifier explains these exact bytes, so a record that never
        # reached the accepted ledger cannot carry the explanation.
        del self.sources['altera_modular_adc_control_fsm.v']['accepted']
        with self.assertRaisesRegex(ValueError, "not an accepted ledger record"):
            self.classify()

    def test_changed_copied_vendor_source_rejected(self):
        with patch.object(fpga_adc, 'file_hash', return_value='changed'):
            with self.assertRaisesRegex(ValueError, "copied ADC source"):
                self.classify()

    def test_controls_system_requires_exact_relocated_vendor_owner(self):
        relocated = self.text.replace('n2m_adc_backend:u_adc|',
            'n2m_controls_system:u_controls|n2m_adc_backend:u_adc|')
        result = fpga_adc.explained_diagnostics(relocated, self.folder, self.sources,
                                               'v05_controls_proof')
        self.assertEqual(len(result), 15)
        for bad in (self.text, relocated.replace('u_controls|', 'wrong_controls|')):
            with self.assertRaises(ValueError):
                fpga_adc.explained_diagnostics(bad, self.folder, self.sources,
                                              'v05_controls_proof')
        with self.assertRaises(ValueError):
            self.classify(relocated)

    def test_no_global_warning_code_waiver(self):
        with self.assertRaisesRegex(ValueError, "unexplained"):
            fpga.diagnostics(self.text)


class ComposedClassifierScopeTests(unittest.TestCase):
    """One image carrying two classified IPs: each classifier judges only its own.

    `v05-controls-board` places the Intel ADC control and the On-Chip Flash IP.
    The ADC classifier used to select every 10036, 14284, 14285 and 14320 line in
    the whole compile log and demand exactly fifteen, so the flash IP's twenty
    accepted 10036 warnings made it refuse a log in which every warning was
    already explained by one owner or the other, and no host could build the
    target.

    Nothing measured that break when the flash reader entered this image: a
    MAX 10 fit of it costs minutes of CPU, it is in no workflow, and a
    [regression subset](../../../wiki/tools/n2m/SPEC.md#regression-subsets) takes
    catalogue simulation targets only, so no subset can hold an FPGA target at
    all. The break was decidable from a captured log and these two modules, which
    is what this unit reads. It finds the images with both IPs from the registry
    rather than naming one, so a second such target is covered when it appears.
    """

    def setUp(self):
        self.folder = Path.cwd() / "workdir/composed-classifier-fixture"
        self.adc = (Path(__file__).parent / "data/adc-unused-features.txt").read_text()
        self.digests = {name: hashlib.sha256(name.encode()).hexdigest()
                        for name in (*fpga_adc.DIAGNOSTIC_CONTROL, *fpga_flash.SOURCES)}
        self.adc_sources = {name: vendor_support.accepted("/vendor/" + name, self.digests[name], CONTROL + name)
                            for name in fpga_adc.DIAGNOSTIC_CONTROL}
        self.flash_sources = {name: vendor_support.accepted("/vendor/" + name, self.digests[name],
                                                            FLASH_IP + folder + "/" + name)
                              for name, folder in fpga_flash.SOURCES.items()}
        for module in (fpga_adc, fpga_flash):
            patcher = patch.object(module, "file_hash", side_effect=lambda p: self.digests[Path(p).name])
            patcher.start()
            self.addCleanup(patcher.stop)

    def both(self):
        """Registered targets that place the ADC backend and list the flash reader."""
        return [(name, target) for name, target in registered_targets()
                if target["top"] in fpga_adc.TOPS and fpga_flash.flash_target(target)]

    def adc_only(self):
        """Registered ADC targets without the flash IP: the ones that passed before."""
        return [(name, target) for name, target in registered_targets()
                if target["top"] in fpga_adc.TOPS and not fpga_flash.flash_target(target)]

    def adc_lines(self, top):
        """The captured ADC inventory, relocated to this top's hierarchy."""
        text = self.adc.replace("{folder}", self.folder.as_posix())
        if top == "v05_controls_proof":
            text = text.replace("n2m_adc_backend:u_adc|",
                                "n2m_controls_system:u_controls|n2m_adc_backend:u_adc|")
        return text.splitlines()

    def flash_lines(self, top):
        """The IP's twenty read-only-mode objects and its four compile-log strobes."""
        path = (self.folder / fpga_flash.CONTROLLER).resolve().as_posix()
        return [f'Warning (10036): Verilog HDL or VHDL warning at {fpga_flash.CONTROLLER}({number}): '
                f'object "{name}" assigned a value but never read File: {path} Line: {number}'
                for number, name in fpga_flash.UNUSED_OBJECTS] + [
            fpga_flash.STROBE_WARNING.format(node=fpga_flash.strobe_node(top))
        ] * fpga_flash.STROBE_COUNTS["compile.log"]

    def compile_log(self, top, extra=()):
        """A compile log holding both inventories, in the order Quartus writes them."""
        return "\n".join(["Info: Running Quartus Prime Analysis & Synthesis",
                          *self.flash_lines(top)[:len(fpga_flash.UNUSED_OBJECTS)],
                          *self.adc_lines(top), "Info: Running Quartus Prime Fitter",
                          *self.flash_lines(top)[len(fpga_flash.UNUSED_OBJECTS):], *extra]) + "\n"

    def classify(self, top, text):
        """Both classifiers, then the builder's own gate over everything they explained."""
        explained = fpga_adc.explained_diagnostics(text, self.folder, self.adc_sources, top)
        explained += fpga_flash.explained_diagnostics(text, self.folder, self.flash_sources, top, "compile.log")
        return explained, fpga.diagnostics(text, explained)

    def test_an_image_with_both_ips_keeps_both_classified_inventories(self):
        """The defect, as a check: the union of both accepted sets is classified."""
        targets = self.both()
        self.assertEqual([name for name, _ in targets], ["v05-controls-board"])
        for name, target in targets:
            top = target["top"]
            with self.subTest(target=name):
                explained, classified = self.classify(top, self.compile_log(top))
                self.assertEqual(len(explained), 36)
                self.assertEqual(Counter(item["code"] for item in classified),
                                 Counter({"10036": 21, "332060": 4, "14320": 12, "14284": 1, "14285": 1}))
                self.assertTrue(all(item["reason"] for item in classified))

    def test_the_unscoped_selection_this_replaced_still_refuses_that_log(self):
        """Proof the guard fails without the fix: the old predicate, restated."""
        def unscoped(line, prefix):
            return re.match(r'Warning \((10036|14284|14285|14320)\):', line) is not None
        for name, target in self.both():
            with self.subTest(target=name), patch.object(fpga_adc, "owned_diagnostic", unscoped):
                with self.assertRaisesRegex(ValueError, "unexpected ADC unused-feature diagnostic"):
                    self.classify(target["top"], self.compile_log(target["top"]))

    def test_neither_classifier_claims_the_other_owner_s_lines(self):
        """The scope itself: the ADC predicate takes no flash line, and each set is its own.

        The second half is behavioral rather than a copy of the flash predicate,
        so it still holds if that module scopes itself differently later.
        """
        for name, target in self.both():
            top = target["top"]
            prefix = fpga_adc.node_prefix(top)
            with self.subTest(target=name):
                for line in self.flash_lines(top):
                    self.assertFalse(fpga_adc.owned_diagnostic(line, prefix), line)
                text = self.compile_log(top)
                adc = {item["text"] for item in
                       fpga_adc.explained_diagnostics(text, self.folder, self.adc_sources, top)}
                flash = {item["text"] for item in fpga_flash.explained_diagnostics(
                    text, self.folder, self.flash_sources, top, "compile.log")}
                self.assertEqual(adc, set(self.adc_lines(top)))
                self.assertEqual(flash, set(self.flash_lines(top)))
                self.assertEqual(adc & flash, set())

    def test_a_warning_outside_both_scopes_still_fails_the_build(self):
        """Scoping accepts nothing: an unowned line of either shared code still fails.

        These are the warnings a reviewer would try to slip past the narrower
        predicate — our own unread register and our own node synthesized away,
        under the same codes the ADC inventory uses. Neither classifier claims
        them, and `fpga.diagnostics` refuses every line no classifier explained,
        so each one fails the build by its own text.
        """
        design = (self.folder / "n2m_controls_system.sv").as_posix()
        for extra in (f'Warning (10036): Verilog HDL or VHDL warning at n2m_controls_system.sv(42): '
                      f'object "spare_state" assigned a value but never read File: {design} Line: 42',
                      'Warning (14320): Synthesized away node "n2m_controls_system:u_controls|'
                      f'n2m_input:u_input|held_mask[3]" File: {design} Line: 91',
                      'Warning (10036): unrelated unused register'):
            for name, target in self.both():
                top = target["top"]
                with self.subTest(target=name, extra=extra[:60]):
                    text = self.compile_log(top, extra=[extra])
                    # Both inventories are still exactly right; only the new line is not.
                    explained = fpga_adc.explained_diagnostics(text, self.folder, self.adc_sources, top)
                    explained += fpga_flash.explained_diagnostics(text, self.folder, self.flash_sources,
                                                                 top, "compile.log")
                    with self.assertRaisesRegex(ValueError, "unexplained Quartus diagnostic"):
                        fpga.diagnostics(text, explained)

    def test_a_warning_inside_a_scope_still_fails_its_own_classifier(self):
        """In scope and unpredicted stays a named refusal by the owner that claims it."""
        for name, target in self.both():
            top = target["top"]
            path = (self.folder / "altera_modular_adc_control_fsm.v").as_posix()
            controller = (self.folder / fpga_flash.CONTROLLER).resolve().as_posix()
            cases = {
                "unexpected ADC unused-feature diagnostic":
                    [f'Warning (10036): Verilog HDL or VHDL warning at altera_modular_adc_control_fsm.v(71): '
                     f'object "sync_ctrl_state" assigned a value but never read File: {path} Line: 71'],
                "unexpected On-Chip Flash IP diagnostic":
                    [f'Warning (10036): Verilog HDL or VHDL warning at {fpga_flash.CONTROLLER}(999): '
                     f'object "spare" assigned a value but never read File: {controller} Line: 999'],
            }
            for message, extra in cases.items():
                with self.subTest(target=name, message=message):
                    with self.assertRaisesRegex(ValueError, message):
                        self.classify(top, self.compile_log(top, extra=extra))
            for header in ('Warning (14284): Synthesized away the following LCELL buffer node(s):',
                           'Warning (14285): Synthesized away the following node(s):'):
                with self.subTest(target=name, header=header):
                    with self.assertRaisesRegex(ValueError, "unexpected ADC unused-feature diagnostic"):
                        self.classify(top, self.compile_log(top, extra=[header]))

    def test_an_adc_image_without_the_flash_ip_is_unchanged(self):
        """The two ADC targets that passed before keep the same fifteen, from the same log."""
        self.assertEqual([name for name, _ in self.adc_only()], ["adc-early", "controls-board"])
        for name, target in self.adc_only():
            top = target["top"]
            with self.subTest(target=name):
                text = "\n".join(self.adc_lines(top)) + "\n"
                explained = fpga_adc.explained_diagnostics(text, self.folder, self.adc_sources, top)
                self.assertEqual(len(explained), 15)
                self.assertEqual(Counter(item["code"] for item in fpga.diagnostics(text, explained)),
                                 Counter({"14320": 12, "10036": 1, "14284": 1, "14285": 1}))


# Which owner names each `No Clock` row of every registered target, recorded so a
# target that gains, loses or reassigns a row fails here. Grouped by the owner
# sequence because that, not the node text, is what this inventory decides; each
# owner's node text is pinned by that owner's own unit.
ACCEPTED_OWNERS = {
    (): ["builder-invalid", "builder-smoke", "de2-invalid", "de2-smoke", "memory-stores",
         "memory-stores-preloaded", "nano-clocking", "nano-clocking-invalid", "nano-invalid",
         "nano-smoke", "nano-uart", "nano-uart-invalid", "snapshot", "uart-exchange-stores",
         "uart-packet-stores", "uart-presence-store"],
    ("adc",): ["adc-early"],
    ("clocking", "clocking"): ["clocking-invalid", "clocking-nominal", "clocking-upper", "de2-clocking",
                               "de2-clocking-invalid", "de2-system", "de2-system-invalid", "de2-vga",
                               "de2-vga-invalid", "intel-memory", "ppu-invalid", "ppu-nominal",
                               "ppu-upper", "sdram-proof", "vga-invalid", "vga-nominal", "vga-upper"],
    ("clocking", "clocking", "adc"): ["controls-board"],
    ("clocking", "clocking", "onchip_flash", "onchip_flash"): ["flash-proof", "v05", "v05-board"],
    ("clocking", "clocking", "adc", "onchip_flash", "onchip_flash"): ["v05-controls-board"],
}


class NoClockInventoryTests(unittest.TestCase):
    """What every checker accepts in the fit's `No Clock` table is one named list.

    Two checkers read that table: the family's clocking gate and the ADC's. Each
    used to resolve its own expected list and compare the whole table against it.
    On `v05-controls-board` one accepted four register rows through an
    `extra_rows` allowance and the other three, while the audited *count* stayed
    right, so the count comparison that guarded this passed straight over the
    disagreement. `fpga.no_clock_inventory` now resolves one list from the modules
    that own the vendor blocks, and every checker is handed it, so these tests
    compare names.

    Deciding that needs the three registries and these modules, not Quartus. A fit
    costs minutes and needs a tool no hosted runner has, so this is the check that
    can run per change; it reads each target's sources, which is why this unit
    declares them as inputs.
    """

    def targets(self):
        return registered_targets()

    def adc_targets(self):
        """The registered targets that place the ADC backend."""
        return [(name, target) for name, target in self.targets() if target["top"] in fpga_adc.TOPS]

    def rows(self, target):
        """The (node, reason) pairs every checker of this target's table is handed."""
        return fpga.accepted_no_clock_rows(target)

    def report(self, rows):
        """The `No Clock` table a fit reporting exactly `rows` writes."""
        return no_clock_table(rows)

    def check_table(self, target, checks, rows=None):
        """Run every checker that reads this target's table, on the rows it names.

        Each raises further on its netlist, which these fixtures do not carry; the
        assertions are about the inventory comparison alone, so a message about
        anything else is a pass for that checker.
        """
        rows = self.rows(target) if rows is None else rows
        top, parallel = target["top"], target.get("pll", {}).get("system_divide") == 2
        raised = []
        if "pll" in target:
            if target["family"] == fpga.CYCLONEV_FAMILY:
                verify = fpga_lock_cyclonev.verify
            else:
                verify = fpga_lock.verify_parallel if parallel else fpga_lock.verify
            with self.assertRaises(ValueError) as caught:
                verify("", checks, top, rows=rows)
            raised.append(("clocking", str(caught.exception)))
        if top in fpga_adc.TOPS:
            with self.assertRaises(ValueError) as caught:
                fpga_adc.verify_netlist("", checks, top, rows=rows)
            raised.append(("adc", str(caught.exception)))
        self.assertTrue(raised, "no checker reads this target's table")
        return raised

    def test_every_registered_target_names_an_owner_for_every_row(self):
        """All 39: one owner per row, no row named twice, and the count is the length."""
        for name, target in self.targets():
            with self.subTest(target=name):
                inventory = fpga.no_clock_inventory(target)
                self.assertEqual(len({row.node for row in inventory}), len(inventory))
                self.assertLessEqual({row.owner for row in inventory}, {"clocking", "adc", "onchip_flash"})
                self.assertEqual(fpga.expected_no_clock_count(target), len(inventory))
                self.assertEqual(self.rows(target), [(row.node, row.reason) for row in inventory])
        self.assertEqual(len(self.targets()), 39)

    def test_the_accepted_owner_inventory_is_the_recorded_one(self):
        """Every target's accepted rows and their owners are the recorded inventory."""
        actual = {}
        for name, target in self.targets():
            actual.setdefault(tuple(row.owner for row in fpga.no_clock_inventory(target)), []).append(name)
        self.assertEqual({key: sorted(names) for key, names in actual.items()},
                         {key: sorted(names) for key, names in ACCEPTED_OWNERS.items()})

    def test_the_composed_image_attributes_each_of_its_five_rows(self):
        """`v05-controls-board`: both target PLLs, the ADC's, and the IP's two."""
        target = dict(self.targets())["v05-controls-board"]
        inventory = fpga.no_clock_inventory(target)
        self.assertEqual([row.owner for row in inventory],
                         ["clocking", "clocking", "adc", "onchip_flash", "onchip_flash"])
        self.assertEqual([row.node for row in inventory][:3],
                         [fpga_lock.ROW, fpga_lock.SYSTEM_ROW, fpga_adc.lock_row("v05_controls_proof")])
        self.assertEqual([row.node for row in inventory][3:], [node for node, _ in fpga_flash.no_clock_rows("v05_controls_proof")])
        # Four of the five are unclocked registers; the strobe feeds a clock port.
        self.assertEqual([row.reason for row in inventory].count(fpga_lock.REGISTER_REASON), 4)
        self.assertEqual([row.reason for row in inventory][3], fpga_flash.STROBE_REASON)

    def test_one_reported_table_satisfies_every_checker_that_reads_it(self):
        """The table the inventory predicts passes the inventory step of every checker.

        Run for all 39 targets, including the flash images the count-based guard
        had to skip: that skip is where the disagreement lived.
        """
        for name, target in self.targets():
            checks = self.report(self.rows(target))
            if not ("pll" in target or target["top"] in fpga_adc.TOPS):
                self.assertEqual(fpga_lock.reported_no_clock_rows(checks), list(self.rows(target)))
                continue
            for checker, message in self.check_table(target, checks):
                with self.subTest(target=name, checker=checker):
                    self.assertNotIn("inventory", message)
                    # Stated as "nothing about this table", not as "not my own
                    # wording": a checker that refuses the agreed rows for a
                    # reason of its own has to fail here too.
                    for phrase in ("no-clock", "no clock", "endpoint"):
                        self.assertNotIn(phrase, message.lower())

    def test_two_owners_naming_different_rows_of_the_same_number_fails(self):
        """The case a count comparison cannot see, in both directions.

        Each patch renames one owner's row without changing how many rows it
        names, so the audited count is identical and the names are not. The
        refusal has to name the row, because nothing else distinguishes it.
        """
        target = dict(self.targets())["v05-controls-board"]
        truth = self.report(self.rows(target))
        before = fpga.expected_no_clock_count(target)
        drifts = {
            "adc": patch.object(fpga_adc, "lock_row", return_value="n2m_drifted:u_controls|pll_lock_sync"),
            "clocking": patch.object(fpga_pll, "no_clock_rows",
                                     return_value=[("n2m_drifted:u_clocking|pixel_lock_sync", fpga_lock.REGISTER_REASON),
                                                   (fpga_lock.SYSTEM_ROW, fpga_lock.REGISTER_REASON)]),
            "onchip_flash": patch.object(fpga_flash, "no_clock_rows",
                                         return_value=(("n2m_drifted:u_reader|flash_se_neg_reg", fpga_flash.STROBE_REASON),
                                                       ("n2m_drifted:u_reader|ufm_block~XE_YE_TO_SE_FF", fpga_lock.REGISTER_REASON))),
        }
        # Every owner of a row on this target gets its turn.
        self.assertEqual(set(drifts), {row.owner for row in fpga.no_clock_inventory(target)})
        for owner, drift in drifts.items():
            with self.subTest(owner=owner), drift:
                drifted = self.rows(target)
                # The count is all a count-based guard compares, and it did not move.
                self.assertEqual(fpga.expected_no_clock_count(target), before)
                self.assertEqual(len(drifted), before)
                self.assertNotEqual(drifted, list(fpga_lock.reported_no_clock_rows(truth)))
                with self.assertRaises(ValueError) as caught:
                    fpga_lock.require_no_clock_rows(truth, drifted, "fit")
                message = str(caught.exception)
                self.assertIn("no owner claims no-clock row", message)
                self.assertTrue(any(node in message for node, _ in fpga_lock.reported_no_clock_rows(truth)),
                                "the refusal does not name the row it refused")
                for checker, checker_message in self.check_table(target, truth, rows=drifted):
                    self.assertTrue("no owner claims no-clock row" in checker_message
                                    or "inventory omits" in checker_message,
                                    f"{checker} accepted a table its inventory does not name")
        self.assertEqual(self.rows(target), list(fpga_lock.reported_no_clock_rows(truth)))

    def test_a_row_no_owner_claims_fails_with_its_name(self):
        """An extra row in the table is refused by its own name, for every target."""
        extra = ("n2m_unowned:u_thing|some_register", fpga_lock.REGISTER_REASON)
        for name, target in self.targets():
            rows = self.rows(target)
            checks = self.report(list(rows) + [extra])
            with self.subTest(target=name):
                with self.assertRaises(ValueError) as caught:
                    fpga_lock.require_no_clock_rows(checks, rows, "fit")
                self.assertIn(extra[0], str(caught.exception))
                if "pll" in target or target["top"] in fpga_adc.TOPS:
                    for checker, message in self.check_table(target, checks):
                        self.assertIn(extra[0], message, f"{checker} did not name the unowned row")

    def test_a_dropped_row_still_fails_although_the_count_follows_it(self):
        """The complementary case: the count moves with the row, the names do not.

        Each owner's count is the length of its own named rows, so dropping a row
        moves both sides of the audited sum together and no count comparison sees
        it. What refuses it is the fit's own table, compared row by row.
        """
        target = dict(self.targets())["v05-controls-board"]
        truth = self.report(self.rows(target))
        for owner, drift in (("clocking", patch.object(fpga_pll, "no_clock_rows",
                                                       return_value=[(fpga_lock.ROW, fpga_lock.REGISTER_REASON)])),
                             ("adc", patch.object(fpga_adc, "no_clock_rows", return_value=())),
                             ("onchip_flash", patch.object(fpga_flash, "no_clock_rows",
                                                           return_value=(fpga_flash.no_clock_rows("v05_controls_proof")[0],)))):
            with self.subTest(owner=owner), drift:
                short = self.rows(target)
                self.assertEqual(fpga.expected_no_clock_count(target), len(short))
                self.assertEqual(len(short), 4)
                with self.assertRaisesRegex(ValueError, "no owner claims no-clock row"):
                    fpga_lock.require_no_clock_rows(truth, short, "fit")

    def test_the_adc_top_set_is_exactly_the_targets_that_compile_the_backend(self):
        """`TOPS` is a literal, so tie it to the source the registry actually places.

        A new ADC top, or the backend added to a target on another top, would
        otherwise pass the checks above by being filtered out of them. Both cases
        fail closed at fit time; this makes them fail here instead.
        """
        placed = [name for name, target in self.targets()
                  if ADC_BACKEND in dependencies(ROOT, target["sources"], synthesis=True)]
        self.assertEqual(placed, [name for name, _ in self.adc_targets()])
        self.assertEqual(placed, ["adc-early", "controls-board", "v05-controls-board"])

    def test_the_adc_top_without_a_generated_pll_is_still_the_only_one(self):
        """The scope the ADC's separate row rests on: one such target, and it is counted."""
        alone = [name for name, target in self.adc_targets() if "pll" not in target]
        self.assertEqual(alone, ["adc-early"])
        target = dict(self.adc_targets())["adc-early"]
        self.assertEqual(fpga.expected_no_clock_count(target), 1)
        self.assertEqual(self.rows(target), [(fpga_adc.lock_row("adc_proof"), fpga_lock.REGISTER_REASON)])

    def test_each_checker_refuses_an_inventory_that_omits_its_own_row(self):
        """Every owner still states which row is its own, so a list missing it fails."""
        for name, target in self.targets():
            rows = self.rows(target)
            if not rows:
                continue
            for dropped in rows:
                kept = [row for row in rows if row != dropped]
                checks = self.report(kept)
                with self.subTest(target=name, dropped=dropped[0][-40:]):
                    for checker, message in self.check_table(target, checks, rows=kept):
                        self.assertTrue("inventory omits" in message
                                        or "no owner claims no-clock row" not in message)


# A minimal MAX 10 fit report shaped like the one `adc-early` produces: the
# dedicated ADC reference pin, the system clock pin, the ADC PLL's compensation
# mode, and the degree sign (0xb0) Quartus writes into Operating Settings and
# Conditions. The real report carries 0xb0 at two offsets inside that block and
# nowhere else, so this fixture reproduces the decode the reader must survive.
ADC_FIT = """\
+------------------------------------------+
; Input Pins                               ;
+----------+------------+-------+-----------+
; N5       ; 2          ; clk_adc_reference ; input  ; 3.3-V LVTTL ; Row I/O    ;
; P11      ; 3          ; clk_sys           ; input  ; 3.3-V LVTTL ; Column I/O ;
+------------------------------------------+
; PLL Summary                              ;
+----------+--------------------------------+
; PLL mode                      ; No compensation ;
+------------------------------------------+
; Operating Settings and Conditions        ;
+----------+--------------------------------+
; Low Junction Temperature      ; 0 \xb0C  ;
; High Junction Temperature     ; 85 \xb0C ;
"""
ADC_FIT_SUMMARY = ("Total memory bits : 0 / 1,677,312 ( 0 % )\n"
                   "Total PLLs : 1 / 4 ( 25 % )\n"
                   "ADC blocks : 1 / 2 ( 50 % )\n")


class AdcGeneratorDiscoveryTests(unittest.TestCase):
    """The ADC path discovers the generator the way the PLL path already does.

    The `.exe` suffix is a platform fact, so both hosts are exercised here, and
    only the module's own `os` reference is replaced. The reason is narrower than
    "pathlib breaks under a patched host". Linux `pathlib` installs a
    `WindowsPath.__new__` that raises, chosen once when `pathlib` was imported,
    so no later patch lifts it. Patching the real `os.name` to "nt" does hand
    back a `WindowsPath`, because `Path()` bypasses that guard, and `.name` and
    `.is_file()` on the result still work. Re-instantiation is what raises: `/`,
    `.parent` and `.resolve()` each call `WindowsPath(...)` again and fail with
    `UnsupportedOperation`. `generator()` joins with `/`, so a broad patch would
    raise there instead of measuring the fact.

    Windows cannot be run here; this stands in for it, and it is exact because
    the expression that served `fpga_pll.identity()` on Windows is the one the
    ADC path now calls.
    """

    def host(self, name):
        return patch.object(fpga_pll, "os", SimpleNamespace(name=name))

    def installation(self, generator):
        """A Quartus tree holding every path `fpga_adc.identity` requires.

        Original placeholder bytes, not copied vendor sources: `identity` checks
        that each path is a file and hashes it, nothing more.
        """
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        # A Linux-shaped tree: the ledger reads the platform from the layout, and
        # this test is about the generator filename, not the platform.
        vendor_support.installation(root)
        vendor_support.ledger(self, root / "ledger.json")
        quartus, control = root / "quartus", root / "ip/altera/altera_modular_adc/control"
        megafunctions = quartus / "libraries/megafunctions"
        paths = [control / name for name in fpga_adc.CONTROL]
        paths += [control / "altera_modular_adc_control_hw.tcl",
                  root / "ip/altera/altera_modular_adc/top/altera_modular_adc_hw.tcl",
                  megafunctions / "altera_std_synchronizer.v", megafunctions / "altpll.tdf",
                  megafunctions / "xml_info/altpll_info.xml",
                  megafunctions / "xml_info/altpll_rules.xml",
                  megafunctions / "xml_info/altpll_wiz_map.xml",
                  quartus / "eda/sim_lib/fiftyfivenm_atoms.v",
                  quartus / "eda/sim_lib/altera_primitives.v",
                  quartus / "bin" / generator]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("host-test placeholder for " + path.name + "\n")
        return quartus / "bin"

    def test_the_generator_name_follows_the_host_on_both_hosts(self):
        for host, name in (("nt", "qmegawiz.exe"), ("posix", "qmegawiz")):
            with self.subTest(host=host), self.host(host):
                self.assertEqual(fpga_pll.generator("/quartus/bin").name, name)

    def test_identity_discovers_the_generator_this_host_actually_has(self):
        """The marginal blocker, as a test: a Linux tree resolves, a Windows one does not.

        Both entries must name the same file, because a build generates the ADC
        PLL from `generator` and reuses the ALTPLL identity beside it.
        """
        for host, name in (("posix", "qmegawiz"), ("nt", "qmegawiz.exe")):
            with self.subTest(host=host), self.host(host):
                directory = self.installation(name)
                result = fpga_adc.identity(directory)
                self.assertEqual(Path(result["generator"]["path"]).name, name)
                self.assertTrue(Path(result["generator"]["path"]).is_file())
                self.assertEqual(Path(result["generator"]["path"]).resolve(),
                                 Path(result["pll_generator"]["path"]).resolve())
                self.assertEqual(result["generator"]["sha256"], result["pll_generator"]["sha256"])

    def test_identity_refuses_a_tree_holding_only_the_other_host_name(self):
        """So the check stays a real check and cannot pass on the wrong name."""
        for host, other in (("posix", "qmegawiz.exe"), ("nt", "qmegawiz")):
            with self.subTest(host=host), self.host(host):
                directory = self.installation(other)
                with self.assertRaisesRegex(ValueError, "missing installed Intel ADC/PLL dependency"):
                    fpga_adc.identity(directory)


class AdcFitReportEncodingTests(unittest.TestCase):
    """The ADC fit report is decoded as Quartus writes it, not as the host guesses.

    `verify` reads `output/design.fit.rpt` itself. The netlist and timing checks
    above that read own their own coverage and are stubbed here, so each test is
    about the one decode and the checks that consume its text.
    """

    def build(self, fit=None, summary=None):
        scratch = Path.cwd() / "workdir/adc-fit-encoding"
        scratch.mkdir(parents=True, exist_ok=True)
        folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch)))
        (folder / "simulation/questa").mkdir(parents=True)
        (folder / "simulation/questa/design.vo").write_text("checked by verify_netlist\n")
        output = folder / "output"
        output.mkdir()
        (output / "check_timing.rpt").write_text("checked by verify_netlist\n")
        (output / "design.fit.rpt").write_text(ADC_FIT if fit is None else fit,
                                               encoding=fpga_adc.FIT_ENCODING)
        (output / "design.fit.summary").write_text(ADC_FIT_SUMMARY if summary is None else summary)
        return folder

    def verify(self, folder):
        with patch.object(fpga_adc, "verify_netlist", return_value={"netlist": "stub"}):
            return fpga_adc.verify(folder)

    def test_the_reader_accepts_a_report_with_a_non_ascii_byte(self):
        folder = self.build()
        self.assertIn(b"\xb0", (folder / "output/design.fit.rpt").read_bytes())
        self.assertEqual(self.verify(folder), {"netlist": "stub"})

    def test_the_host_chosen_read_is_what_used_to_fail(self):
        """The defect, stated as a test: the same bytes are undecodable as utf-8."""
        path = self.build() / "output/design.fit.rpt"
        with self.assertRaises(UnicodeDecodeError):
            path.read_text(encoding="utf-8")

    def test_the_encoding_is_the_one_windows_already_used(self):
        """Criterion 4 at the decode boundary: same bytes, same text, same evidence.

        The pre-fix read named no encoding, so it took the host's locale: cp1252
        on Windows, and whatever the host said elsewhere. The constant is that
        Windows cp1252, so a report decodes to the string Windows already had and
        every check below the read sees identical input.
        """
        windows_locale = "cp1252"
        self.assertEqual(fpga_adc.FIT_ENCODING, windows_locale)
        path = self.build() / "output/design.fit.rpt"
        self.assertEqual(path.read_text(encoding=fpga_adc.FIT_ENCODING),
                         path.read_text(encoding=windows_locale))

    def test_the_decoded_report_is_not_vacuously_accepted(self):
        """The fit checks really consume the decoded text, so the decode matters."""
        cases = {
            "ADC physical clock pin mismatch: N5": (ADC_FIT.replace("; N5  ", "; N6  "), None),
            "ADC fit compensation mode differs": (ADC_FIT.replace("No compensation", "Normal"), None),
            "ADC fit resource mismatch: ADC blocks":
                (None, ADC_FIT_SUMMARY.replace("ADC blocks : 1 /", "ADC blocks : 2 /")),
        }
        for message, (fit, summary) in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, re.escape(message)):
                    self.verify(self.build(fit, summary))


if __name__ == '__main__':
    unittest.main()
