"""Sensitivity of the exact explained vendor-warning boundary, and the ADC host facts."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.n2m import fpga, fpga_adc, fpga_flash, fpga_lock, fpga_pll
from tools.n2m.tests import vendor_support

CONTROL = "ip/altera/altera_modular_adc/control/"
ROOT = Path(__file__).resolve().parents[3]


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
        cases = ["\n".join(lines[1:]), self.text + lines[-1] + "\n",
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


def no_clock_report(rows):
    """A `check_timing.rpt` fragment reporting exactly these registers as unclocked."""
    return "".join(f"; {row} ; No clock feeds this register's clock port. ;\n" for row in rows)


class AdcNoClockInventoryTests(unittest.TestCase):
    """The audited no-clock count and the rows the netlist gates require are one sum.

    They were two statements and they disagreed. `fpga.timing_evidence` counted
    the accepted rows from the target's own `pll` field, while
    `fpga_adc.verify_netlist` required the ADC backend's lock synchronizer
    whether or not the target generated a PLL. For the one registered target
    with an ADC top and no `pll` field, `adc-early`, the two differed by exactly
    that row, so no fit could satisfy both: one row failed the count and zero
    rows failed the gate.

    That was decidable from the registry and these modules alone, so the guard is
    a host test and needs no Quartus. It reads the three target registries, which
    is why this unit declares them as inputs.
    """

    def registered(self):
        """Every registered target with its declared top, read from the registries."""
        for registry in fpga.REGISTRIES:
            for name, entry in json.loads((ROOT / registry).read_text(encoding="utf-8"))["targets"].items():
                yield name, entry["top"]

    def adc_targets(self):
        """Resolved definitions of the registered targets that place the ADC backend."""
        return [(name, fpga.target_definition(ROOT, name))
                for name, top in self.registered() if top in fpga_adc.TOPS]

    def rows(self, target):
        """Every no-clock row the audit accounts for, from the owners that name them."""
        parallel = target.get("pll", {}).get("system_divide") == 2
        rows = list(fpga_adc.no_clock_rows(target["top"], parallel=parallel))
        if fpga_flash.flash_target(target):
            rows += list(fpga_flash.no_clock_rows(target["top"]))
        return rows

    def agree(self, target):
        """The one assertion: the audit counts exactly the rows the gates require."""
        self.assertEqual(fpga.expected_no_clock_count(target), len(self.rows(target)))
        self.assertIn(fpga_adc.lock_row(target["top"]), self.rows(target))

    def test_the_audited_count_is_exactly_the_rows_its_owners_name(self):
        for name, target in self.adc_targets():
            with self.subTest(target=name):
                self.agree(target)
        for name, top in self.registered():
            if top not in fpga_adc.TOPS:
                with self.subTest(target=name):
                    self.assertEqual(fpga_adc.lock_event_count(top), 0)

    def test_the_adc_top_without_a_generated_pll_is_still_the_only_one(self):
        """The scope the fix rests on, as a check: one such target, and it is counted."""
        alone = [name for name, target in self.adc_targets() if "pll" not in target]
        self.assertEqual(alone, ["adc-early"])
        target = fpga.target_definition(ROOT, "adc-early")
        self.assertEqual(fpga.expected_no_clock_count(target), 1)
        self.assertEqual(self.rows(target), [fpga_adc.lock_row("adc_proof")])

    def test_one_reported_inventory_satisfies_both_gates(self):
        """The rows the audit counts are the rows each netlist gate accepts.

        `v05-controls-board` is left out of this gate check and covered by the
        count check above. Its fit reports one further register row, the On-Chip
        Flash IP's atom register, which `fpga_lock` accepts through `extra_rows`
        while the ADC gate accounts for no row but its own. That is a second
        disagreement, in the flash/ADC composition, and not the count this unit
        guards.
        """
        for name, target in self.adc_targets():
            if fpga_flash.flash_target(target):
                continue
            top, parallel = target["top"], target.get("pll", {}).get("system_divide") == 2
            checks = no_clock_report(self.rows(target))
            with self.subTest(target=name, gate="adc"):
                with self.assertRaises(ValueError) as caught:
                    fpga_adc.verify_netlist("", checks, top, parallel=parallel)
                self.assertNotIn("unexpected ADC no-clock endpoint", str(caught.exception))
            if top not in fpga_adc.COMPOSED:
                continue
            with self.subTest(target=name, gate="clocking"):
                verify = fpga_lock.verify_parallel if parallel else fpga_lock.verify
                with self.assertRaises(ValueError) as caught:
                    verify("", checks, top)
                self.assertNotIn("inventory differs", str(caught.exception))
                self.assertNotIn("unrecognized no-clock endpoint", str(caught.exception))

    def test_an_audit_that_drops_the_adc_row_fails_this_guard(self):
        """Proof the guard fails: the pre-fix arithmetic, restated, still disagrees.

        Keying the count on the `pll` field is the same as counting no ADC row at
        all for a target that generates no PLL, so patching the ADC's own count
        to zero reproduces the refusal exactly, and both directions of the
        contradiction are shown: one row fails the count, zero fails the gate.
        """
        target = fpga.target_definition(ROOT, "adc-early")
        rows = self.rows(target)
        with patch.object(fpga_adc, "lock_event_count", return_value=0):
            self.assertEqual(fpga.expected_no_clock_count(target), 0)
            self.assertNotEqual(fpga.expected_no_clock_count(target), len(rows))
            with self.assertRaises(AssertionError):
                self.agree(target)
        with self.assertRaisesRegex(ValueError, "unexpected ADC no-clock endpoint"):
            fpga_adc.verify_netlist("", no_clock_report([]), "adc_proof")


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
