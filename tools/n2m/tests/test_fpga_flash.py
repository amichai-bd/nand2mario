"""On-Chip Flash IP staging, diagnostics and evidence contracts with fixture files; no Quartus needed."""
from pathlib import Path
import hashlib
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vendor_support
from fit_reports import no_clock_table
from n2m import fpga, fpga_flash, fpga_lock, flash_library, vendor_sources
from n2m.records import read_json

IP = "ip/altera/altera_onchip_flash/"

TARGET = {"top": "flash_proof", "sources": [fpga_flash.READER]}
STROBE = fpga_flash.strobe_node("flash_proof")


class FlashIpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="flash ip ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.quartus = self.root / "quartus"
        self.ip = self.root / "ip/altera/altera_onchip_flash"
        self.attempt = self.root / "attempt"
        self.attempt.mkdir()
        vendor_support.installation(self.root, platform="windows")
        self.ledger = vendor_support.ledger(self, self.root / "ledger.json", platform="windows")
        (self.quartus / "eda/sim_lib").mkdir(parents=True)
        (self.quartus / "eda/sim_lib/fiftyfivenm_atoms.v").write_text("atoms\n")
        for name, folder in fpga_flash.SOURCES.items():
            path = self.ip / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"// {name}\n")
        for name in fpga_flash.DEFINITIONS:
            (self.ip / "altera_onchip_flash" / name).write_text(f"# {name}\n")

    def sources(self):
        """A record naming digests the installed files do not carry, so staging refuses."""
        return {name: vendor_support.accepted(self.ip / folder / name, hashlib.sha256(name.encode()).hexdigest(),
                                              IP + folder + "/" + name, platform="windows")
                for name, folder in fpga_flash.SOURCES.items()}

    def test_identity_records_then_refuses_a_changed_vendor_file(self):
        block = "altera_onchip_flash_block.v"
        first = fpga_flash.identity(self.quartus / "bin64")
        self.assertEqual(first[block]["accepted"], "recorded")
        self.assertEqual(set(read_json(self.ledger)["installations"]["windows"]["sources"]),
                         {IP + folder + "/" + name for name, folder in fpga_flash.SOURCES.items()}
                         | {IP + "altera_onchip_flash/" + name for name in fpga_flash.DEFINITIONS}
                         | {"quartus/eda/sim_lib/fiftyfivenm_atoms.v"})
        self.assertEqual(fpga_flash.identity(self.quartus / "bin64")[block]["accepted"], "unchanged")
        (self.ip / "rtl" / block).write_text("// different original test bytes\n")
        with self.assertRaisesRegex(ValueError, "changed since it was accepted"):
            fpga_flash.identity(self.quartus / "bin64")
        # Accepting the reviewed change lets the same tree build again.
        vendor_sources.accept(self.quartus / "bin64", [IP + "rtl/" + block],
                             "Reviewed original host-test bytes for this test.")
        self.assertEqual(fpga_flash.identity(self.quartus / "bin64")[block]["accepted"], "unchanged")
        (self.ip / "rtl" / block).unlink()
        with self.assertRaisesRegex(ValueError, "missing installed Intel On-Chip Flash IP"):
            fpga_flash.identity(self.quartus / "bin64")

    def test_stage_copies_only_unchanged_recorded_files(self):
        sources = self.sources()
        with self.assertRaisesRegex(ValueError, "changed before staging"):
            fpga_flash.stage(self.attempt, sources)
        for name, entry in sources.items():
            entry["sha256"] = hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()
        fpga_flash.stage(self.attempt, sources)
        self.assertEqual(sorted(p.name for p in self.attempt.iterdir()), sorted(fpga_flash.SOURCES))

    def test_assignments_name_the_four_files_the_compressed_image_mode_and_the_library(self):
        lines = fpga_flash.assignments("flash_proof")
        self.assertEqual(lines[:4], [f"set_global_assignment -name VERILOG_FILE {n}" for n in fpga_flash.SOURCES])
        self.assertEqual(lines[4], fpga_flash.CONFIGURATION_MODE)
        self.assertEqual(lines[5], 'set_parameter -name INIT_FILENAME "library.hex" -to "u_reader"')
        self.assertEqual(len(lines), 6)
        self.assertEqual(fpga_flash.assignments("v05_proof")[5],
                         'set_parameter -name INIT_FILENAME "library.hex" -to "u_system|u_copier|u_reader"')
        with self.assertRaisesRegex(ValueError, "unsupported flash reader top"):
            fpga_flash.assignments("sdram_proof")
        self.assertTrue(fpga_flash.flash_target(TARGET))
        self.assertFalse(fpga_flash.flash_target({"top": "sdram_proof", "sources": ["src/rtl/storage/n2m_sdram_ctrl.sv"]}))

    def library(self):
        """A two-word library and a .pof holding it: erased user range, the words, then a CFM0 with 5 programmed bytes."""
        words = {0: 0x03020100, 0x22000: 0x80000101}
        flash_library.write(self.attempt, {"words": words, "catalogue": b"", "rows": []})
        (self.attempt / flash_library.CATALOGUE_NAME).unlink()
        user = flash_library.pof_words(flash_library.words_to_bytes(words))
        cfm0 = b"\x12\x34\xFF\x56\x78" + b"\xFF" * (flash_library.CFM0_BYTES - 5)
        return words, b"POF header" + user + cfm0 + b"trailer"

    def test_verify_requires_the_ufm_block_the_assignments_and_the_library_in_the_pof(self):
        output = self.attempt / "output"
        output.mkdir()
        for name in fpga_flash.SOURCES:
            (self.attempt / name).write_text("copy\n")
        (self.attempt / "design.qsf").write_text("\n".join(fpga_flash.assignments("flash_proof")) + "\n")
        (output / "design.fit.summary").write_text("UFM blocks : 1 / 1 ( 100 % )\n")
        words, pof = self.library()
        (output / "design.pof").write_bytes(pof)
        evidence = fpga_flash.verify(self.attempt, "flash_proof")
        self.assertEqual((evidence["ufm_blocks"], evidence["configuration_mode"]), (1, "Single Comp Image"))
        self.assertEqual(set(evidence["sources"]), set(fpga_flash.SOURCES))
        self.assertEqual((evidence["init_filename"], evidence["reader"]), ("library.hex", "u_reader"))
        self.assertEqual(evidence["pof"]["user_range_offset"], len(b"POF header"))
        self.assertEqual((evidence["pof"]["cfm0_used_bytes"], evidence["pof"]["cfm0_programmed_bytes"],
                          evidence["pof"]["cfm0_spare_bytes"], evidence["pof"]["library_bytes"]),
                         (5, 4, flash_library.CFM0_BYTES - 5, 8))
        self.assertTrue(evidence["pof"]["user_range_match"])
        (output / "design.fit.summary").write_text("UFM blocks : 0 / 1 ( 0 % )\n")
        with self.assertRaisesRegex(ValueError, "UFM block"):
            fpga_flash.verify(self.attempt, "flash_proof")
        (output / "design.fit.summary").write_text("UFM blocks : 1 / 1 ( 100 % )\n")
        (self.attempt / "design.qsf").write_text(fpga_flash.CONFIGURATION_MODE + "\n")
        with self.assertRaisesRegex(ValueError, "configuration mode or library initialization"):
            fpga_flash.verify(self.attempt, "flash_proof")
        (self.attempt / "design.qsf").write_text("\n".join(fpga_flash.assignments("flash_proof")) + "\n")
        # One altered library byte, a missing or truncated .pof, and a
        # disagreeing .dat each fail.
        altered = bytearray(pof)
        altered[len(b"POF header")] ^= 1
        (output / "design.pof").write_bytes(altered)
        with self.assertRaisesRegex(ValueError, "does not hold the assembled library"):
            fpga_flash.verify(self.attempt, "flash_proof")
        (output / "design.pof").write_bytes(pof[:-len(b"trailer") - 1])
        with self.assertRaisesRegex(ValueError, "ends before the CFM0"):
            fpga_flash.verify(self.attempt, "flash_proof")
        # The assembler enforces the CFM0 fit and emits no .pof otherwise: a
        # missing or empty .pof is the overflow failure, and a CFM0 programmed
        # to its last byte is the accepted boundary with no spare.
        (output / "design.pof").unlink()
        with self.assertRaisesRegex(ValueError, "design.pof"):
            fpga_flash.verify(self.attempt, "flash_proof")
        (output / "design.pof").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "design.pof"):
            fpga_flash.verify(self.attempt, "flash_proof")
        user = flash_library.pof_words(flash_library.words_to_bytes(words))
        full = b"POF header" + user + b"\x5A" * flash_library.CFM0_BYTES + b"trailer"
        (output / "design.pof").write_bytes(full)
        evidence = fpga_flash.verify(self.attempt, "flash_proof")
        self.assertEqual((evidence["pof"]["cfm0_used_bytes"], evidence["pof"]["cfm0_spare_bytes"]),
                         (flash_library.CFM0_BYTES, 0))
        (output / "design.pof").write_bytes(pof)
        (self.attempt / flash_library.DAT_NAME).write_text("@00000 03020100\n")
        with self.assertRaisesRegex(ValueError, "different words"):
            fpga_flash.verify(self.attempt, "flash_proof")
        (self.attempt / flash_library.DAT_NAME).write_text("@00000 03020100\n@22000 80000101\n")
        (self.attempt / flash_library.HEX_NAME).write_text(flash_library.intel_hex(words, count=0x22001))
        with self.assertRaisesRegex(ValueError, "different words"):
            fpga_flash.verify(self.attempt, "flash_proof")

    def compile_log(self):
        path = (self.attempt / fpga_flash.CONTROLLER).resolve().as_posix()
        lines = [f'Warning (10036): Verilog HDL or VHDL warning at {fpga_flash.CONTROLLER}({line}): object "{name}" '
                 f'assigned a value but never read File: {path} Line: {line}' for line, name in fpga_flash.UNUSED_OBJECTS]
        lines += [fpga_flash.STROBE_WARNING.format(node=STROBE)] * 4
        return "Info: fitting\n" + "\n".join(lines) + "\n"

    def staged_sources(self):
        return {name: vendor_support.accepted(self.attempt / name, hashlib.sha256(name.encode()).hexdigest(),
                                              IP + folder + "/" + name, platform="windows")
                for name, folder in fpga_flash.SOURCES.items()}

    def test_explained_diagnostics_are_exact_and_match_the_accepted_source(self):
        sources = self.staged_sources()
        for name in fpga_flash.SOURCES:
            (self.attempt / name).write_text("copy\n")
        text = self.compile_log()
        # The staged copy must carry the accepted digest before any line is explained.
        with self.assertRaisesRegex(ValueError, "staged Intel On-Chip Flash IP source"):
            fpga_flash.explained_diagnostics(text, self.attempt, sources, "flash_proof", "compile.log")
        with unittest.mock.patch.object(fpga_flash, "file_hash",
                                        side_effect=lambda p: sources[Path(p).name]["sha256"]):
            explained = fpga_flash.explained_diagnostics(text, self.attempt, sources, "flash_proof", "compile.log")
            self.assertEqual([item["code"] for item in explained], ["10036"] * 20 + ["332060"])
            self.assertEqual([item["code"] for item in fpga.diagnostics(text, explained)], ["10036"] * 20 + ["332060"] * 4)
            strobe = fpga_flash.STROBE_WARNING.format(node=STROBE)
            (self.attempt / "audit.tcl").write_text("create_timing_netlist\nread_sdc\nupdate_timing_netlist\n")
            audit = fpga_flash.explained_diagnostics(strobe + "\n", self.attempt, sources, "flash_proof", "audit.log")
            self.assertEqual([item["code"] for item in audit], ["332060"])
            # A composed audit updates the netlist once per corner and pass.
            (self.attempt / "audit.tcl").write_text("create_timing_netlist\n" + "update_timing_netlist\n" * 7)
            with self.assertRaisesRegex(ValueError, "strobe clock diagnostic count"):
                fpga_flash.explained_diagnostics(strobe + "\n", self.attempt, sources, "flash_proof", "audit.log")
            self.assertEqual([item["code"] for item in fpga_flash.explained_diagnostics(
                (strobe + "\n") * 7, self.attempt, sources, "flash_proof", "audit.log")], ["332060"])
            (self.attempt / "audit.tcl").write_text("create_timing_netlist\nread_sdc\nupdate_timing_netlist\n")
            for broken in (text.replace("write_count", "read_count", 1), text + strobe + "\n",
                           text.replace(strobe + "\n", "", 1), text.replace("(201)", "(202)", 1)):
                with self.subTest(broken=broken[-80:]):
                    with self.assertRaises(ValueError):
                        fpga_flash.explained_diagnostics(broken, self.attempt, sources, "flash_proof", "compile.log")
            with self.assertRaisesRegex(ValueError, "unsupported flash reader top"):
                fpga_flash.explained_diagnostics(text, self.attempt, sources, "sdram_proof", "compile.log")
        with self.assertRaises(ValueError):
            fpga.diagnostics(text)

    def test_unconstrained_clock_exception_names_only_the_strobe(self):
        report = f"; {STROBE} ;  ; Base ; Unconstrained ;\n; clk_reference ; clk_reference ; Base ; Constrained ;\n"
        self.assertTrue(fpga_flash.accepted_unconstrained_clock(1, TARGET, report))
        for count, target, text in ((2, TARGET, report), (1, {"top": "sdram_proof", "sources": []}, report),
                                    (1, TARGET, report.replace("flash_se_neg_reg", "flash_drclk")),
                                    (1, TARGET, report + report), (1, TARGET, "")):
            with self.subTest(count=count, top=target["top"], text=text[:30]):
                self.assertFalse(fpga_flash.accepted_unconstrained_clock(count, target, text))

    def test_reader_paths_follow_the_instance_pairs(self):
        self.assertEqual(fpga_flash.reader_path("flash_proof"), "u_reader")
        self.assertEqual(fpga_flash.reader_path("v05_proof"), "u_system|u_copier|u_reader")
        self.assertEqual(fpga_flash.reader_path("v05_controls_proof"), "u_controls|u_system|u_copier|u_reader")
        self.assertEqual(fpga_flash.strobe_node("v05_proof"),
                         "n2m_v05_system:u_system|n2m_boot_copier:u_copier|n2m_flash_reader:u_reader|" + fpga_flash.STROBE)
        self.assertTrue(fpga_flash.no_clock_rows("v05_proof")[1][0].startswith(
            "n2m_v05_system:u_system|n2m_boot_copier:u_copier|n2m_flash_reader:u_reader|altera_onchip_flash:u_flash|"))
        with self.assertRaisesRegex(ValueError, "unsupported flash reader top"):
            fpga_flash.reader_path("sdram_proof")

    def test_the_ip_names_one_register_row_and_one_clock_feed_row(self):
        """Only the atom register is an unclocked register; the strobe feeds its clock.

        The fit states that difference in the `Reason` column, which is why each
        owner names the reason with the node: a checker comparing register rows
        must see one of these two, and the audited inventory must hold both.
        """
        rows = fpga_flash.no_clock_rows("flash_proof")
        self.assertEqual(rows[0], (STROBE, fpga_flash.STROBE_REASON))
        self.assertEqual(rows[1][1], fpga_lock.REGISTER_REASON)
        self.assertTrue(rows[1][0].endswith("ufm_block~XE_YE_TO_SE_FF"))
        self.assertNotEqual(fpga_flash.STROBE_REASON, fpga_lock.REGISTER_REASON)

    def test_the_ip_rows_extend_the_parallel_lock_inventory(self):
        """The clocking gate accepts the IP's rows only as part of the one inventory."""
        rows = fpga_flash.no_clock_rows("flash_proof")
        system_row = ("n2m_clocking:u_clocking|n2m_system_pll:u_system_pll|altpll:altpll_component|"
                      "n2m_system_pll_altpll:auto_generated|pll_lock_sync")
        pll_rows = [(fpga_lock.ROW, fpga_lock.REGISTER_REASON), (system_row, fpga_lock.REGISTER_REASON)]
        checks = no_clock_table(pll_rows + list(rows))
        netlist = "module flash_proof (a);\ninput a;\nendmodule\n"
        # Each of the IP's two rows is named on its own when the inventory drops it.
        for dropped in rows:
            kept = pll_rows + [row for row in rows if row != dropped]
            with self.subTest(dropped=dropped[0][-40:]), self.assertRaisesRegex(
                    ValueError, "no owner claims no-clock row " + re.escape(dropped[0])):
                fpga_lock.verify_parallel(netlist, checks, "flash_proof", rows=kept)
        # With the IP's rows in the inventory the table matches and the netlist checks proceed.
        with self.assertRaises(ValueError) as caught:
            fpga_lock.verify_parallel(netlist, checks, "flash_proof", rows=pll_rows + list(rows))
        self.assertNotIn("no-clock row", str(caught.exception))


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
