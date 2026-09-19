"""The DE10-Nano UART endpoint image: generated project, corner reports, netlist, stores.

The fixtures are abstract, not copied vendor output: each states the shape the
checks accept, then mutates it one way at a time so every rejection is proved.
"""
import tempfile
import unittest
from pathlib import Path

from tools.n2m import fpga, fpga_controls, fpga_uart_cyclonev as uart, fpga_vga

ROOT = Path(__file__).resolve().parents[3]
TARGET = "nano-uart"
IDENTITY = "123456789abcdef00123456789abcdef"
CHAIN = uart.CHAINS[0]
CLOCK = uart.SYSTEM_CLOCK


def scratch():
    directory = ROOT / "workdir/fpga-nano-uart-tests"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def report(check, *, slack="38.904", first=CHAIN[2], second=CHAIN[3], launch=CLOCK, violated=0):
    """One retained corner report with the summary row the check reads."""
    row = f"; {slack} ; {first} ; {second} ; {launch} ; {CLOCK} ; 40.000 ; -0.088 ; 0.928 ;"
    return (f"Report Timing: Found 1 {check} paths ({violated} violated).  Worst case slack is {slack}\n"
            "; Summary of Paths ;\n"
            "; Slack ; From Node ; To Node ; Launch Clock ; Latch Clock ; Relationship ; Clock Skew ; Data Delay ;\n"
            + row + "\nPath #1: Setup slack is " + slack + "\n")


def write_reports(folder, **changes):
    output = folder / "output"
    output.mkdir(parents=True, exist_ok=True)
    for name in uart.required_reports():
        check = "setup" if name.endswith("setup.rpt") else "hold"
        (output / name).write_text(report(check, **changes))
    return folder


def netlist(**changes):
    """A synthetic Cyclone V netlist with the receive synchronizer the check accepts."""
    statements = ["wire gnd", "wire vcc", "assign gnd = 1'b0", "assign vcc = 1'b1",
                  "tri1 devclrn", "tri1 devpor"]
    params = []

    def cell(kind, name, **ports):
        statements.append(kind + " \\" + name + " ("
                          + ",".join(f".{port}({value})" for port, value in ports.items()) + ")")

    def modes(name, values):
        for key, value in values.items():
            params.append("defparam \\" + name + f" .{key} = {value}")

    external = CHAIN[1]
    buffered = "\\" + external + "~input_o"
    cell("cyclonev_io_ibuf", external + "~input", i=external, ibar="gnd",
         dynamicterminationcontrol="gnd", o=buffered)
    lut = CHAIN[2] + "~0"
    combout = "\\" + lut + "_combout"
    inputs = changes.get("lut_inputs", {"dataa": "gnd", "datab": "gnd", "datac": "!" + buffered,
                                        "datad": "gnd", "datae": "gnd", "dataf": "gnd"})
    cell("cyclonev_lcell_comb", lut, **inputs, datag="gnd", cin="gnd", sharein="gnd",
         combout=combout, sumout="", cout="", shareout="")
    modes(lut, {"extended_lut": '"off"', "lut_mask": changes.get("lut_mask", "64'hF0F0F0F0F0F0F0F0"),
                "shared_arith": '"off"'})
    meta = "\\" + CHAIN[2] + "~q"
    cell("dffeas", CHAIN[2], clk=changes.get("clock", uart.SYSTEM_NET), d=combout, asdata="vcc",
         clrn=changes.get("reset", uart.RESET_NET), aload="gnd", sclr="gnd",
         sload=changes.get("sload", "gnd"), ena=changes.get("enable", "vcc"),
         devclrn="devclrn", devpor="devpor", q=meta, prn="vcc")
    modes(CHAIN[2], uart.REGISTER_MODES)
    cell("dffeas", CHAIN[3], clk=uart.SYSTEM_NET, d="gnd", asdata=meta, clrn=uart.RESET_NET,
         aload="gnd", sclr="gnd", sload="vcc", ena="vcc", devclrn="devclrn", devpor="devpor",
         q="\\" + CHAIN[3] + "~q", prn="vcc")
    modes(CHAIN[3], uart.REGISTER_MODES)
    if "extra" in changes:
        statements.append(changes["extra"])
    return ";\n".join(statements + params) + ";\n"


def store_row(owner, depth, width, blocks):
    bits = str(depth * width)
    cells = [f"n2m_uart:{owner}" + uart.STORE_SUFFIX, "M10K block", "True Dual Port", "Single Clock",
             str(depth), str(width), str(depth), str(width), "yes", "no", "yes", "no", bits,
             str(depth), str(width), str(depth), str(width), bits, str(blocks), "0", "None",
             "M10K_X1_Y1_N0", "Old data", "New data", "New data", "Off", "No", "No - Unsupported Mode"]
    return "; " + " ; ".join(cells) + " ;"


