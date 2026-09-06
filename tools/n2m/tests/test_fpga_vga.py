"""Bounded VGA collection selection; no Quartus or licensed execution."""
import tkinter
import tempfile
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.n2m import fpga, fpga_vga, fpga_pll
from tools.n2m.records import file_hash


def memory_netlist():
    """Original physical-shape fixture; no copied vendor generated HDL."""
    cells = []
    for bank in range(3):
        for block in range(6):
            bit = block % 2
            name = f"u_bridge|banks[{bank}].u_ram|u_storage|ram|auto_generated|ram_block1a{block}"
            ports = {"clk0": r"\clk_sys~inputclkctrl_outclk",
                     "clk1": r"\u_clocking|u_pll|altpll_component|auto_generated|wire_pll1_clk[0]~clkctrl_outclk",
                     "clr0": "gnd", "clr1": "gnd", "portare": "gnd", "portbwe": "gnd",
                     "portaaddrstall": "gnd", "portbaddrstall": "gnd",
                     "portabyteenamasks": "1'b1", "portbbyteenamasks": "1'b1",
                     "portadatain": "{\\shade[" + str(bit) + "]~7_combout }"}
            cells.append("fiftyfivenm_ram_block \\" + name + " (" + ",".join(f".{k}({v})" for k, v in ports.items()) + ");")
            params = {"operation_mode": "bidir_dual_port", "ram_block_type": "M9K",
                      "power_up_uninitialized": "true", "mixed_port_feed_through_mode": "dont_care",
                      "port_b_address_clock": "clock1", "port_b_read_enable_clock": "clock1"}
            for port in ("a", "b"):
                params.update({f"port_{port}_logical_ram_depth": "23040", f"port_{port}_logical_ram_width": "2",
                               f"port_{port}_data_out_clock": "none", f"port_{port}_address_clear": "none",
                               f"port_{port}_data_out_clear": "none", f"port_{port}_data_width": "1",
                               f"port_{port}_address_width": "13", f"port_{port}_first_address": "0",
                               f"port_{port}_last_address": "8191", f"port_{port}_first_bit_number": str(bit),
                               f"port_{port}_read_during_write_mode": "new_data_with_nbe_read"})
            cells += [f'defparam \\{name} .{key} = "{value}";' for key, value in params.items()]
    return "\n".join(cells)


