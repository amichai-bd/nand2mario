"""Cyclone V clocking evidence: family refusal, generated HDL, fit report, netlist.

The fixtures are abstract, not copied vendor output: each states the shape the
checks accept, then mutates it one way at a time so every rejection is proved.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.n2m import fpga, fpga_clocking, fpga_lock_cyclonev, fpga_pll, fpga_pll_cyclonev as cv

ROOT = Path(__file__).resolve().parents[3]
LITE_DEFINITION = {"module": "n2m_pixel_pll", "input_ps": 20000, "multiply": 63, "divide": 125, "system_divide": 2}


def scratch():
    directory = ROOT / "workdir/fpga-cyclonev-tests"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class FamilyRefusalTests(unittest.TestCase):
    """A family without a clocking implementation refuses; it never skips checks."""

    def test_unimplemented_family_has_no_implementation(self):
        for family in ("Arria V", "Cyclone 10 LP", "MAX 10 ", "", None, 10):
            with self.subTest(family=family), self.assertRaises(ValueError) as error:
                fpga_clocking.implementation(family)
            self.assertIn("no clocking evidence implementation for FPGA family", str(error.exception))

    def test_implemented_families_expose_the_whole_surface(self):
        surface = ("TOOLS_KEY", "SUPPORTED_TOPS", "SYSTEM_CLOCK", "PIXEL_CLOCK", "SYSTEM_NET", "validate",
                   "identity", "generate", "verify", "verify_fit", "verify_lock_event", "generated_sources",
                   "assignments", "cache_files", "timed_clocks", "corner_slacks", "lock_event_count",
                   "explained_diagnostics")
        for family in fpga_clocking.IMPLEMENTATIONS:
            module = fpga_clocking.implementation(family)
            for name in surface:
                with self.subTest(family=family, name=name):
                    self.assertTrue(hasattr(module, name), f"{family} is missing {name}")

    def test_pll_target_on_an_unimplemented_family_refuses_the_build(self):
        """The refusal happens in target_definition, before any tool is launched."""
        board = {"name": "Probe", "device": "5AGXFB3H4F35C4", "family": "Arria V",
                 "timing_corners": ["Slow 900mV 85C", "Slow 900mV 0C", "Fast 900mV 0C"],
                 "specification": "wiki/src/de10-nano-board.md"}
        target = json.loads(json.dumps(fpga.target_definition(ROOT, "nano-clocking")))
        for key in ("family", "timing_corners"):
            target.pop(key)
        target["device"] = board["device"]
        entry = {"probe-clocking": ("src/fpga/de10_nano/targets.json", board, target)}
        with patch.object(fpga, "board_registries", return_value=entry):
            with self.assertRaises(ValueError) as error:
                fpga.target_definition(ROOT, "probe-clocking")
        self.assertIn("no clocking evidence implementation for FPGA family: 'Arria V'", str(error.exception))

    def test_registered_boards_with_generated_clocks_have_an_implementation(self):
        """Every registered target that declares a PLL resolves an implementation."""
        for name, (_, board, target) in sorted(fpga.board_registries(ROOT).items()):
            if "pll" not in target:
                continue
            with self.subTest(target=name):
                module = fpga_clocking.implementation(board["family"])
                module.validate(target["pll"])
                self.assertIn(target["top"], module.SUPPORTED_TOPS)


class DefinitionTests(unittest.TestCase):
    def test_only_the_contract_definition_is_accepted(self):
        cv.validate(cv.DEFINITION)
        for bad in ({**cv.DEFINITION, "multiply": 64}, {**cv.DEFINITION, "system_divide": 3},
                    {k: v for k, v in cv.DEFINITION.items() if k != "system_divide"},
                    LITE_DEFINITION, {}, {**cv.DEFINITION, "extra": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cv.validate(bad)

    def test_requested_frequencies_come_from_the_definition(self):
        values = cv.frequencies(cv.DEFINITION)
        self.assertEqual([float(values["reference"]), float(values[cv.SYSTEM_MODULE]), float(values[cv.PIXEL_MODULE])],
                         [50.0, 25.0, 25.2])

    def test_generation_command_states_family_device_and_frequency(self):
        identity = {"generator": {"path": "/quartus/ip-generate"}}
        command = cv.generation_command(identity, cv.DEFINITION, cv.PIXEL_MODULE, "5CSEBA6U23I7")
        self.assertEqual(command[0], "/quartus/ip-generate")
        for expected in ("--component-name=altera_pll", "--output-name=" + cv.PIXEL_MODULE,
                         "--component-parameter=gui_en_adv_params=1",
                         "--component-parameter=gui_multiply_factor=63",
                         "--component-parameter=gui_divide_factor_n=5",
                         "--component-parameter=gui_divide_factor_c0=25",
                         "--component-parameter=gui_reference_clock_frequency=50.0",
                         "--component-parameter=gui_operation_mode=direct",
                         "--component-parameter=gui_use_locked=1",
                         "--part=5CSEBA6U23I7", "--system-info=DEVICE_FAMILY=Cyclone V"):
            self.assertIn(expected, command)
        # No desired frequency is requested at all: the counters state the VCO.
        self.assertFalse([item for item in command if "gui_output_clock_frequency" in item])
        system = cv.generation_command(identity, cv.DEFINITION, cv.SYSTEM_MODULE, "5CSEBA6U23I7")
        for expected in ("--component-parameter=gui_multiply_factor=26",
                         "--component-parameter=gui_divide_factor_n=2",
                         "--component-parameter=gui_divide_factor_c0=26"):
            self.assertIn(expected, system)
        for device in (None, "", "5CSEBA6U23I7 ", "../etc"):
            with self.subTest(device=device), self.assertRaises(ValueError):
                cv.generation_command(identity, cv.DEFINITION, cv.PIXEL_MODULE, device)
        with self.assertRaises(ValueError):
            cv.generation_command(identity, cv.DEFINITION, "n2m_pixel_pll", "5CSEBA6U23I7")

    def test_project_inputs_name_both_generated_instances(self):
        self.assertEqual(cv.generated_sources(cv.DEFINITION),
                         [cv.PIXEL_MODULE + ".v", cv.SYSTEM_MODULE + ".v"])
        self.assertEqual(len(cv.cache_files(cv.DEFINITION)), 6)
        for module in (cv.PIXEL_MODULE, cv.SYSTEM_MODULE):
            self.assertIn("PLL_COMPENSATION_MODE DIRECT",
                          "\n".join(line for line in cv.assignments(cv.DEFINITION) if module in line))
        self.assertEqual(cv.lock_event_count({"top": "nano_clocking_proof"}), 0)


class VcoRangeTests(unittest.TestCase):
    """The recorded datasheet range refuses a configuration outside it.

    The range bounds the oscillator, not the figure the tools print. The post-scale
    divider K sits between them, so a design is judged on `physical_vco`: a K=2
    design whose printed figure is below the floor is legal and must be accepted,
    and a K=2 design whose printed figure is inside the range is still refused when
    the oscillator is not.
    """

    def configured(self, module, config):
        return patch.dict(cv.CONFIGURATION, {module: cv.Configuration(*config)})

    def test_the_shipped_configuration_states_an_in_range_vco(self):
        low, high = cv.VCO_RANGE_MHZ
        self.assertEqual((float(low), float(high)), (600.0, 1400.0))
        for module, vco in ((cv.SYSTEM_MODULE, 650.0), (cv.PIXEL_MODULE, 630.0)):
            with self.subTest(module=module):
                self.assertEqual(float(cv.physical_vco(module)), vco)
                # K is 1, so the oscillator and the printed figure are one number.
                self.assertEqual(cv.physical_vco(module), cv.stated_vco(module))
                self.assertTrue(low <= cv.physical_vco(module) <= high)

    def test_every_entry_point_refuses_an_out_of_range_oscillator(self):
        # multiply, divide, counter, post_scale, charge_pump, bandwidth; each still
        # produces exactly 25 MHz, so only the oscillator is wrong.
        for name, config in {"half the floor, as the solver once chose": (6, 1, 12, 1, 20, 2000),
                             "above the ceiling": (30, 1, 60, 1, 20, 2000),
                             "printed figure in range, oscillator above it": (15, 1, 30, 2, 20, 2000)}.items():
            with self.configured(cv.SYSTEM_MODULE, config):
                self.assertEqual(cv.stated_vco(cv.SYSTEM_MODULE) / config[2],
                                 cv.frequencies(cv.DEFINITION)[cv.SYSTEM_MODULE])
                for entry in (lambda: cv.validate(cv.DEFINITION),
                              lambda: cv.generated_sources(cv.DEFINITION),
                              lambda: cv.cache_files(cv.DEFINITION),
                              lambda: cv.assignments(cv.DEFINITION),
                              lambda: cv.generation_command({"generator": {"path": "/ip-generate"}}, cv.DEFINITION,
                                                            cv.SYSTEM_MODULE, "5CSEBA6U23I7"),
                              lambda: cv.verify(Path("."), cv.DEFINITION)):
                    with self.subTest(configuration=name), self.assertRaises(ValueError) as error:
                        entry()
                    self.assertIn("PLL VCO frequency outside the Cyclone V range", str(error.exception))

    def test_a_post_scale_divider_below_the_printed_floor_is_accepted(self):
        """The same counters with K=2 run the oscillator at 600 MHz and are legal."""
        with self.configured(cv.SYSTEM_MODULE, (6, 1, 12, 2, 20, 2000)):
            self.assertEqual(float(cv.stated_vco(cv.SYSTEM_MODULE)), 300.0)
            self.assertEqual(float(cv.physical_vco(cv.SYSTEM_MODULE)), 600.0)
            cv.validate(cv.DEFINITION)

    def test_counters_that_miss_the_contract_frequency_are_refused(self):
        with self.configured(cv.SYSTEM_MODULE, (26, 2, 25, 1, 20, 4000)):
            with self.assertRaises(ValueError) as error:
                cv.validate(cv.DEFINITION)
        self.assertIn("does not produce the contract frequency", str(error.exception))


def generated_hdl(module, frequency=None):
    """A generated Altera PLL wrapper with exactly the parameters the check reads."""
    config = cv.CONFIGURATION[module]
    frequency = frequency or f"{float(cv.frequencies(cv.DEFINITION)[module]):.6f} MHz"
    parameters = [('fractional_vco_multiplier', '"false"'), ('reference_clock_frequency', '"50.0 MHz"'),
                  ('pll_fractional_cout', '32'), ('pll_dsm_out_sel', '"1st_order"'),
                  ('operation_mode', '"direct"'), ('number_of_clocks', '1'),
                  ('output_clock_frequency0', f'"{frequency}"'), ('phase_shift0', '"0 ps"'), ('duty_cycle0', '50')]
    for index in range(1, 18):
        parameters += [(f'output_clock_frequency{index}', '"0 MHz"'), (f'phase_shift{index}', '"0 ps"'),
                       (f'duty_cycle{index}', '50')]
    parameters += [('pll_type', '"Cyclone V"'), ('pll_subtype', '"General"')]
    for name, value in (("m_cnt", config.multiply), ("n_cnt", config.divide)):
        parameters += sorted(cv._counter_halves(name, value).items())
    parameters += sorted({**cv._counter_halves("c_cnt", config.counter, index=0), "c_cnt_prst0": "1",
                          "c_cnt_ph_mux_prst0": "0", "c_cnt_in_src0": '"ph_mux_clk"'}.items())
    for index in range(1, 18):
        parameters += [(f'c_cnt_hi_div{index}', '1'), (f'c_cnt_lo_div{index}', '1'), (f'c_cnt_prst{index}', '1'),
                       (f'c_cnt_ph_mux_prst{index}', '0'), (f'c_cnt_in_src{index}', '"ph_mux_clk"'),
                       (f'c_cnt_bypass_en{index}', '"true"'), (f'c_cnt_odd_div_duty_en{index}', '"false"')]
    parameters += [('pll_vco_div', str(config.post_scale)), ('pll_cp_current', str(config.charge_pump)),
                   ('pll_bwctrl', str(config.bandwidth)),
                   ('pll_output_clk_frequency', f'"{float(cv.stated_vco(module)):.1f} MHz"'),
                   ('pll_fractional_division', '"1"'), ('mimic_fbclk_type', '"none"'),
                   ('pll_fbclk_mux_1', '"glb"'), ('pll_fbclk_mux_2', '"m_cnt"'),
                   ('pll_m_cnt_in_src', '"ph_mux_clk"'), ('pll_slf_rst', '"false"')]
    body = ",\n".join(f"\t\t.{key}({value})" for key, value in parameters)
    return (f"`timescale 1ns/10ps\nmodule  {module}(\n\n\t// interface 'refclk'\n\tinput wire refclk,\n\n"
            "\t// interface 'reset'\n\tinput wire rst,\n\n\t// interface 'outclk0'\n\toutput wire outclk_0,\n\n"
            f"\t// interface 'locked'\n\toutput wire locked\n);\n\n\taltera_pll #(\n{body}\n\t) altera_pll_i (\n"
            "\t\t.rst\t(rst),\n\t\t.outclk\t({outclk_0}),\n\t\t.locked\t(locked),\n\t\t.fboutclk\t( ),\n"
            "\t\t.fbclk\t(1'b0),\n\t\t.refclk\t(refclk)\n\t);\nendmodule\n")


class GeneratedHdlTests(unittest.TestCase):
    def write(self, folder, pixel=None, system=None):
        (folder / (cv.PIXEL_MODULE + ".v")).write_text(pixel or generated_hdl(cv.PIXEL_MODULE))
        (folder / (cv.SYSTEM_MODULE + ".v")).write_text(system or generated_hdl(cv.SYSTEM_MODULE))

    def test_requested_parameters_are_accepted(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
            folder = Path(temporary)
            self.write(folder)
            cv.verify(folder, cv.DEFINITION)

    def test_every_parameter_and_port_mutation_is_rejected(self):
        good = generated_hdl(cv.PIXEL_MODULE)
        mutations = {
            "wrong output frequency": good.replace("25.200000 MHz", "25.000000 MHz"),
            "wrong reference": good.replace('"50.0 MHz"', '"100.0 MHz"'),
            "wrong operation mode": good.replace('"direct"', '"normal"'),
            "second output clock": good.replace('.output_clock_frequency1("0 MHz")',
                                               '.output_clock_frequency1("12.0 MHz")'),
            "phase shifted": good.replace('.phase_shift0("0 ps")', '.phase_shift0("100 ps")'),
            "duty changed": good.replace('.duty_cycle0(50)', '.duty_cycle0(40)'),
            "fractional vco": good.replace('.fractional_vco_multiplier("false")',
                                           '.fractional_vco_multiplier("true")'),
            "two clocks declared": good.replace('.number_of_clocks(1)', '.number_of_clocks(2)'),
            "untracked include": good.replace("`timescale", '`include "other.v"\n`timescale'),
            "renamed module": good.replace("module  " + cv.PIXEL_MODULE, "module  n2m_other_pll"),
            "renamed instance": good.replace(") altera_pll_i (", ") altera_pll_other ("),
            "extra port": good.replace("\toutput wire locked\n", "\toutput wire locked,\n\toutput wire phout\n"),
            "reset port renamed": good.replace("\tinput wire rst,", "\tinput wire areset,"),
            # The VCO the design states, its post-scale divider and the counters
            # that produce them are all evidence; each mutation is a different PLL.
            "wrong stated VCO": good.replace('.pll_output_clk_frequency("630.0 MHz")',
                                             '.pll_output_clk_frequency("300.0 MHz")'),
            "post-scale divider changed": good.replace(".pll_vco_div(1)", ".pll_vco_div(2)"),
            "M counter changed": good.replace(".m_cnt_hi_div(32)", ".m_cnt_hi_div(31)"),
            "C counter changed": good.replace(".c_cnt_hi_div0(13)", ".c_cnt_hi_div0(12)"),
            "odd duty dropped": good.replace('.c_cnt_odd_div_duty_en0("true")',
                                             '.c_cnt_odd_div_duty_en0("false")'),
            "loop filter changed": good.replace(".pll_bwctrl(6000)", ".pll_bwctrl(4000)"),
            "counters solved instead of stated": re.sub(r"\n\t\t\.(?:pll_output_clk_frequency|pll_vco_div)\([^)]*\),", "", good),
        }
        for name, text in mutations.items():
            with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
                folder = Path(temporary)
                self.write(folder, pixel=text)
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    cv.verify(folder, cv.DEFINITION)

    def test_generator_log_must_report_the_checked_result(self):
        good = ("2026.09.18.16:18:18 Info: MODULE: The legal reference clock frequency is 5.0 MHz..700.0 MHz\n"
                "2026.09.18.16:18:18 Info: MODULE: Able to implement PLL with user settings\n"
                '2026.09.18.16:18:18 Info: MODULE: Done "MODULE" with 1 modules, 2 files\n')
        with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
            log = Path(temporary) / "generate.log"
            log.write_text(good.replace("MODULE", cv.PIXEL_MODULE))
            cv._verify_log(log, cv.PIXEL_MODULE)
            for name, text in {
                    "generator warning": good.replace("Info: MODULE: Able", "Warning: MODULE: Able"),
                    "generator error": good + "2026.09.18.16:18:19 Error: MODULE: no valid solution\n",
                    "not implementable": good.replace("Able to implement PLL with user settings", "skipped"),
                    "extra file": good.replace("with 1 modules, 2 files", "with 1 modules, 3 files"),
            }.items():
                log.write_text(text.replace("MODULE", cv.PIXEL_MODULE))
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    cv._verify_log(log, cv.PIXEL_MODULE)


def usage_summary(overrides=()):
    """A PLL Usage Summary with both fitted PLLs, optionally mutated by (owner, key, value)."""
    blocks = []
    for owner, module in ((cv.FIT_SYSTEM, cv.SYSTEM_MODULE), (cv.FIT_PIXEL, cv.PIXEL_MODULE)):
        multiply, divide, counter = cv.CONFIGURATION[module][:3]
        rows = [("PLL Type", "Integer PLL"), ("PLL Location", "FRACTIONALPLL_X0_Y1_N0"),
                ("PLL Feedback clock type", "none"), ("PLL Bandwidth", "Auto"),
                ("Reference Clock Frequency", "50.0 MHz"), ("Reference Clock Sourced by", "Dedicated Pin"),
                ("PLL VCO Frequency", f"{float(cv.stated_vco(module)):.1f} MHz"), ("PLL Operation Mode", "Direct"),
                ("PLL Enable", "On"), ("PLL Fractional Division", "N/A"), ("M Counter", str(multiply)),
                ("N Counter", str(divide)), ("IOPLL Self RST", "Off"), ("PLL Refclk Select", ""),
                ("CLKIN(0) source", "clk_reference~input"), ("PLL Output Counter", ""),
                (cv.FIT_WRAPPERS[module] + "|" + cv.FIT_PLL + "|" + cv.COUNTER_ATOM, ""),
                ("Output Clock Frequency", f"{50.0 * multiply / divide / counter:.1f} MHz"),
                ("C Counter Odd Divider Even Duty Enable", "On" if counter % 2 else "Off"),
                ("Duty Cycle", "50.0000"), ("Phase Shift", "0.000000 degrees"), ("C Counter", str(counter)),
                ("C Counter PH Mux PRST", "0"), ("C Counter PRST", "1")]
        for target, key, value in overrides:
            if target == owner:
                rows = [(k, value if k == key else v) for k, v in rows]
        blocks.append(f"; {owner} ;   ;")
        blocks += [f";     -- {key} ; {value} ;" for key, value in rows]
    return ("; PLL Usage Summary ;\n+---+---+\n" + "\n".join(blocks)
            + "\n+---+---+\n\nFitter Resource Utilization by Entity\n")


def sta_clocks(rows):
    header = "; Clock Name ; Type ; Period ; Frequency ; Rise ; Fall ; Duty Cycle ; Divide by ; Multiply by ; Phase ; Offset ; Edge List ; Edge Shift ; Inverted ; Master ; Source ; Targets ;"
    lines = [header]
    for name, kind, period, ratio, master in rows:
        duty, divide, multiply = ratio or ("", "", "")
        lines.append(f"; {name} ; {kind} ; {period} ; ; ; ; {duty} ; {divide} ; {multiply} ; ; ; ; ; false ; {master} ; ; ;")
    return "\n".join(lines) + "\n"


def clock_rows():
    rows = [("clk_reference", "Base", "20.000", None, "")]
    for module, vco, output in ((cv.SYSTEM_MODULE, cv.SYSTEM_VCO, cv.SYSTEM_CLOCK),
                                (cv.PIXEL_MODULE, cv.PIXEL_VCO, cv.PIXEL_CLOCK)):
        multiply, divide, counter = cv.CONFIGURATION[module][:3]
        rows.append((vco, "Generated", f"{20.0 * divide / multiply:.3f}",
                     ("50.00", str(divide), str(multiply)), "clk_reference"))
        rows.append((output, "Generated", f"{20.0 * divide * counter / multiply:.3f}",
                     ("50.00", str(counter), "1"), vco))
    return rows


class FitEvidenceTests(unittest.TestCase):
    def build(self, folder, summary=None, clocks=None, total="2"):
        output = folder / "output"
        output.mkdir(parents=True, exist_ok=True)
        (output / "design.fit.rpt").write_text(summary if summary is not None else usage_summary(),
                                              encoding=cv.FIT_ENCODING)
        (output / "design.sta.rpt").write_text(sta_clocks(clocks if clocks is not None else clock_rows()))
        (output / "design.fit.summary").write_text(f"Fitter Status : Successful\nTotal PLLs : {total} / 6 ( 33 % )\n")
        for name in fpga_clocking.required_reports():
            path = output / name
            if name.startswith("chain_"):
                chain, check = name.removeprefix("chain_").removesuffix(".rpt").rsplit("_", 1)
                path.write_text(f"Report Timing: Found 1 {check} paths (0 violated).  Worst case slack is 0.500\n"
                                f"u_reset|{chain}[0] -> u_reset|{chain}[1]\n")
            else:
                path.write_text("synthetic report\n")

    def target(self):
        return {"pll": cv.DEFINITION, "timing": {"reference_ns": "20.000"}, "top": "nano_clocking_proof"}

    def test_fitted_counters_clocks_and_reports_are_accepted(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
            folder = Path(temporary)
            self.build(folder)
            cv.verify_fit(folder, self.target())

    def test_fit_report_mutations_are_rejected(self):
        mutations = {
            "wrong system M counter": usage_summary([(cv.FIT_SYSTEM, "M Counter", "13")]),
            "wrong pixel N counter": usage_summary([(cv.FIT_PIXEL, "N Counter", "6")]),
            "wrong C counter": usage_summary([(cv.FIT_PIXEL, "C Counter", "24")]),
            "wrong VCO": usage_summary([(cv.FIT_SYSTEM, "PLL VCO Frequency", "300.0 MHz")]),
            "wrong output frequency": usage_summary([(cv.FIT_PIXEL, "Output Clock Frequency", "25.0 MHz")]),
            "compensated operation": usage_summary([(cv.FIT_SYSTEM, "PLL Operation Mode", "Normal")]),
            "fractional division": usage_summary([(cv.FIT_PIXEL, "PLL Fractional Division", "On")]),
            "phase shifted": usage_summary([(cv.FIT_PIXEL, "Phase Shift", "90.000000 degrees")]),
            "duty changed": usage_summary([(cv.FIT_SYSTEM, "Duty Cycle", "40.0000")]),
            "reference not a pin": usage_summary([(cv.FIT_SYSTEM, "Reference Clock Sourced by", "Global Clock")]),
            "reference not the board clock": usage_summary([(cv.FIT_PIXEL, "CLKIN(0) source", "other~input")]),
            "auto reset on": usage_summary([(cv.FIT_SYSTEM, "IOPLL Self RST", "On")]),
            "one PLL only": usage_summary().replace(f"; {cv.FIT_PIXEL} ;   ;", "; other ;   ;"),
        }
        for name, summary in mutations.items():
            with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
                folder = Path(temporary)
                self.build(folder, summary=summary)
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    cv.verify_fit(folder, self.target())

    def test_clock_inventory_mutations_are_rejected(self):
        base = clock_rows()
        mutations = {
            "missing VCO clock": [row for row in base if row[0] != cv.SYSTEM_VCO],
            "extra clock": base + [("stray", "Generated", "10.000", ("50.00", "2", "1"), "clk_reference")],
            "wrong pixel period": [(n, k, "40.000" if n == cv.PIXEL_CLOCK else p, r, m) for n, k, p, r, m in base],
            "wrong ratio": [(n, k, p, ("50.00", "24", "1") if n == cv.PIXEL_CLOCK else r, m) for n, k, p, r, m in base],
            "wrong master": [(n, k, p, r, "clk_reference" if n == cv.PIXEL_CLOCK else m) for n, k, p, r, m in base],
            "base instead of generated": [(n, "Base" if n == cv.SYSTEM_CLOCK else k, p, r, m) for n, k, p, r, m in base],
        }
        for name, clocks in mutations.items():
            with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
                folder = Path(temporary)
                self.build(folder, clocks=clocks)
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    cv.verify_fit(folder, self.target())

    def test_resource_count_and_reports_are_required(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
            folder = Path(temporary)
            self.build(folder, total="1")
            with self.assertRaises(ValueError):
                cv.verify_fit(folder, self.target())
        for missing in ("metastability.rpt", "clock_transfers.rpt", "chain_pix_release_hold.rpt"):
            with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
                folder = Path(temporary)
                self.build(folder)
                (folder / "output" / missing).unlink()
                with self.subTest(missing=missing), self.assertRaises(ValueError):
                    cv.verify_fit(folder, self.target())
        for name, text in {"violated": "Report Timing: Found 1 hold paths (1 violated).  Worst case slack is 0.500\n",
                           "negative": "Report Timing: Found 1 hold paths (0 violated).  Worst case slack is -0.100\n"
                                       "u_reset|sys_release[0] -> u_reset|sys_release[1]\n",
                           "other endpoints": "Report Timing: Found 1 hold paths (0 violated).  Worst case slack is 0.500\n"
                                              "u_reset|other[0] -> u_reset|other[1]\n"}.items():
            with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
                folder = Path(temporary)
                self.build(folder)
                (folder / "output/chain_sys_release_hold.rpt").write_text(text)
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    cv.verify_fit(folder, self.target())


def netlist(**changes):
    """A synthetic Cyclone V clocking netlist with the topology the check accepts."""
    reset, system, pixel = fpga_lock_cyclonev.RESET, fpga_lock_cyclonev.SYSTEM, fpga_lock_cyclonev.PLL
    reference_out = fpga_lock_cyclonev.REFERENCE_OUT
    reference_net = changes.get("bootstrap_clock", fpga_lock_cyclonev.REFERENCE_NET)
    statements = ["wire gnd", "wire vcc", "assign gnd = 1'b0", "assign vcc = 1'b1", "tri1 devclrn", "tri1 devpor"]
    params = []

    def cell(kind, name, **ports):
        statements.append(kind + " \\" + name + " (" + ",".join(f".{port}({value})" for port, value in ports.items()) + ")")

    def param(name, key, value):
        params.append("defparam \\" + name + f" .{key} = {value}")

    def modes(name, values):
        for key, value in values.items():
            param(name, key, value)

    cell("cyclonev_io_ibuf", "clk_reference~input", i="clk_reference", o=reference_out)
    cell("cyclonev_clkena", "clk_reference~inputCLKENA0", inclk=reference_out, ena="vcc",
         outclk=fpga_lock_cyclonev.REFERENCE_NET, enaout="")
    modes("clk_reference~inputCLKENA0", fpga_lock_cyclonev.BUFFER_MODES)
    release = "\\" + reset + "pll_areset~q"
    cell("dffeas", reset + "pll_areset", clk=reference_net, d="gnd", asdata="\\" + reset + "pll_areset~0_combout",
         clrn=changes.get("reset_clear", "\\" + reset + "board_release[1]"), aload="gnd", sclr="gnd", sload="vcc",
         ena="vcc", devclrn="devclrn", devpor="devpor", q=release, prn="vcc")
    modes(reset + "pll_areset", fpga_lock_cyclonev.REGISTER_MODES)
    cell("cyclonev_lcell_comb", reset + "pll_areset~0", dataa="gnd", datab="gnd", datac="gnd", datad="gnd",
         datae="gnd", dataf="gnd", datag="gnd", cin="gnd", sharein="gnd",
         combout="\\" + reset + "pll_areset~0_combout", sumout="", cout="", shareout="")
    modes(reset + "pll_areset~0", {"extended_lut": '"off"', "lut_mask": "64'hFFFFFFFFFFFFFFFF",
                                   "shared_arith": '"off"'})
    locks = []
    for prefix in (system, pixel):
        select = "\\" + prefix + fpga_lock_cyclonev.REFCLK_OUT
        lock = "\\" + prefix + "locked_wire[0]"
        cell("cyclonev_pll_refclk_select", prefix + fpga_lock_cyclonev.REFCLK_SELECT,
             clkin=changes.get("refclk_input", "{gnd,gnd,gnd," + reference_out + "}"), clkout=select,
             extswitchbuf="\\" + prefix + "fpll_0|refclk_select_extswitchbuf_wire",
             clk0bad="", clk1bad="", pllclksel="")
        cell("cyclonev_fractional_pll", prefix + fpga_lock_cyclonev.FRACTIONAL,
             nresync=changes.get("pll_reset", release), refclkin=select, lock=lock,
             fbclk="\\" + prefix + "fboutclk_wire[0]", coreclkfb="\\" + prefix + "fboutclk_wire[0]",
             cntnen="", mcntout="", fblvdsout="", plniotribuf="", shiftdoneout="", tclk="", mhi="", vcoph="")
        cell("cyclonev_pll_output_counter", prefix + fpga_lock_cyclonev.COUNTER,
             cascadein="gnd", divclk="\\" + prefix + fpga_lock_cyclonev.OUTPUT_WIRE, cascadeout="", shiftdone0o="")
        cell("cyclonev_clkena", prefix + fpga_lock_cyclonev.OUTPUT_WIRE + "~CLKENA0", inclk="\\" + prefix + fpga_lock_cyclonev.OUTPUT_WIRE,
             ena="vcc", outclk="\\" + prefix + fpga_lock_cyclonev.OUTPUT_WIRE + "~CLKENA0_outclk", enaout="")
        modes(prefix + fpga_lock_cyclonev.OUTPUT_WIRE + "~CLKENA0", fpga_lock_cyclonev.BUFFER_MODES)
        locks.append(lock)
    gate = "\\" + reset + "lock_reset~combout"
    inputs = changes.get("gate_inputs", {"dataa": "!" + locks[0], "datab": "gnd", "datac": "!" + locks[1],
                                         "datad": "gnd", "datae": "gnd", "dataf": "!" + release})
    cell("cyclonev_lcell_comb", reset + "lock_reset", **inputs, datag="gnd", cin="gnd", sharein="gnd",
         combout=gate, sumout="", cout="", shareout="")
    modes(reset + "lock_reset", {"extended_lut": '"off"',
                                 "lut_mask": changes.get("gate_mask", "64'hFFFFFFFFFAFAFAFA"),
                                 "shared_arith": '"off"'})
    feeder = "\\" + reset + "lock_samples[0]~feeder_combout"
    cell("cyclonev_lcell_comb", reset + "lock_samples[0]~feeder", dataa="gnd", datab="gnd", datac="gnd",
         datad="gnd", datae="gnd", dataf="gnd", datag="gnd", cin="gnd", sharein="gnd", combout=feeder,
         sumout="", cout="", shareout="")
    modes(reset + "lock_samples[0]~feeder", {"extended_lut": '"off"',
                                             "lut_mask": changes.get("feeder_mask", "64'hFFFFFFFFFFFFFFFF"),
                                             "shared_arith": '"off"'})
    sampling = changes.get("sampling_clock", "\\" + system + fpga_lock_cyclonev.OUTPUT_WIRE + "~CLKENA0_outclk")
    cell("dffeas", reset + "lock_samples[0]", clk=sampling, d=feeder, asdata="vcc",
         clrn=changes.get("sample_clear", "!" + gate), aload="gnd", sclr="gnd", sload="gnd", ena="vcc",
         devclrn="devclrn", devpor="devpor", q="\\" + reset + "lock_samples[0]", prn="vcc")
    modes(reset + "lock_samples[0]", fpga_lock_cyclonev.REGISTER_MODES)
    cell("dffeas", reset + "lock_samples[1]", clk=sampling, d="gnd", asdata="\\" + reset + "lock_samples[0]",
         clrn="!" + gate, aload="gnd", sclr="gnd", sload="vcc", ena="vcc", devclrn="devclrn", devpor="devpor",
         q="\\" + reset + "lock_samples[1]", prn="vcc")
    modes(reset + "lock_samples[1]", fpga_lock_cyclonev.REGISTER_MODES)
    if "extra" in changes:
        statements.append(changes["extra"])
    return ";\n".join(statements + params) + ";\n"


NO_LOCK_ROWS = "; check_timing ; 0 ;\n"


class LockEvidenceTests(unittest.TestCase):
    def test_the_qualification_topology_is_accepted(self):
        evidence = fpga_lock_cyclonev.verify(netlist(), NO_LOCK_ROWS)
        self.assertEqual(evidence["truth_cases"], 8)
        self.assertEqual(evidence["endpoints"], [])
        self.assertEqual(evidence["bootstrap_clock"], fpga_lock_cyclonev.REFERENCE_NET)

    def test_any_no_clock_row_is_refused(self):
        checks = "; some|register ; No clock feeds this register's clock port. ;\n"
        with self.assertRaises(ValueError):
            fpga_lock_cyclonev.verify(netlist(), checks)

    def test_unsupported_top_is_refused(self):
        for top in ("clocking_proof", "nano_smoke", "other"):
            with self.subTest(top=top), self.assertRaises(ValueError):
                fpga_lock_cyclonev.verify(netlist(), NO_LOCK_ROWS, top)

    def test_bootstrap_reset_and_reference_mutations_are_rejected(self):
        system = fpga_lock_cyclonev.SYSTEM
        mutations = {
            "bootstrap on a generated clock": {
                "bootstrap_clock": "\\" + system + fpga_lock_cyclonev.OUTPUT_WIRE + "~CLKENA0_outclk"},
            "reset cleared by something else": {"reset_clear": "vcc"},
            "PLL reset not the bootstrap register": {"pll_reset": "gnd"},
            "PLL reset inverted": {"pll_reset": "!\\" + fpga_lock_cyclonev.RESET + "pll_areset~q"},
            "PLL reference not the board pin": {"refclk_input": "{gnd,gnd,gnd,gnd}"},
            "sampling on the reference": {"sampling_clock": fpga_lock_cyclonev.REFERENCE_NET},
            "sample cleared by something else": {"sample_clear": "vcc"},
        }
        for name, change in mutations.items():
            with self.subTest(mutation=name), self.assertRaises(ValueError):
                fpga_lock_cyclonev.verify(netlist(**change), NO_LOCK_ROWS)

    def test_lock_gate_truth_table_mutations_are_rejected(self):
        release = "\\" + fpga_lock_cyclonev.RESET + "pll_areset~q"
        locks = ["\\" + prefix + "locked_wire[0]" for prefix in (fpga_lock_cyclonev.SYSTEM, fpga_lock_cyclonev.PLL)]
        mutations = {
            # Reset alone, so neither raw lock loss reaches the sampling reset.
            "reset only": {"gate_inputs": {"dataa": "gnd", "datab": "gnd", "datac": "gnd", "datad": "gnd",
                                           "datae": "gnd", "dataf": "!" + release},
                           "gate_mask": "64'hFFFFFFFF00000000"},
            # The pixel lock dropped: only the system lock and reset propagate.
            "one lock dropped": {"gate_inputs": {"dataa": "!" + locks[0], "datab": "gnd", "datac": "gnd",
                                                 "datad": "gnd", "datae": "gnd", "dataf": "!" + release},
                                 "gate_mask": "64'hFFFFFFFFAAAAAAAA"},
            "inverted table": {"gate_mask": "64'h0000000005050505"},
            "unrelated input": {"gate_inputs": {"dataa": "!" + locks[0], "datab": "\\stranger", "datac": "!" + locks[1],
                                                "datad": "gnd", "datae": "gnd", "dataf": "!" + release}},
        }
        for name, change in mutations.items():
            with self.subTest(mutation=name), self.assertRaises(ValueError):
                fpga_lock_cyclonev.verify(netlist(**change), NO_LOCK_ROWS)

    def test_constant_sample_data_and_extra_fanout_are_rejected(self):
        reset = fpga_lock_cyclonev.RESET
        mutations = {
            "sample data not constant one": {"feeder_mask": "64'h0000000000000000"},
            "lock reset reaches a datapath": {
                "extra": "dffeas \\stranger (.clk(gnd), .clrn(!\\" + reset + "lock_reset~combout ), .q(\\stranger_q))"},
            "raw lock reaches a datapath": {
                "extra": "dffeas \\stranger (.clk(\\" + fpga_lock_cyclonev.SYSTEM
                         + "locked_wire[0] ), .q(\\stranger_q))"},
            "unsupported primitive": {"extra": "fiftyfivenm_pll \\stranger (.locked(\\stranger_q))"},
            "second driver on the gate": {
                "extra": "cyclonev_lcell_comb \\stranger (.dataa(gnd), .combout(\\" + reset + "lock_reset~combout ))"},
        }
        for name, change in mutations.items():
            with self.subTest(mutation=name), self.assertRaises(ValueError):
                fpga_lock_cyclonev.verify(netlist(**change), NO_LOCK_ROWS)


class DiagnosticTests(unittest.TestCase):
    def connectivity(self, folder, owners=None, ports=None):
        output = folder / "output"
        output.mkdir(parents=True, exist_ok=True)
        ports = cv.CONNECTIVITY_PORTS if ports is None else ports
        blocks = []
        for owner in owners if owners is not None else sorted(cv.FIT_WRAPPERS.values()):
            blocks.append(f'; Port Connectivity Checks: "{owner}" ;')
            blocks.append("; Port ; Type ; Severity ; Details ;")
            blocks += [f"; {name} ; {kind} ; {severity} ; {detail} ;"
                       for (name, kind, severity), detail in ports.items()]
            blocks.append("+---+---+---+---+")
        (output / "design.map.rpt").write_text("\n".join(blocks) + "\n", encoding="cp1252")

    def text(self, *lines):
        return "\n".join(lines) + "\n"

    def predicted(self):
        """Every diagnostic line the two fitted PLL instances produce, in log order."""
        quartus = "/opt/quartus/libraries/megafunctions"
        lines = [cv.SYNTHESIS_WARNING, cv.CONNECTIVITY_WARNING]
        for port, source, line in cv.UNDRIVEN_PORTS:
            lines += [f'Warning (10034): Output port "{port}" at {source}({line}) has no driver'
                      f" File: {quartus}/{source} Line: {line}"] * 2
        lines += ['Warning (12030): Port "extclk" on the entity instantiation of "cyclonev_pll" is connected to a '
                  "signal of width 1. The formal width of the signal in the module is 2.  The extra bits will be "
                  f"left dangling without any fan-out logic. File: {quartus}/altera_pll.v Line: 2224"] * 2
        lines += [cv.REMOVED_HEADERS["14284"], cv.REMOVED_HEADERS["14285"]]
        lines += [f'Warning (14320): Synthesized away node "{wrapper}|{node}"'
                  f" File: {quartus}/altera_pll.v Line: 425"
                  for wrapper in cv.FIT_WRAPPERS.values() for node in cv.REMOVED_NODES]
        return lines

    def test_every_clocking_diagnostic_is_explained(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
            folder = Path(temporary)
            self.connectivity(folder)
            lines = self.predicted()
            explained = cv.explained_diagnostics(self.text(*lines), folder, cv.DEFINITION)
            self.assertEqual(len(explained), len(lines))
            self.assertEqual({entry["code"] for entry in explained}, set(cv.EXPLAINED_CODES))
            self.assertTrue(all(entry["reason"] for entry in explained))
            self.assertEqual(sorted(entry["text"] for entry in explained), sorted(lines))

    def test_no_diagnostic_explains_nothing(self):
        with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
            self.assertEqual(cv.explained_diagnostics("", Path(temporary), cv.DEFINITION), [])

    def test_diagnostic_identity_count_and_report_mutations_are_rejected(self):
        lines = self.predicted()
        with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
            folder = Path(temporary)
            self.connectivity(folder)
            mutations = {
                "connectivity warning missing": [line for line in lines if line != cv.CONNECTIVITY_WARNING],
                "synthesis warning repeated": lines + [cv.SYNTHESIS_WARNING],
                "hierarchy count differs": [line.replace("2 hierarchies", "3 hierarchies") for line in lines],
                "one undriven port only once": [line for line in lines
                                                if "extclk_out" not in line] + [next(line for line in lines
                                                                                     if "extclk_out" in line)],
                "another undriven port": lines + [lines[2].replace("lvds_clk", "outclk_1")],
                "another removed node": lines + [lines[-1].replace("gnd", "stranger")],
                "a vendor line from another file": [line.replace("altera_pll.v(320)", "altera_other.v(320)")
                                                   for line in lines],
                "a vendor line from another line number": [line.replace("altera_pll.v(320)", "altera_pll.v(999)")
                                                           for line in lines],
            }
            for name, text in mutations.items():
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    cv.explained_diagnostics(self.text(*text), folder, cv.DEFINITION)
        good = self.text(*lines)
        for name, kwargs in {
                "third hierarchy": {"owners": [*sorted(cv.FIT_WRAPPERS.values()), "other:u_other"]},
                "unexpected port": {"ports": {**cv.CONNECTIVITY_PORTS, ("outclk_1", "Output", "Warning"): "unused"}},
                "severity raised": {"ports": {(name, kind, "Critical Warning" if name == "refclk1" else severity): detail
                                              for (name, kind, severity), detail in cv.CONNECTIVITY_PORTS.items()}},
        }.items():
            with tempfile.TemporaryDirectory(dir=scratch()) as temporary:
                folder = Path(temporary)
                self.connectivity(folder, **kwargs)
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    cv.explained_diagnostics(good, folder, cv.DEFINITION)


class Max10ParityTests(unittest.TestCase):
    """The MAX 10 implementation keeps its definitions, endpoints and audit text."""

    def test_max10_surface_is_unchanged(self):
        self.assertEqual(fpga_pll.TOOLS_KEY, "altpll")
        self.assertEqual(fpga_pll.generated_sources(LITE_DEFINITION), ["n2m_pixel_pll.v", "n2m_system_pll.v"])
        self.assertEqual(fpga_pll.generated_sources({k: v for k, v in LITE_DEFINITION.items()
                                                     if k != "system_divide"}), ["n2m_pixel_pll.v"])
        self.assertEqual(fpga_pll.assignments(LITE_DEFINITION), [])
        self.assertEqual(fpga_pll.cache_files(LITE_DEFINITION),
                         ["n2m_pixel_pll.v", "generate-pll.log", "n2m_system_pll.v", "generate-system-pll.log"])
        self.assertEqual(fpga_pll.timed_clocks({"pll": LITE_DEFINITION}),
                         ("clk_reference", fpga_pll.SYSTEM_CLOCK, fpga_pll.PIXEL_CLOCK))
        self.assertEqual(fpga_pll.corner_slacks({"pll": LITE_DEFINITION}, "Slow 1200mV 85C"), [])
        self.assertEqual(fpga_pll.lock_event_count({"top": "clocking_proof", "pll": LITE_DEFINITION}), 2)
        self.assertEqual(fpga_pll.lock_event_count({"top": "controls_proof", "pll": LITE_DEFINITION}), 3)

    def test_reset_chain_audit_and_reports_are_shared_and_unchanged(self):
        self.assertIs(fpga_pll.chain_audit, fpga_clocking.chain_audit)
        self.assertEqual(fpga_pll.required_reports(), fpga_clocking.required_reports())
        audit = fpga_clocking.chain_audit(fpga.tcl_word)
        self.assertEqual(len(re.findall(r"^report_timing ", audit, re.M)), 8)
        for chain in fpga_clocking.CHAINS:
            self.assertIn(f'"missing reset stage: {chain}\\[0\\]"', audit)

    def test_cyclonev_endpoints_are_not_altpll_endpoints(self):
        self.assertNotIn("altpll", cv.SYSTEM_CLOCK + cv.PIXEL_CLOCK + cv.SYSTEM_NET)
        self.assertNotEqual(cv.SYSTEM_CLOCK, fpga_pll.SYSTEM_CLOCK)
        self.assertNotEqual(cv.PIXEL_CLOCK, fpga_pll.PIXEL_CLOCK)


if __name__ == "__main__":
    unittest.main()