def write_fit(folder, *, stores=None, blocks=None, bits=None):
    stores = uart.STORES if stores is None else stores
    output = folder / "output"
    output.mkdir(parents=True, exist_ok=True)
    rows = [store_row(owner, depth, width, count) for owner, (depth, width, count) in stores.items()]
    (output / "design.fit.rpt").write_text("; Fitter RAM Summary ;\n" + "\n".join(rows) + "\n",
                                           encoding="cp1252")
    total_blocks = uart.TOTAL_BLOCKS if blocks is None else blocks
    total_bits = uart.TOTAL_BITS if bits is None else bits
    (output / "design.fit.summary").write_text(
        f"Total RAM Blocks : {total_blocks} / 553 ( 2 % )\n"
        f"Total block memory bits : {total_bits:,} / 5,662,720 ( 1 % )\n")
    return folder


class ProjectTests(unittest.TestCase):
    """The generated project states the identity, the family's memory and its I/O."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=scratch()))
        self.target = fpga.target_definition(ROOT, TARGET)

    def test_the_target_carries_an_identity_and_its_macro(self):
        self.assertTrue(fpga.identity_target(self.target))
        with self.assertRaisesRegex(ValueError, "nonzero fingerprint identity"):
            fpga.prepare(ROOT, self.folder, self.target)
        fpga.prepare(ROOT, self.folder, self.target, build_id=IDENTITY)
        qsf = (self.folder / "design.qsf").read_text(encoding="utf-8")
        self.assertIn(f'set_global_assignment -name VERILOG_MACRO "N2M_NANO_UART_BUILD_ID=128\'h{IDENTITY}"', qsf)
        self.assertIn('set_global_assignment -name RESERVE_ALL_UNUSED_PINS "AS INPUT TRI-STATED"', qsf)
        # Cyclone V has no M9K, so the product memory wrapper selects its block.
        self.assertIn('set_global_assignment -name VERILOG_MACRO "N2M_RAM_CYCLONEV=1"', qsf)

    def test_every_output_pin_states_drive_strength_and_slew_rate(self):
        fpga.prepare(ROOT, self.folder, self.target, build_id=IDENTITY)
        qsf = (self.folder / "design.qsf").read_text(encoding="utf-8")
        outputs = ["uart_tx"] + [f"leds\\[{index}\\]" for index in range(8)]
        for port in outputs:
            self.assertIn(f'set_instance_assignment -name CURRENT_STRENGTH_NEW "8MA" -to "{port}"', qsf)
            self.assertIn(f'set_instance_assignment -name SLEW_RATE 1 -to "{port}"', qsf)
        self.assertEqual(qsf.count("CURRENT_STRENGTH_NEW"), len(outputs))
        self.assertEqual(qsf.count("SLEW_RATE"), len(outputs))
        # The receive line is an input: it carries its pin and standard only.
        self.assertEqual([line for line in qsf.splitlines() if line.endswith('-to "uart_rx"')],
                         ['set_location_assignment PIN_W14 -to "uart_rx"',
                          'set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to "uart_rx"'])

    def test_the_audit_and_constraints_carry_this_board_s_corners(self):
        audit = uart.audit(fpga.tcl_word)
        for _, model, temperature in uart.CORNERS:
            self.assertIn(f"set_operating_conditions -model {model} -voltage 1100 -temperature {temperature}", audit)
        self.assertEqual(audit.count("set_operating_conditions"), len(uart.CORNERS))
        self.assertEqual(len(uart.required_reports()), 2 * len(uart.CORNERS))
        # The DE10-Lite audit is untouched by this family's corners.
        self.assertIn("-voltage 1200 -temperature 85", fpga_controls.audit(fpga.tcl_word))
        self.assertIn("set_false_path -from $controls_uart -to $controls_first_uart",
                      uart.constraints(fpga.tcl_word))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=scratch()))

    def test_every_corner_report_is_read(self):
        paths = fpga_controls.verify_reports(write_reports(self.folder), chains=uart.CHAINS,
                                            corners=uart.CORNERS, system_clock=CLOCK)
        self.assertEqual(sorted(paths), sorted(uart.required_reports()))
        self.assertEqual(set(paths.values()), {38.904})

    def test_violated_negative_or_misdirected_paths_are_rejected(self):
        for changes in ({"violated": 1}, {"slack": "-0.100"}, {"first": "u_uart|u_serial_rx|rx_sync"},
                        {"second": "u_uart|other"}, {"launch": "clk_reference"}):
            with self.subTest(changes=changes):
                write_reports(self.folder, **changes)
                with self.assertRaises(ValueError):
                    fpga_controls.verify_reports(self.folder, chains=uart.CHAINS, corners=uart.CORNERS,
                                                 system_clock=CLOCK)

    def test_a_missing_corner_report_is_rejected(self):
        write_reports(self.folder)
        (self.folder / "output" / uart.required_reports()[-1]).unlink()
        with self.assertRaises(OSError):
            fpga_controls.verify_reports(self.folder, chains=uart.CHAINS, corners=uart.CORNERS,
                                         system_clock=CLOCK)


class NetlistTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=scratch()))
        write_reports(self.folder)
        (self.folder / "simulation/questa").mkdir(parents=True)

    def structure(self, **changes):
        (self.folder / "simulation/questa/design.vo").write_text(netlist(**changes))
        return uart.verify(self.folder)

    def test_the_fitted_synchronizer_is_accepted(self):
        evidence = self.structure()
        self.assertEqual(evidence["first_stage_sinks"]["uart"],
                         {"external_path": [CHAIN[2] + "~0"], "second_path": [], "capture": CHAIN[3]})

    def test_an_unsupported_top_is_refused(self):
        for top in ("nano_clocking_proof", "sdram_proof", "controls_proof"):
            with self.subTest(top=top), self.assertRaises(ValueError):
                uart.verify(self.folder, top=top)

    def test_clock_reset_and_control_mutations_are_rejected(self):
        mutations = {"clock": r"\clk_reference~inputCLKENA0_outclk",
                     "reset": r"\u_clocking|u_reset|sys_release[0]",
                     "enable": r"\u_uart|u_serial_rx|enable",
                     "sload": r"\u_uart|u_serial_rx|select"}
        for key, value in mutations.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.structure(**{key: value})

    def test_wide_constant_or_inverted_first_stage_logic_is_rejected(self):
        buffered = "\\" + CHAIN[1] + "~input_o"
        cases = {
            # A second live input is not a unary function of the external port.
            "wide": {"lut_inputs": {"dataa": "\\other", "datab": "gnd", "datac": "!" + buffered,
                                    "datad": "gnd", "datae": "gnd", "dataf": "gnd"}},
            # A constant mask drops the port, and the wrong polarity is not the
            # complement the register's reset value requires.
            "constant": {"lut_mask": "64'h0000000000000000"},
            "polarity": {"lut_mask": "64'h0F0F0F0F0F0F0F0F"},
            # An instance that does not state every input is an unexpected shape,
            # not a grounded input.
            "partial": {"lut_inputs": {"dataa": "gnd", "datab": "gnd", "datac": "!" + buffered,
                                       "datad": "gnd", "datae": "gnd"}},
        }
        for name, changes in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                self.structure(**changes)

    def test_bypass_fanout_and_aliases_are_rejected(self):
        buffered = "\\" + CHAIN[1] + "~input_o"
        # A second consumer of the buffered port bypasses the first stage.
        bypass = ("cyclonev_lcell_comb \\u_uart|other~0 (.dataa(gnd),.datab(gnd),.datac(" + buffered
                  + "),.datad(gnd),.datae(gnd),.dataf(gnd),.datag(gnd),.cin(gnd),.sharein(gnd),"
                  ".combout(\\u_uart|other~0_combout),.sumout(),.cout(),.shareout())")
        with self.assertRaisesRegex(ValueError, "bypass fanout"):
            self.structure(extra=bypass)
        with self.assertRaisesRegex(ValueError, "unexpected alias"):
            self.structure(extra="assign \\u_uart|alias = " + buffered)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=scratch()))

    def test_the_endpoint_s_six_stores_are_accepted(self):
        self.assertEqual(uart.verify_memory(write_fit(self.folder)),
                         {"stores": 6, "blocks": 13, "bits": 76272})

    def test_a_missing_extra_or_reshaped_store_is_rejected(self):
        first = next(iter(uart.STORES))
        cases = {"missing": {name: shape for name, shape in uart.STORES.items() if name != first},
                 "extra": {**uart.STORES, "u_uart|u_other|store": (16, 8, 1)},
                 "reshaped": {**uart.STORES, first: (uart.STORES[first][0] * 2, 1, 8)}}
        for name, stores in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                uart.verify_memory(write_fit(self.folder, stores=stores))

    def test_capacity_totals_must_match_the_stores(self):
        for changes in ({"blocks": uart.TOTAL_BLOCKS + 1}, {"bits": uart.TOTAL_BITS + 8}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                uart.verify_memory(write_fit(self.folder, **changes))

    def test_a_duplicated_store_row_is_rejected(self):
        write_fit(self.folder)
        path = self.folder / "output/design.fit.rpt"
        owner, (depth, width, blocks) = next(iter(uart.STORES.items()))
        path.write_text(path.read_text(encoding="cp1252") + store_row(owner, depth, width, blocks) + "\n",
                        encoding="cp1252")
        with self.assertRaises(ValueError):
            uart.verify_memory(self.folder)

    def test_the_fitted_owner_name_is_read_as_the_instance_path(self):
        rows = fpga_vga.rows("; Fitter RAM Summary ;\n" + store_row(next(iter(uart.STORES)), 268, 8, 1) + "\n")
        self.assertEqual(len(rows[-1]), 28)


if __name__ == "__main__":
    unittest.main()