def fixture(folder, lcd=False):
    """Original minimal tables exercise report semantics, not vendor prose."""
    output = folder / "output"
    output.mkdir()
    def write(name, text):
        (output / name).write_text(text, encoding="utf-8")
    def row(*cells):
        return "; " + " ; ".join(str(c) for c in cells) + " ;\n"
    def report(header, model, data):
        return header + "\nDelay Model:\n" + model + "\n; Summary of Paths ;\n" + data + "Path #1:\n"
    ram = row("M9Ks", "18 / 182 ( 10 % )") + row("Total block memory bits", "138,240 / 1,677,312 ( 8 % )")
    for bank in range(3):
        ram += row(f"u_bridge|banks[{bank}].u_ram|u_storage|ram|auto_generated|ALTSYNCRAM", "M9K", "True Dual Port", "Dual Clocks", "23040", "2", "23040", "2", "yes", "no", "yes", "no", "46080", "23040", "2", "23040", "2", "46080", "6", "None", "six locations", "Don't care", "New data with NBE Read", "New data with NBE Read", "Off", "No", "No - Unknown")
    outputs = []
    for color_index, color in enumerate(("red", "green", "blue")):
        for bit in range(4):
            copy = color_index * 2 + bit // 2
            register = f"u_bridge|u_scan|gray_out[{bit % 2}]" + (f"~_Duplicate_{copy}" if copy else "")
            outputs.append((f"{color}[{bit}]", register))
    outputs += [("hsync_n", "u_bridge|u_scan|hs_out"), ("vsync_n", "u_bridge|u_scan|vs_out")]
    for port, register in outputs:
        ram += row(register, "Packed Register", "Register Packing", "Timing optimization", "Q", "", port + "~output", "I", "")
    write("design.fit.rpt", ram)
    netlist = folder / "simulation/questa/design.vo"
    netlist.parent.mkdir(parents=True)
    netlist.write_text(memory_netlist(), encoding="utf-8")
    names = (*fpga_vga.CHAINS, "blank_pix", "blank_seen_sys") if lcd else fpga_vga.CHAINS
    write("vga_first_pins.rpt", "".join(f"{name} u_bridge|{name}[0]|d\n" for name in names))
    pix_clock = "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]"
    for corner, model, temperature in fpga_vga.CORNERS:
        model_name = f"{model.title()} 1200mV {temperature}C Model"
        prefix = "vga_" + corner + "_"
        for source, capture, width in fpga_vga.BUNDLES:
            data = "".join(row("1.000", f"u_bridge|{source}[{i}]", f"u_bridge|{capture}[{i}]") for i in range(width))
            write(prefix + source + ".rpt", report(f"Report Path: Found {width} paths.", model_name, data))
        for direction in ("max", "min"):
            data = "".join(row("5.000", register, port) for port, register in outputs)
            write(prefix + "outputs_" + direction + ".rpt", report("Report Path: Found 14 paths.", model_name, data))
        if lcd:
            for name, launch in (("active", "u_bridge|blank_active"), ("request", "u_bridge|blank_pix[1]")):
                for bit, (_, register) in enumerate(outputs[:12]):
                    for check in ("setup", "hold"):
                        data = row("0.750", launch, register, pix_clock, pix_clock, "39.683", "0.000", "1.000")
                        write(prefix + f"blank_{name}_gray{bit}_{check}.rpt", report(f"Report Timing: Found 1 {check} paths (0 violated).", model_name, data))
        port_filter = "[get_ports {" + " ".join("{" + p + "}" if "[" in p else p for p in fpga_vga.PORTS) + "}]"
        data = row("set_max_skew", "1.000", "2.000", "1.000", "", port_filter, "", "", "")
        data += "".join(row("--", "1.000", "2.000", "1.000", outputs[i % 14][1], outputs[i % 14][0], pix_clock, pix_clock, "") for i in range(28))
        write(prefix + "skew.rpt", report("Report Max Skew: Found 28 paths (0 violated).", model_name, data))
        for name in names:
            clock = "clk_sys" if name in ("pix_ready_sys", "ack_sys", "blank_seen_sys") else pix_clock
            for check in ("setup", "hold"):
                data = row("0.500", f"u_bridge|{name}[0]", f"u_bridge|{name}[1]", clock, clock, "20.000", "0.000", "1.000")
                write(prefix + name + "_" + check + ".rpt", report(f"Report Timing: Found 1 {check} paths (0 violated).", model_name, data))


