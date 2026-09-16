"""Synthetic hold-path reports: parsing, the record shape, the text summary and the audit script."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import fpga, fpga_hold, fpga_pll, fpga_vga

SYSTEM = fpga_pll.SYSTEM_CLOCK
SDRAM = fpga_pll.SDRAM_CLOCK
# Slacks per corner, worst first; the fast corner is the tightest, as on the board fits.
SYSTEM_SLACKS = {"slow85": (0.256, 0.301, 0.333, 0.410, 0.412), "slow0": (0.222, 0.240, 0.290, 0.300, 0.350),
                 "fast0": (0.019, 0.052, 0.127, 0.130, 0.200)}
SDRAM_SLACKS = {"slow85": (20.002, 20.010, 20.100), "slow0": (19.753, 19.800, 19.900), "fast0": (18.939, 19.000, 19.100)}


def row(*cells):
    return "; " + " ; ".join(str(c) for c in cells) + " ;\n"


def report(corner, label, slacks, *, violated=None):
    """The shape quartus_sta writes for report_timing -hold -detail full_path -file."""
    clock = fpga_hold.CLOCKS[label]
    launch = SYSTEM
    if label == "system":
        endpoints = [(f"n2m_v05_system:u_system|n2m_uart:u_uart|stage[{i}]", f"n2m_v05_system:u_system|n2m_uart:u_uart|stage[{i + 1}]") for i in range(len(slacks))]
    else:
        endpoints = [(f"n2m_v05_system:u_system|n2m_sdram_ctrl:u_sdram|addr[{i}]", f"DRAM_ADDR[{i}]") for i in range(len(slacks))]
    violated = sum(s < 0 for s in slacks) if violated is None else violated
    header = (f"Report Timing: Found {len(slacks)} hold paths ({violated} violated).  Worst case slack is {slacks[0]:.3f} \n\n"
              f"Tcl Command:\n    report_timing -hold -file output/{fpga_hold.report_name(corner, label)} -to_clock [get_clocks {{{clock}}}] -npaths 5 -detail full_path\n\n"
              f"Delay Model:\n    {fpga_hold.MODELS[corner]}\n\n")
    table = "; Summary of Paths\n" + row("Slack", "From Node", "To Node", "Launch Clock", "Latch Clock", "Relationship", "Clock Skew", "Data Delay")
    for slack, (source, sink) in zip(slacks, endpoints):
        table += row(f"{slack:.3f}", source, sink, launch, clock, "0.000", "-0.025", f"{slack + 0.3:.3f}")
    return header + table + "\nPath #1: Hold slack is %.3f \n" % slacks[0]


def fixture(folder, *, system=SYSTEM_SLACKS, sdram=SDRAM_SLACKS):
    output = folder / "output"
    output.mkdir(exist_ok=True)
    for corner, _, _ in fpga_vga.CORNERS:
        (output / fpga_hold.report_name(corner, "system")).write_text(report(corner, "system", system[corner]), encoding="utf-8")
        (output / fpga_hold.report_name(corner, "sdram")).write_text(report(corner, "sdram", sdram[corner]), encoding="utf-8")


class HoldPathTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[3] / "workdir" / "fpga-unit-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="hold paths ", dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_audit_reports_both_clocks_at_every_corner(self):
        script = fpga_hold.audit(fpga.tcl_word)
        self.assertEqual(script.count("update_timing_netlist"), 3)
        self.assertEqual(script.count("report_timing -to_clock $hold_system -hold -npaths 5 -detail full_path"), 3)
        self.assertEqual(script.count("report_timing -to_clock $hold_sdram -hold -npaths 5 -detail full_path"), 3)
        self.assertIn('set hold_sdram [get_clocks "sdram_clk"]', script)
        self.assertIn('set hold_system [get_clocks "u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk\\[0\\]"]', script)
        for name in fpga_hold.required_reports():
            self.assertIn(f"-file output/{name}", script)
        self.assertEqual(len(fpga_hold.required_reports()), 6)

    def test_parse_reads_endpoints_slack_and_order(self):
        parsed = fpga_hold.parse(report("fast0", "system", SYSTEM_SLACKS["fast0"]), corner="fast0", clock=SYSTEM)
        self.assertEqual((parsed["found"], parsed["violated"], parsed["worst_slack_ns"]), (5, 0, 0.019))
        first = parsed["paths"][0]
        self.assertEqual(first, {"slack_ns": 0.019, "from": "u_system|u_uart|stage[0]", "to": "u_system|u_uart|stage[1]",
                                 "launch_clock": SYSTEM, "latch_clock": SYSTEM, "relationship_ns": 0.0,
                                 "clock_skew_ns": -0.025, "data_delay_ns": 0.319})
        self.assertEqual([p["slack_ns"] for p in parsed["paths"]], list(SYSTEM_SLACKS["fast0"]))
        sdram = fpga_hold.parse(report("slow85", "sdram", SDRAM_SLACKS["slow85"]), corner="slow85", clock=SDRAM)
        self.assertEqual((sdram["found"], sdram["paths"][0]["to"], sdram["paths"][0]["latch_clock"]), (3, "DRAM_ADDR[0]", SDRAM))
        text = f"Delay Model:\n    {fpga_hold.MODELS['fast0']}\n{fpga_hold.EMPTY}\n"
        self.assertEqual(fpga_hold.parse(text, corner="fast0", clock=SDRAM), {"found": 0, "violated": 0, "worst_slack_ns": None, "paths": []})

    def test_negative_slack_is_recorded_not_judged(self):
        parsed = fpga_hold.parse(report("fast0", "system", (-0.010, 0.052)), corner="fast0", clock=SYSTEM)
        self.assertEqual((parsed["violated"], parsed["worst_slack_ns"]), (1, -0.010))

    def test_malformed_reports_fail(self):
        good = report("fast0", "system", SYSTEM_SLACKS["fast0"])
        cases = {
            "corner": (fpga_hold.MODELS["fast0"], fpga_hold.MODELS["slow0"]),
            "header": ("Report Timing: Found 5 hold paths", "Report Timing: Found 4 hold paths"),
            "worst": ("Worst case slack is 0.019", "Worst case slack is 0.020"),
            "latch": (f"; {SYSTEM} ; 0.000 ; -0.025 ; 0.319", f"; {SDRAM} ; 0.000 ; -0.025 ; 0.319"),
            "order": ("; 0.052 ; ", "; 0.010 ; "),
            "violated": ("(0 violated)", "(1 violated)"),
            "nonfinite": ("; 0.127 ; ", "; nan ; "),
            "table": ("; Summary of Paths", "; Summary"),
        }
        for name, (before, after) in cases.items():
            with self.subTest(name=name):
                self.assertIn(before, good)
                with self.assertRaises(ValueError):
                    fpga_hold.parse(good.replace(before, after, 1), corner="fast0", clock=SYSTEM)

    def test_verify_records_every_corner_and_the_worst_path_per_clock(self):
        fixture(self.folder)
        evidence = fpga_hold.verify(self.folder)
        self.assertEqual(evidence["npaths"], 5)
        self.assertEqual(set(evidence["clocks"]), {"system", "sdram"})
        system = evidence["clocks"]["system"]
        self.assertEqual(system["clock"], SYSTEM)
        self.assertEqual(set(system["corners"]), {"slow85", "slow0", "fast0"})
        self.assertEqual(system["corners"]["slow0"]["report"], "hold_slow0_system.rpt")
        self.assertEqual(system["corners"]["slow0"]["worst_slack_ns"], 0.222)
        self.assertEqual(len(system["corners"]["slow0"]["paths"]), 5)
        self.assertEqual(system["worst"]["corner"], "fast0")
        self.assertEqual(system["worst"]["slack_ns"], 0.019)
        self.assertEqual(system["worst"]["report"], "hold_fast0_system.rpt")
        self.assertEqual((system["worst"]["from"], system["worst"]["to"]), ("u_system|u_uart|stage[0]", "u_system|u_uart|stage[1]"))
        sdram = evidence["clocks"]["sdram"]
        self.assertEqual((sdram["clock"], sdram["worst"]["corner"], sdram["worst"]["slack_ns"], sdram["worst"]["to"]),
                         (SDRAM, "fast0", 18.939, "DRAM_ADDR[0]"))
        lines = fpga_hold.summary_lines(evidence)
        self.assertEqual(lines, [
            f"Worst hold (system {SYSTEM}): 0.019 ns at fast0, u_system|u_uart|stage[0] -> u_system|u_uart|stage[1] (hold_fast0_system.rpt)",
            f"Worst hold (sdram {SDRAM}): 18.939 ns at fast0, u_system|u_sdram|addr[0] -> DRAM_ADDR[0] (hold_fast0_sdram.rpt)"])
        self.assertEqual(fpga_hold.summary_lines(None), [])
        (self.folder / "output/hold_slow85_sdram.rpt").unlink()
        with self.assertRaisesRegex(ValueError, "missing hold path report: hold_slow85_sdram.rpt"):
            fpga_hold.verify(self.folder)

    def test_a_clock_without_paths_has_no_worst_entry(self):
        fixture(self.folder)
        for corner, _, _ in fpga_vga.CORNERS:
            (self.folder / "output" / fpga_hold.report_name(corner, "sdram")).write_text(
                f"Delay Model:\n    {fpga_hold.MODELS[corner]}\n{fpga_hold.EMPTY}\n", encoding="utf-8")
        evidence = fpga_hold.verify(self.folder)
        self.assertIsNone(evidence["clocks"]["sdram"]["worst"])
        self.assertEqual(evidence["clocks"]["sdram"]["corners"]["fast0"]["found"], 0)
        self.assertEqual(fpga_hold.summary_lines(evidence)[1], f"Worst hold (sdram {SDRAM}): no paths reported")


if __name__ == "__main__":
    unittest.main()
