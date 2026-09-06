"""Installed-model dependency checks with fake execution, never RTL evidence."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile

import test_builder
from n2m import intel_memory, fpga_intel_memory
from n2m.questa import diagnostic
from n2m.records import file_hash, read_json


class IntelMemoryTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def prepare_model(self):
        self.models = self.root / "installation with spaces/quartus/eda/sim_lib"
        self.models.mkdir(parents=True)
        self.source = self.models / "altera_mf.v"
        self.source.write_text("// Original host-test dependency bytes; not a vendor simulation model.\n")
        self.pin_path = self.root / "tools/n2m/dependencies.json"
        self.pins = read_json(self.pin_path)
        self.pins["intel_memory"]["sources"]["altera_mf.v"] = file_hash(self.source)
        self.pin_path.write_text(json.dumps(self.pins))
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        targets["builder-smoke"]["vendor_model"] = "intel-memory"
        registry.write_text(json.dumps(targets))
        self.args.intel_sim_lib = str(self.models)
        def run(argv, cwd=None):
            self.sim.calls.append(argv)
            if argv[0] == "vlib":
                (cwd / argv[1]).mkdir()
            if argv[0] == "vmap" and "-c" in argv:
                (cwd / "modelsim.ini").write_text("test mappings")
            if argv[0] == "vlog":
                library = argv[argv.index("-work") + 1]
                (cwd / library / "compiled.bin").write_text("fake compilation artifact")
            if argv[0] == "vsim":
                (cwd / "waves/smoke.vcd").write_text("fake wave")
            return SimpleNamespace(returncode=0, stdout="PASS builder-smoke\nErrors: 0, Warnings: 0")
        self.sim.run = run

    def test_explicit_source_binding_and_unchanged_cache(self):
        self.prepare_model()
        first = self.run_stage()
        self.assertEqual(first["status"], "PASS")
        descriptor = first["options"]["vendor_model"]
        self.assertEqual(descriptor["sources"][0]["sha256"], file_hash(self.source))
        self.assertEqual(descriptor["binding_options"], ["-L", "n2m_altera_mf"])
        compiler = next(call for call in self.sim.calls if call[0] == "vlog" and "n2m_altera_mf" in call)
        self.assertEqual(compiler[-1], str(self.source))
        runtime = next(call for call in self.sim.calls if call[0] == "vsim")
        self.assertEqual(runtime[runtime.index("-L") + 1], "n2m_altera_mf")
        count = len(self.sim.calls)
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        self.assertEqual(len(self.sim.calls), count)

    def test_changed_source_cannot_reuse_prior_success(self):
        self.prepare_model()
        first = self.run_stage()
        count = len(self.sim.calls)
        self.source.write_text("// Different host-test dependency bytes\n")
        with self.assertRaisesRegex(ValueError, "unsupported Intel memory model hash"):
            self.run_stage()
        self.assertEqual(len(self.sim.calls), count)
        # A reviewed dependency pin change must also invalidate the prior build.
        self.pins["intel_memory"]["sources"]["altera_mf.v"] = file_hash(self.source)
        self.pin_path.write_text(json.dumps(self.pins))
        second = self.run_stage()
        self.assertEqual(second["status"], "PASS")
        self.assertEqual(second["cache"], "BUILT")
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_missing_model_cannot_reuse_prior_success(self):
        self.prepare_model()
        self.run_stage()
        self.source.unlink()
        count = len(self.sim.calls)
        with self.assertRaisesRegex(ValueError, "missing Intel memory model source"):
            self.run_stage()
        self.assertEqual(len(self.sim.calls), count)
        self.args.intel_sim_lib = str(self.models / "absent")
        with self.assertRaisesRegex(ValueError, "missing Intel simulation library"):
            self.run_stage()

    def test_selected_tool_installation_discovery(self):
        self.prepare_model()
        self.args.intel_sim_lib = None
        self.sim.tools["vsim"] = str(self.models.parents[2] / "questa_fse/win64/vsim.exe")
        descriptor = intel_memory.resolve(self.root, self.sim, {"vendor_model": "intel-memory"})
        self.assertEqual(Path(descriptor["sources"][0]["path"]), self.source)

    def test_wrong_library_and_repository_shadow_are_rejected(self):
        self.prepare_model()
        with self.assertRaisesRegex(ValueError, "unsupported vendor model"):
            intel_memory.resolve(self.root, self.sim, {"vendor_model": "portable"}, self.models)
        source = self.root / "src/dv/builder/tb_smoke.sv"
        source.write_text("module altsyncram; endmodule\n")
        with self.assertRaisesRegex(ValueError, "shadows the installed"):
            intel_memory.reject_shadow_models(self.root, [source.relative_to(self.root).as_posix()])


class IntelDiagnosticTests(unittest.TestCase):
    instance = "tb_intel_ram.frame_case.dut.ram.m_default.altsyncram_inst"

    def setUp(self):
        self.descriptor = {"mixed_mode_instances": [self.instance],
                           "sources": [{"name": "altera_mf.v", "sha256": intel_memory.MIXED_MODE_MODEL_HASH}]}
        self.pair = ("# Warning: read_during_write_mode_mixed_ports is assumed as               OLD_DATA\n"
                     f"# Time: 0  Instance: {self.instance}")

    def test_exact_pair_is_recorded_without_changing_raw_input(self):
        raw = self.pair + "\n# Errors: 0, Warnings: 0\n"
        checked, evidence = intel_memory.classify_diagnostics(raw, self.descriptor)
        self.assertIsNone(diagnostic(checked))
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["raw"], self.pair)
        self.assertEqual(evidence[0]["instance"], self.instance)
        self.assertIn(self.pair, raw)

    def test_missing_duplicate_wrong_time_and_instance_fail(self):
        for raw in ("", self.pair + "\n" + self.pair,
                    self.pair.replace("Time: 0", "Time: 1"),
                    self.pair.replace("frame_case", "byte_case"),
                    self.pair.replace("OLD_DATA", "NEW_DATA")):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "count or instance"):
                intel_memory.classify_diagnostics(raw, self.descriptor)

    def test_other_warning_and_nonzero_summary_remain_failures(self):
        for extra in ("# Warning: other issue", "# Errors: 0, Warnings: 1"):
            checked, _ = intel_memory.classify_diagnostics(self.pair + "\n" + extra, self.descriptor)
            self.assertEqual(diagnostic(checked), "unexplained simulator warning")

    def test_unpinned_or_undeclared_warning_cannot_be_classified(self):
        self.descriptor["sources"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "reviewed model source hash"):
            intel_memory.classify_diagnostics(self.pair, self.descriptor)
        checked, evidence = intel_memory.classify_diagnostics(self.pair, None)
        self.assertEqual(evidence, [])
        self.assertEqual(diagnostic(checked), "unexplained simulator warning")

    def test_synthesis_rejects_missing_or_different_model(self):
        with tempfile.TemporaryDirectory() as directory:
            quartus = Path(directory)
            with self.assertRaisesRegex(ValueError, "missing installed"):
                fpga_intel_memory.identity(quartus / "bin64")
            for relative in ("libraries/megafunctions/altsyncram.tdf",
                             "libraries/megafunctions/altsyncram.inc", "eda/sim_lib/altera_mf.v"):
                path = quartus / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Original test bytes, not an Intel implementation.")
            with self.assertRaisesRegex(ValueError, "differs from the reviewed"):
                fpga_intel_memory.identity(quartus / "bin64")


if __name__ == "__main__":
    unittest.main()
