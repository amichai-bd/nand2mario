"""On-Chip Flash IP staging, diagnostics and evidence contracts with fixture files; no Quartus needed."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import fpga, fpga_flash, fpga_lock, flash_library

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
        (self.quartus / "bin64").mkdir(parents=True)
        (self.quartus / "eda/sim_lib").mkdir(parents=True)
        (self.quartus / "eda/sim_lib/fiftyfivenm_atoms.v").write_text("atoms\n")
        for name, (folder, _) in fpga_flash.SOURCES.items():
            path = self.ip / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"// {name}\n")
        for name in fpga_flash.DEFINITIONS:
            (self.ip / "altera_onchip_flash" / name).write_text(f"# {name}\n")

    def sources(self):
        """An identity record whose hashes match the pins, as identity() would return for the real files."""
        return {name: {"path": str(self.ip / folder / name), "sha256": sha}
                for name, (folder, sha) in fpga_flash.SOURCES.items()}

    def test_identity_refuses_an_unpinned_vendor_file(self):
        with self.assertRaisesRegex(ValueError, "unsupported Intel On-Chip Flash IP source"):
            fpga_flash.identity(self.quartus / "bin64")
        (self.ip / "rtl/altera_onchip_flash_block.v").unlink()
        with self.assertRaisesRegex(ValueError, "missing installed Intel On-Chip Flash IP"):
            fpga_flash.identity(self.quartus / "bin64")

    def test_stage_copies_only_unchanged_pinned_files(self):
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
        with self.assertRaisesRegex(ValueError, "unsupported flash reader top"):
            fpga_flash.assignments("v05_proof")
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
        sources = {}
        for name, (_, sha) in fpga_flash.SOURCES.items():
            sources[name] = {"path": str(self.attempt / name), "sha256": sha}
        return sources

    def test_explained_diagnostics_are_exact_and_pinned(self):
        sources = self.staged_sources()
        for name in fpga_flash.SOURCES:
            (self.attempt / name).write_text("copy\n")
        text = self.compile_log()
        # The staged copy must carry the pinned hash before any line is explained.
        with self.assertRaisesRegex(ValueError, "unsupported Intel On-Chip Flash IP source"):
            fpga_flash.explained_diagnostics(text, self.attempt, sources, "flash_proof", "compile.log")
        with unittest.mock.patch.object(fpga_flash, "file_hash", side_effect=lambda p: fpga_flash.SOURCES[Path(p).name][1]):
            explained = fpga_flash.explained_diagnostics(text, self.attempt, sources, "flash_proof", "compile.log")
            self.assertEqual([item["code"] for item in explained], ["10036"] * 20 + ["332060"])
            self.assertEqual([item["code"] for item in fpga.diagnostics(text, explained)], ["10036"] * 20 + ["332060"] * 4)
            strobe = fpga_flash.STROBE_WARNING.format(node=STROBE)
            audit = fpga_flash.explained_diagnostics(strobe + "\n", self.attempt, sources, "flash_proof", "audit.log")
            self.assertEqual([item["code"] for item in audit], ["332060"])
            for broken in (text.replace("write_count", "read_count", 1), text + strobe + "\n",
                           text.replace(strobe + "\n", "", 1), text.replace("(201)", "(202)", 1)):
                with self.subTest(broken=broken[-80:]):
                    with self.assertRaises(ValueError):
                        fpga_flash.explained_diagnostics(broken, self.attempt, sources, "flash_proof", "compile.log")
            with self.assertRaisesRegex(ValueError, "unsupported flash reader top"):
                fpga_flash.explained_diagnostics(text, self.attempt, sources, "v05_proof", "compile.log")
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

    def test_no_clock_rows_extend_the_parallel_lock_inventory(self):
        rows = fpga_flash.no_clock_rows("flash_proof")
        self.assertEqual(rows[0], STROBE)
        self.assertTrue(rows[1].endswith("ufm_block~XE_YE_TO_SE_FF"))
        checks = "".join(f"; {row} ; No clock feeds this register's clock port. ;\n" for row in
                         (fpga_lock.ROW, "n2m_clocking:u_clocking|n2m_system_pll:u_system_pll|altpll:altpll_component|"
                          "n2m_system_pll_altpll:auto_generated|pll_lock_sync", rows[1]))
        with self.assertRaisesRegex(ValueError, "parallel lock event inventory differs"):
            fpga_lock.verify_parallel("module flash_proof (a);\ninput a;\nendmodule\n", checks, "flash_proof")
        # With the atom row accounted for, the inventory matches and the netlist checks proceed.
        with self.assertRaises(ValueError) as caught:
            fpga_lock.verify_parallel("module flash_proof (a);\ninput a;\nendmodule\n", checks, "flash_proof", extra_rows=rows[1:])
        self.assertNotIn("inventory", str(caught.exception))


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
