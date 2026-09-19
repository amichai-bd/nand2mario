"""Installed-model dependency checks with fake execution, never RTL evidence."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tempfile

import test_builder
import vendor_support
from n2m import intel_memory, fpga_intel_memory, vendor_sources
from n2m.questa import diagnostic
from n2m.records import file_hash, read_json

MODEL = "quartus/eda/sim_lib/altera_mf.v"
DEFINITION = "quartus/libraries/megafunctions/altsyncram.tdf"
DECLARATION = "quartus/libraries/megafunctions/altsyncram.inc"


class IntelMemoryTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def prepare_model(self, accepted=True):
        self.models = self.root / "installation with spaces/quartus/eda/sim_lib"
        self.models.mkdir(parents=True)
        self.source = self.models / "altera_mf.v"
        self.source.write_text("// Original host-test dependency bytes; not a vendor simulation model.\n")
        vendor_support.installation(self.models.parents[2])
        self.ledger = vendor_support.ledger(
            self, self.root / "workdir/test-ledger.json",
            {MODEL: file_hash(self.source)} if accepted else {})
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
        self.assertEqual(descriptor["sources"][0]["source"], MODEL)
        self.assertEqual(descriptor["sources"][0]["accepted"], "unchanged")
        self.assertEqual(descriptor["binding_options"], ["-L", "n2m_altera_mf"])
        compile_commands, map_commands, binding = intel_memory.commands(self.questa(), self.build, self.build, descriptor)
        compiler = next(argv for argv, *_ in compile_commands if argv[0] == "vlog")
        self.assertEqual(compiler[-1], str(self.source))
        self.assertEqual(binding, ["-L", "n2m_altera_mf"])
        self.assertEqual(len(map_commands), 1)

    def test_changed_source_is_refused_and_a_new_one_is_recorded(self):
        """A vendor file changing under accepted evidence fails; a first sighting records."""
        self.prepare_model()
        target = read_json(self.root / "src/dv/builder/targets.json")["builder-smoke"]
        accepted = file_hash(self.source)
        self.source.write_text("// Different host-test dependency bytes\n")
        with self.assertRaisesRegex(ValueError, "changed since it was accepted") as raised:
            intel_memory.resolve(self.root, self.questa(), target, str(self.models))
        message = str(raised.exception)
        for part in (MODEL, "linux", accepted, file_hash(self.source), "vendor accept"):
            self.assertIn(part, message)
        # The refused digest is never written: the ledger still holds the accepted one.
        self.assertEqual(read_json(self.ledger)["installations"]["linux"]["sources"][MODEL], accepted)

    def test_first_sighting_records_the_installed_source(self):
        self.prepare_model(accepted=False)
        target = read_json(self.root / "src/dv/builder/targets.json")["builder-smoke"]
        descriptor = intel_memory.resolve(self.root, self.questa(), target, str(self.models))
        self.assertEqual(descriptor["sources"][0]["accepted"], "recorded")
        entry = read_json(self.ledger)["installations"]["linux"]
        self.assertEqual(entry["sources"], {MODEL: file_hash(self.source)})
        self.assertEqual(entry["quartus"], "0.0 host-test")
        self.assertEqual(vendor_sources.notices({"model": descriptor["sources"][0]}),
                         [vendor_sources.NOTICE.format(installation="linux", source=MODEL,
                                                       sha256=file_hash(self.source))])
        # The second run compares against what the first recorded.
        again = intel_memory.resolve(self.root, self.questa(), target, str(self.models))
        self.assertEqual(again["sources"][0]["accepted"], "unchanged")

    def test_missing_source_and_library_are_refused(self):
        self.prepare_model()
        target = read_json(self.root / "src/dv/builder/targets.json")["builder-smoke"]
        self.source.unlink()
        with self.assertRaisesRegex(ValueError, "missing Intel memory model source"):
            intel_memory.resolve(self.root, self.questa(), target, str(self.models))
        with self.assertRaisesRegex(ValueError, "missing Intel simulation library"):
            intel_memory.resolve(self.root, self.questa(), target, str(self.models / "absent"))

    def select_questa(self):
        from n2m.simulation import load_target
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

    def test_a_vendor_model_target_runs_through_the_selected_questa_binding(self):
        self.prepare_model()
        self.select_questa()
        result = self.run_stage()
        self.assertEqual((result["status"], result["simulator"]), ("PASS", "questa"), result)
        self.assertEqual(result["options"]["vendor_model"]["selection"], "intel-memory")
        self.assertTrue(any(argv[0] == "vsim" for argv in self.sim.calls))
        # Nothing was first-sighted, so the record carries no vendor notice.
        self.assertEqual([line for line in result["notices"] if "Recorded vendor source" in line], [])

    def test_a_first_sighting_is_named_in_the_simulation_record(self):
        """The Questa path reports a first sighting the way `fpga build` does.

        Without this the only signals are the descriptor field and the ledger
        diff, and the decision requires a first run to record rather than pass
        silently.
        """
        self.prepare_model(accepted=False)
        self.select_questa()
        result = self.run_stage()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["notices"][-1],
                         vendor_sources.NOTICE.format(installation="linux", source=MODEL,
                                                      sha256=file_hash(self.source)))
        self.assertEqual(result["options"]["vendor_model"]["sources"][0]["accepted"], "recorded")

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
        self.model = "a" * 64
        self.descriptor = {"mixed_mode_instances": [self.instance],
                           "sources": [{"name": intel_memory.MIXED_MODE_MODEL,
                                        **vendor_support.accepted("/vendor/altera_mf.v", self.model, MODEL)}]}
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

    def test_unrecorded_or_undeclared_warning_cannot_be_classified(self):
        """The classifier explains a specific model's warning, so it refuses a
        descriptor whose model never reached the accepted record."""
        self.assertEqual(intel_memory.classify_diagnostics(self.pair, self.descriptor)[1][0]["model_sha256"],
                         self.model)
        del self.descriptor["sources"][0]["accepted"]
        with self.assertRaisesRegex(ValueError, "not an accepted ledger record"):
            intel_memory.classify_diagnostics(self.pair, self.descriptor)
        checked, evidence = intel_memory.classify_diagnostics(self.pair, None)
        self.assertEqual(evidence, [])
        self.assertEqual(diagnostic(checked), "unexplained simulator warning")

    def test_synthesis_refuses_a_changed_model_and_keeps_the_named_exemption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = vendor_support.installation(Path(directory), platform="windows")
            quartus = root / "quartus"
            bin64 = quartus / "bin64"
            ledger = vendor_support.ledger(self, root / "ledger.json", platform="windows")
            with self.assertRaisesRegex(ValueError, "missing installed"):
                fpga_intel_memory.identity(bin64)
            for relative in ("libraries/megafunctions/altsyncram.tdf",
                             "libraries/megafunctions/altsyncram.inc", "eda/sim_lib/altera_mf.v"):
                path = quartus / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Original test bytes, not an Intel implementation.")
            model = file_hash(quartus / "eda/sim_lib/altera_mf.v")
            # Nothing is recorded yet, so the first build records all three and says so.
            first = fpga_intel_memory.identity(bin64)
            self.assertEqual((first["model"]["sha256"], first["model"]["accepted"]), (model, "recorded"))
            self.assertEqual(set(read_json(ledger)["installations"]["windows"]["sources"]),
                             {MODEL, DEFINITION, DECLARATION})
            # Every family synthesizes through the definition and declaration, so
            # both are compared whether or not the model is.
            for name in ("definition", "declaration"):
                self.assertEqual(first[name]["accepted"], "recorded")
            # The exemption is named, so a family nobody has considered is checked
            # like MAX 10. Only Cyclone V, which compiles no simulation model,
            # records the installed hash as found.
            (quartus / "eda/sim_lib/altera_mf.v").write_text("Different original test bytes.")
            changed = file_hash(quartus / "eda/sim_lib/altera_mf.v")
            for family in ("MAX 10", "Arria V", "", None):
                with self.subTest(family=family), self.assertRaisesRegex(ValueError, "changed since it was accepted"):
                    fpga_intel_memory.identity(bin64, family=family)
            exempt = fpga_intel_memory.identity(bin64, family="Cyclone V")
            self.assertEqual(exempt["model"]["sha256"], changed)
            self.assertNotIn("accepted", exempt["model"])
            # The exemption covers the simulation model alone: the exempt family's
            # own synthesis inputs are still compared.
            self.assertEqual(exempt["definition"]["accepted"], "unchanged")
            (quartus / "libraries/megafunctions/altsyncram.tdf").write_text("Different original test bytes.")
            with self.assertRaisesRegex(ValueError, "changed since it was accepted"):
                fpga_intel_memory.identity(bin64, family="Cyclone V")
            (quartus / "libraries/megafunctions/altsyncram.tdf").write_text(
                "Original test bytes, not an Intel implementation.")
            # With the change accepted, every family builds and records it as unchanged.
            record = vendor_sources.accept(bin64, [MODEL], "Reviewed original host-test bytes for this test.")
            self.assertEqual(record["changed"], {MODEL: {"from": model, "to": changed}})
            for family in ("MAX 10", "Cyclone V"):
                with self.subTest(accepted=family):
                    recorded = fpga_intel_memory.identity(bin64, family=family)
                    self.assertEqual(recorded["model"]["sha256"], changed)


if __name__ == "__main__":
    unittest.main()
