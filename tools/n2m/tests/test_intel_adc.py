"""Host-only ADC dependency and binding checks; no simulated ADC evidence."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import test_builder
from n2m import intel_adc, intel_memory, fpga_adc
from n2m.records import file_hash
from n2m.questa import diagnostic


class IntelAdcTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ADC host space ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.installation = self.root / "installation"
        self.folder = self.installation / "quartus/eda/sim_lib"
        self.folder.mkdir(parents=True)
        self.source = self.folder / "host-only.txt"
        self.source.write_text("Original host-test bytes, not an ADC model.")
        (self.root / "tools/n2m").mkdir(parents=True)
        (self.root / "tools/n2m/dependencies.json").write_text(json.dumps({"intel_adc": {
            "version": "host-test", "sources": {"quartus/eda/sim_lib/host-only.txt": file_hash(self.source)}}}))
        self.sim = SimpleNamespace(tools={name: name for name in ("vlib", "vmap", "vlog", "vsim")})
        self.sim.tools["vsim"] = str(self.installation / "questa_fse/win64/vsim.exe")
        self.generation = {"generator": {"path": str(self.installation / "quartus/bin64/qmegawiz.exe"), "sha256": "host-only"}}

    def resolve(self, directory=None):
        with patch.object(fpga_adc, "identity", return_value=self.generation):
            return intel_memory.resolve(self.root, self.sim, {"vendor_model": "intel-adc"}, directory)

    def test_selected_installation_explicit_path_and_exact_binding(self):
        descriptor = self.resolve()
        self.assertEqual(descriptor, self.resolve(self.folder))
        self.assertEqual(descriptor["sources"][0]["sha256"], file_hash(self.source))
        self.assertEqual(descriptor["generation_inputs"], self.generation)
        compiler, run = self.root / "compile", self.root / "run"
        commands, maps, binding = intel_memory.commands(self.sim, compiler, run, descriptor)
        self.assertEqual(commands[0][0], fpga_adc.generation_command(self.generation))
        self.assertEqual(commands[3][0], ["vlog", "-work", "n2m_intel_adc_atoms", str(self.source)])
        self.assertEqual(commands[6][0], ["vlog", "-work", "n2m_intel_adc", str(compiler / "n2m_adc_pll.v")])
        self.assertEqual(maps[0][0], ["vmap", "n2m_intel_adc", (compiler / "n2m_intel_adc").as_posix()])
        self.assertEqual(binding, ["-L", "n2m_intel_adc", "-L", "n2m_intel_adc_atoms"])

    def test_canonical_control_source_is_separate_from_embedded_sync(self):
        descriptor = self.resolve()
        canonical = {"name": "quartus/libraries/megafunctions/altera_std_synchronizer.v",
                     "path": str(self.installation / "canonical.v"), "sha256": "host-only"}
        descriptor["sources"].append(canonical)
        commands, _, _ = intel_adc.commands(self.sim, self.root, self.root, descriptor)
        self.assertNotIn(canonical["path"], commands[3][0])
        self.assertIn(canonical["path"], commands[6][0])
        self.assertNotIn(str(self.source), commands[6][0])

    def test_exact_lexical_warning_visible_and_all_variants_rejected(self):
        descriptor = {"sources": [{"name": intel_adc.TOP_SOURCE, "path": "C:/vendor/top.v", "sha256": intel_adc.TOP_HASH}]}
        warning = "** Warning: (vlog-2083) C:/vendor/top.v(24): Carriage return (0x0D) is not followed by a newline (0x0A)."
        raw = warning + "\nErrors: 0, Warnings: 1\n"
        checked, evidence = intel_adc.classify_compile_diagnostics(raw, descriptor, "intel-adc-control-compile.log")
        self.assertIsNone(diagnostic(checked))
        self.assertEqual(evidence[0]["raw"], warning)
        self.assertEqual(evidence[0]["warning_count"], 1)
        self.assertEqual(evidence[0]["raw_summary"], "Errors: 0, Warnings: 1")
        for bad in ("Errors: 0, Warnings: 0\n", raw + warning, raw.replace("(24)", "(25)"),
                    raw.replace("top.v", "other.v"), raw.replace("2083", "2275"),
                    raw.replace("Warnings: 1", "Warnings: 2"), raw.replace("Errors: 0", "Errors: 1"),
                    raw + "** Warning: other\n", raw + "Errors: 0, Warnings: 1\n"):
            with self.assertRaisesRegex(ValueError, "diagnostic count, location, or summary"):
                intel_adc.classify_compile_diagnostics(bad, descriptor, "intel-adc-control-compile.log")
        for stage in ("sim.log", "intel-adc-atoms-compile.log", "compile.log"):
            with self.assertRaisesRegex(ValueError, "control compilation stage"):
                intel_adc.classify_compile_diagnostics(raw, descriptor, stage)
        descriptor["sources"][0]["sha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "supported wrapper hash"):
            intel_adc.classify_compile_diagnostics(raw, descriptor, "intel-adc-control-compile.log")

    def test_changed_or_missing_dependency_rejected_before_commands(self):
        self.resolve()
        self.source.write_text("changed")
        with self.assertRaisesRegex(ValueError, "unsupported installed Intel ADC source"):
            self.resolve()
        self.source.unlink()
        with self.assertRaisesRegex(ValueError, "unsupported installed Intel ADC source"):
            self.resolve()

    def test_repository_shadow_rejected(self):
        source = self.root / "source.sv"
        source.write_text("// module altpll;\nmodule original; endmodule")
        intel_adc.reject_shadow_models(self.root, ["source.sv"])
        for name in ("altpll", "n2m_adc_pll", "fiftyfivenm_adcblock_encrypted", "altera_modular_adc_control", "altera_std_synchronizer"):
            source.write_text("module " + name + "; endmodule")
            with self.assertRaisesRegex(ValueError, "shadows installed ADC/PLL model"):
                intel_adc.reject_shadow_models(self.root, ["source.sv"])

    def test_generated_parameter_validation_and_hash(self):
        values = {"clk0_divide_by": "1", "clk0_multiply_by": "1", "clk0_duty_cycle": "50",
                  "clk0_phase_shift": '"0"', "inclk0_input_frequency": "100000",
                  "intended_device_family": '"MAX 10"', "operation_mode": '"NO_COMPENSATION"',
                  "port_areset": '"PORT_USED"', "port_locked": '"PORT_USED"'}
        text = "\n".join("altpll_component." + key + " = " + value + ";" for key, value in values.items())
        generated = self.root / "n2m_adc_pll.v"
        generated.write_text(text)
        self.assertEqual(intel_adc.verify_generated(self.root)["sha256"], file_hash(generated))
        generated.write_text(text.replace("100000", "200000"))
        with self.assertRaisesRegex(ValueError, "parameter mismatch"):
            intel_adc.verify_generated(self.root)

    def test_adc_does_not_classify_memory_warnings(self):
        raw = "Warning: unexpected ADC response"
        self.assertEqual(intel_memory.classify_diagnostics(raw, self.resolve()), (raw, []))


if __name__ == "__main__":
    unittest.main()