class VgaEvidenceTests(unittest.TestCase):
    def test_physical_memory_clock_role_latency_init_and_partition_failures(self):
        text = memory_netlist()
        self.assertEqual(len(fpga_vga.verify_memory_netlist(text)), 18)
        mutations = [
            ('.clk1(\\u_clocking|', '.clk1(\\wrong_clock|'),
            ('.portbwe(gnd)', '.portbwe(vcc)'),
            ('.portare(gnd)', '.portare(vcc)'),
            ('.port_a_data_out_clock = "none"', '.port_a_data_out_clock = "clock0"'),
            ('.power_up_uninitialized = "true"', '.power_up_uninitialized = "false"'),
            ('.port_b_logical_ram_depth = "23040"', '.port_b_logical_ram_depth = "23039"'),
            ('.port_b_first_bit_number = "0"', '.port_b_first_bit_number = "1"'),
            ('shade[0]', 'shade[1]'),
            ('banks[2]', 'banks[3]'),
            ('.ram_block_type = "M9K"', '.init_file = "forbidden"'),
        ]
        for before, after in mutations:
            with self.subTest(mutation=before):
                self.assertIn(before, text)
                with self.assertRaises(ValueError):
                    fpga_vga.verify_memory_netlist(text.replace(before, after, 1))


    def test_truncated_mutable_and_immutable_cache_cannot_omit_vga_report(self):
        for lcd in (False, True):
            with self.subTest(lcd=lcd):
                self.cache_inventory(lcd)

    def cache_inventory(self, lcd):
        base = Path(__file__).resolve().parents[3] / "workdir" / "vga-report-tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            root = Path(temp)
            build = root / "workdir/builds/test"
            folder = build / "attempt"
            names = ["output/" + name for name in [*fpga.REQUIRED_REPORTS, *fpga_pll.required_reports(), *fpga_vga.required_reports(lcd=lcd)]]
            names += ["n2m_pixel_pll.v", "generate-pll.log", "simulation/questa/design.vo", "netlist.log",
                      "design.qpf", "design.qsf", "audit.tcl", "compile.log", "audit.log", "checked.sdc"]
            for name in names:
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("original fixture")
            record = {"status": "PASS", "fingerprint": "request", "artifacts": {p.relative_to(root).as_posix(): file_hash(p) for p in folder.rglob("*") if p.is_file()},
                      "attempt_result": (folder / "result.json").relative_to(root).as_posix(),
                      "evidence_directory": folder.relative_to(root).as_posix(), "evidence": {}}
            (folder / "result.json").write_text(json.dumps(record))
            target = {"top": "ppu_proof" if lcd else "vga_proof", "pll": {}, "timing": {}}
            with patch.object(fpga, "timing_evidence", return_value={}):
                self.assertTrue(fpga.complete_cache(record, "request", root, build, target))
                for name in fpga_vga.required_reports(lcd=lcd):
                    path = folder / "output" / name
                    truncated = {**record, "artifacts": {k: v for k, v in record["artifacts"].items() if k != path.relative_to(root).as_posix()}}
                    (folder / "result.json").write_text(json.dumps(truncated))
                    path.unlink()
                    with self.subTest(missing=name):
                        self.assertFalse(fpga.complete_cache(truncated, "request", root, build, target))
                    path.write_text("original fixture")

    def test_lcd_crossings_and_blank_output_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            fixture(folder, lcd=True)
            result = fpga_vga.verify(folder, lcd=True)
            self.assertEqual(len(result["corners"]["slow85"]["chain_slack_ns"]), 12)
            self.assertEqual(len(result["corners"]["slow85"]["blank_control_slack_ns"]), 48)
            pixel = "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]"
            for name, old, new in [
                ("vga_slow0_blank_seen_sys_setup.rpt", "clk_sys", pixel),
                ("vga_slow85_blank_request_gray1_hold.rpt", pixel, "clk_sys"),
                ("vga_slow0_outputs_max.rpt", "gray_out[0]", "x_out[6]"),
                ("vga_fast0_blank_pix_hold.rpt", "; 0.500 ;", "; -0.001 ;"),
                ("vga_slow85_blank_active_gray0_setup.rpt", "u_bridge|blank_active", "u_bridge|request"),
                ("vga_slow0_blank_request_gray0_hold.rpt", "gray_out[0]", "gray_out[1]"),
                ("vga_fast0_blank_active_gray1_setup.rpt", "; 0.750 ;", "; -0.001 ;"),
                ("vga_first_pins.rpt", "blank_seen_sys[0]|d", "blank_seen_sys[1]|d"),
            ]:
                path = folder / "output" / name
                original = path.read_text()
                self.assertIn(old, original)
                path.write_text(original.replace(old, new))
                with self.subTest(mutation=name), self.assertRaises(ValueError):
                    fpga_vga.verify(folder, lcd=True)
                path.write_text(original)
            for name in set(fpga_vga.required_reports(lcd=True)) - set(fpga_vga.required_reports()):
                path = folder / "output" / name
                original = path.read_text()
                path.unlink()
                with self.subTest(missing=name), self.assertRaises(ValueError):
                    fpga_vga.verify(folder, lcd=True)
                path.write_text(original)

    def test_complete_inventory_bounds_and_corner_mutations(self):
        base = Path(__file__).resolve().parents[3] / "workdir" / "vga-report-tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            folder = Path(temp)
            fixture(folder)
            self.assertEqual(fpga_vga.verify(folder)["m9k_blocks"], 18)
            changes = [
                ("vga_fast0_outputs_max.rpt", "gray_out[0]", "valid_out"),
                ("vga_fast0_outputs_max.rpt", "gray_out[0]~_Duplicate_1", "gray_out[1]~_Duplicate_1"),
                ("design.fit.rpt", "gray_out[0]~_Duplicate_5", "gray_out[0]~_Duplicate_6"),
                ("design.fit.rpt", "red[0]~output", "red[1]~output"),
                ("vga_fast0_outputs_max.rpt", "gray_out[0]", "gray_out[2]"),
                ("vga_fast0_offer_sequence.rpt", "|captured_sequence[63]", "|captured_sequence[62]"),
                ("vga_slow0_offer_epoch.rpt", "; 1.000 ;", "; 20.001 ;"),
                ("vga_fast0_outputs_max.rpt", "; 5.000 ;", "; 10.001 ;"),
                ("vga_fast0_outputs_min.rpt", "; 5.000 ;", "; -0.001 ;"),
                ("vga_slow85_outputs_min.rpt", "; 5.000 ;", "; 2.000 ;"),
                ("vga_slow85_skew.rpt", "; 2.000 ;", "; 3.000 ;"),
                ("vga_fast0_skew.rpt", "Fast 1200mV 0C Model", "Slow 1200mV 85C Model"),
                ("vga_slow85_req_pix_hold.rpt", "; 0.500 ;", "; -0.001 ;"),
                ("vga_slow0_ack_sys_setup.rpt", "u_bridge|ack_sys[1]", "u_bridge|ack_sys[0]"),
                ("design.fit.rpt", "Dual Clocks", "Single Clock"),
                ("design.fit.rpt", "18 / 182", "19 / 182"),
                ("vga_first_pins.rpt", "pix_ready_sys[0]|d", "pix_ready_sys[1]|d"),
            ]
            for name, old, new in changes:
                path = folder / "output" / name
                original = path.read_text()
                self.assertIn(old, original)
                path.write_text(original.replace(old, new, 1))
                with self.subTest(name=name), self.assertRaises(ValueError):
                    fpga_vga.verify(folder)
                path.write_text(original)
            for name in fpga_vga.required_reports():
                path = folder / "output" / name
                original = path.read_bytes()
                path.unlink()
                with self.subTest(missing=name), self.assertRaisesRegex(ValueError, "missing VGA evidence"):
                    fpga_vga.verify(folder)
                path.write_bytes(original)

    def test_physical_register_selection_rejects_missing_or_duplicate(self):
        original = "n2m_frame_bridge:u_bridge|n2m_vga_scan:u_scan|gray_out[0]"
        for candidates, accepted in [([], False), ([original], True),
                ([original, original + "~_Duplicate_1"], True),
                ([original + "~_Duplicate_1"], False), ([original, original], False)]:
            with self.subTest(candidates=candidates):
                tcl = tkinter.Tcl()
                tcl.createcommand("get_registers", lambda *args: tuple(candidates))
                tcl.eval("proc get_register_info {flag item} {return $item}")
                tcl.eval("proc foreach_in_collection {var items body} {upvar 1 $var value; foreach value $items {uplevel 1 $body}}")
                script = "\n".join(fpga_vga.physical_register(0, "u_bridge|u_scan|gray_out[0]", fpga.tcl_word))
                if accepted:
                    tcl.eval(script)
                    self.assertEqual(tcl.splitlist(tcl.getvar("vga_gray_0")), (original,))
                else:
                    with self.assertRaisesRegex(tkinter.TclError, "VGA physical output mismatch"):
                        tcl.eval(script)

    def test_exact_first_data_pin_rejects_missing_or_ambiguous_mapping(self):
        for name in (*fpga_vga.CHAINS, "blank_pix", "blank_seen_sys"):
            for suffixes in ([], ["d"], ["asdata"], ["d", "asdata"]):
                with self.subTest(name=name, suffixes=suffixes):
                    tcl = tkinter.Tcl()
                    found = tuple(f"u_bridge|{name}[0]|{suffix}" for suffix in suffixes)
                    requests = []
                    def get_pins(*args):
                        requests.append(args)
                        return found
                    tcl.createcommand("get_pins", get_pins)
                    tcl.eval("proc get_collection_size {items} {llength $items}")
                    tcl.eval("proc get_pin_info {flag item} {return $item}")
                    tcl.eval("proc foreach_in_collection {var items body} {upvar 1 $var value; foreach value $items {uplevel 1 $body}}")
                    tcl.eval("proc puts {args} {}")
                    script = "\n".join(fpga_vga.first_pin(name, fpga.tcl_word))
                    if len(suffixes) == 1:
                        tcl.eval(script)
                    else:
                        with self.assertRaisesRegex(tkinter.TclError, "VGA first data pin mismatch"):
                            tcl.eval(script)
                    self.assertEqual(requests[0][0], "-nowarn")
                    self.assertEqual(tcl.splitlist(requests[0][1]),
                                     (f"u_bridge|{name}[0]|d", f"u_bridge|{name}[0]|asdata"))


if __name__ == "__main__":
    unittest.main()
