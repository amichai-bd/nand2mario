"""Bounded VGA collection selection; no Quartus or licensed execution."""
import tkinter
import tempfile
from pathlib import Path
import unittest

from tools.n2m import fpga, fpga_vga


def fixture(folder):
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
        ram += row(f"u_bridge|banks[{bank}].u_ram|pixels_rtl_0|auto_generated|ALTSYNCRAM", "M9K", "Simple Dual Port", "Dual Clocks", "23040", "2", "23040", "2", "yes", "no", "yes", "no", "46080", "23040", "2", "23040", "2", "46080", "6", "None")
    write("design.fit.rpt", ram)
    write("vga_first_pins.rpt", "".join(f"{name} u_bridge|{name}[0]|d\n" for name in fpga_vga.CHAINS))
    pix_clock = "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]"
    for corner, model, temperature in fpga_vga.CORNERS:
        model_name = f"{model.title()} 1200mV {temperature}C Model"
        prefix = "vga_" + corner + "_"
        for source, capture, width in fpga_vga.BUNDLES:
            data = "".join(row("1.000", f"u_bridge|{source}[{i}]", f"u_bridge|{capture}[{i}]") for i in range(width))
            write(prefix + source + ".rpt", report(f"Report Path: Found {width} paths.", model_name, data))
        for direction in ("max", "min"):
            data = "".join(row("5.000", "u_bridge|u_scan|gray_out[0]", port) for port in fpga_vga.PORTS)
            write(prefix + "outputs_" + direction + ".rpt", report("Report Path: Found 14 paths.", model_name, data))
        port_filter = "[get_ports {" + " ".join("{" + p + "}" if "[" in p else p for p in fpga_vga.PORTS) + "}]"
        data = row("set_max_skew", "1.000", "2.000", "1.000", "", port_filter, "", "", "")
        data += "".join(row("--", "1.000", "2.000", "1.000", "u_bridge|u_scan|gray_out[0]", fpga_vga.PORTS[i % 14], pix_clock, pix_clock, "") for i in range(28))
        write(prefix + "skew.rpt", report("Report Max Skew: Found 28 paths (0 violated).", model_name, data))
        for name in fpga_vga.CHAINS:
            clock = "clk_sys" if name in ("pix_ready_sys", "ack_sys") else pix_clock
            for check in ("setup", "hold"):
                data = row("0.500", f"u_bridge|{name}[0]", f"u_bridge|{name}[1]", clock, clock, "20.000", "0.000", "1.000")
                write(prefix + name + "_" + check + ".rpt", report(f"Report Timing: Found 1 {check} paths (0 violated).", model_name, data))


class VgaEvidenceTests(unittest.TestCase):
    def test_complete_inventory_bounds_and_corner_mutations(self):
        base = Path(__file__).resolve().parents[3] / "workdir" / "vga-report-tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            folder = Path(temp)
            fixture(folder)
            self.assertEqual(fpga_vga.verify(folder)["m9k_blocks"], 18)
            changes = [
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

    def test_exact_first_data_pin_rejects_missing_or_ambiguous_mapping(self):
        for name in fpga_vga.CHAINS:
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
