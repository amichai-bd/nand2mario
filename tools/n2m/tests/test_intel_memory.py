"""Installed-model dependency checks with fake execution, never RTL evidence."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
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
        def run(argv, cwd=None, **_):
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
                (cwd / "waves/simulation.wlf").write_text("fake wave")
            return SimpleNamespace(returncode=0, stdout="PASS builder-smoke\nErrors: 0, Warnings: 0")
        self.sim.run = run

    def questa(self):
        return SimpleNamespace(tools={name: name for name in ("vlib", "vmap", "vlog", "vsim")}, path=str)

    def test_explicit_source_binding_and_commands(self):
        self.prepare_model()
        target = read_json(self.root / "src/dv/builder/targets.json")["builder-smoke"]
        descriptor = intel_memory.resolve(self.root, self.questa(), target, str(self.models))
        self.assertEqual(descriptor["sources"][0]["sha256"], file_hash(self.source))
        self.assertEqual(descriptor["binding_options"], ["-L", "n2m_altera_mf"])
        compile_commands, map_commands, binding = intel_memory.commands(self.questa(), self.build, self.build, descriptor)
        compiler = next(argv for argv, *_ in compile_commands if argv[0] == "vlog")
        self.assertEqual(compiler[-1], str(self.source))
        self.assertEqual(binding, ["-L", "n2m_altera_mf"])
        self.assertEqual(len(map_commands), 1)

    def test_changed_or_missing_source_is_refused(self):
        self.prepare_model()
        target = read_json(self.root / "src/dv/builder/targets.json")["builder-smoke"]
        self.source.write_text("// Different host-test dependency bytes\n")
        with self.assertRaisesRegex(ValueError, "unsupported Intel memory model hash"):
            intel_memory.resolve(self.root, self.questa(), target, str(self.models))
        self.source.unlink()
        with self.assertRaisesRegex(ValueError, "missing Intel memory model source"):
            intel_memory.resolve(self.root, self.questa(), target, str(self.models))
        with self.assertRaisesRegex(ValueError, "missing Intel simulation library"):
            intel_memory.resolve(self.root, self.questa(), target, str(self.models / "absent"))

    def test_a_vendor_model_target_runs_through_the_selected_questa_binding(self):
        from n2m.simulation import load_target
        self.prepare_model()
        self.assertEqual(load_target(self.root, "builder-smoke")[0]["vendor_model"], "intel-memory")
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        targets["builder-smoke"]["simulators"] = ["questa"]
        registry.write_text(json.dumps(targets))
        self.sim.backend = "questa"
        self.sim.compiler = "vlog"
        self.sim.tools = {name: name for name in ("vlib", "vmap", "vlog", "vsim")}
        self.sim.info = {"backend": "questa", "tools": {name: {"path": name}
                                                         for name in self.sim.tools}}
        result = self.run_stage()
        self.assertEqual((result["status"], result["simulator"]), ("PASS", "questa"), result)
        self.assertEqual(result["options"]["vendor_model"]["selection"], "intel-memory")
        self.assertTrue(any(argv[0] == "vsim" for argv in self.sim.calls))

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
            model = file_hash(quartus / "eda/sim_lib/altera_mf.v")
            # The exemption is named, so a family nobody has considered is checked
            # like MAX 10. Only Cyclone V, which compiles no simulation model,
            # records the installed hash as found.
            for family in ("MAX 10", "Arria V", "", None):
                with self.subTest(family=family), self.assertRaisesRegex(ValueError, "differs from the reviewed"):
                    fpga_intel_memory.identity(quartus / "bin64", family=family)
            exempt = fpga_intel_memory.identity(quartus / "bin64", family="Cyclone V")
            self.assertEqual(exempt["model"]["sha256"], model)
            # With the pin satisfied, every family is accepted and records it.
            with patch.object(fpga_intel_memory, "MIXED_MODE_MODEL_HASH", model):
                for family in ("MAX 10", "Cyclone V"):
                    with self.subTest(pinned=family):
                        recorded = fpga_intel_memory.identity(quartus / "bin64", family=family)
                        self.assertEqual(recorded["model"]["sha256"], model)


if __name__ == "__main__":
    unittest.main()
