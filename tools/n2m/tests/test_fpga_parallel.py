"""Independent reset topology challenges for the two-clock PLL implementation.

The fixture takes the family's fitted atom set, so the one abstract topology
serves every ALTPLL family and no family gets a copied fixture.
"""
import unittest
from tools.n2m import fpga_lock, fpga_pll


def fixture(primitives=fpga_lock.MAX10):
    reset = fpga_lock.RESET
    prefixes = (fpga_lock.PLL, "u_clocking|u_system_pll|altpll_component|auto_generated|")
    lines = ["wire gnd;", "wire vcc;", "assign gnd = 1'b0;", "assign vcc = 1'b1;", "tri1 devclrn;", "tri1 devpor;"]
    def cell(kind, name, **ports):
        lines.append(kind + " \\" + name + " (" + ",".join(f".{p}({v})" for p,v in ports.items()) + ");")
        modes = {primitives.register: {"is_wysiwyg": '"true"', "power_up": '"low"'},
                 primitives.buffer: {"clock_type": '"global clock"', "ena_register_mode": '"none"'}}
        for key,value in modes.get(kind,{}).items(): param(name,key,value)
    def param(name,key,value):
        lines.append("defparam \\" + name + f" .{key} = {value};")
    def gate(name, mask, inputs, output):
        cell(primitives.lut, name, **dict(zip(("dataa","datab","datac","datad"),inputs)), cin="gnd", cout="", combout=output)
        param(name,"lut_mask",mask);param(name,"sum_lutc_input",'"datac"')
    def buffer(name, source):
        output="\\" + name + "_outclk"
        cell(primitives.buffer,name,ena="vcc",clkselect="2'b00",inclk="{vcc,vcc,vcc,"+source+"}",outclk=output,devclrn="devclrn",devpor="devpor")
        return output
    release="\\release"
    cell(primitives.register, reset+"pll_areset", q=release, clk=r"\clk_reference~inputclkctrl_outclk")
    reset_buffer=buffer(reset+"pll_areset~clkctrl",release)
    roots=[]
    for index,prefix in enumerate(prefixes):
        raw=f"\\raw{index}";q="\\"+prefix+"pll_lock_sync~q";data=f"\\data{index}"
        cell(primitives.pll,prefix+"pll1",locked=raw,areset="!"+reset_buffer,inclk=r"{gnd,\clk_reference~input_o}")
        gate(prefix+"pll_lock_sync~feeder","16'hFFFF",["gnd"]*4,data)
        cell(primitives.register,prefix+"pll_lock_sync",clk=raw,d=data,asdata="vcc",clrn=reset_buffer,aload="gnd",sclr="gnd",sload="gnd",ena="vcc",devclrn="devclrn",devpor="devpor",q=q,prn="vcc")
        roots += [q,raw]
    gate(reset+"lock_reset~0","16'h7FFF",roots,r"\intermediate")
    gate(reset+"lock_reset","16'hFF33",["gnd",release,"gnd",r"\intermediate"],r"\final")
    lock_buffer=buffer(reset+"lock_reset~clkctrl",r"\final")
    for i in (0,1):
        cell(primitives.register,reset+f"lock_samples[{i}]",q="\\"+reset+f"lock_samples[{i}]",d="vcc" if i==0 else "\\"+reset+"lock_samples[0]",asdata="vcc",clk=fpga_pll.SYSTEM_NET,clrn="!"+lock_buffer,prn="vcc",ena="vcc",aload="gnd",sclr="gnd",sload="gnd",devclrn="devclrn",devpor="devpor")
    system_row="n2m_clocking:u_clocking|n2m_system_pll:u_system_pll|altpll:altpll_component|n2m_system_pll_altpll:auto_generated|pll_lock_sync"
    checks="\n".join("; "+row+"; No clock feeds this register's clock port. ;" for row in (fpga_lock.ROW,system_row))
    return "\n".join(lines),checks


class ParallelClockTests(unittest.TestCase):
    def test_either_lock_loss_asserts_reset(self):
        text,checks=fixture()
        self.assertEqual(fpga_lock.verify_parallel(text,checks,"clocking_proof")["truth_cases"],32)

    def test_synchronous_load_keeps_the_same_pipeline(self):
        text,checks=fixture()
        lines=text.splitlines()
        for i,line in enumerate(lines):
            if line.startswith(r"dffeas \u_clocking|u_reset|lock_samples[1] "):
                lines[i]=line.replace(r".d(\u_clocking|u_reset|lock_samples[0]),.asdata(vcc)",
                                      r".d(gnd),.asdata(\u_clocking|u_reset|lock_samples[0])").replace(".sload(gnd)",".sload(vcc)")
                self.assertNotEqual(lines[i],line)
        self.assertEqual(fpga_lock.verify_parallel("\n".join(lines),checks,"clocking_proof")["truth_cases"],32)

    def test_unsafe_topologies_fail_closed(self):
        text,checks=fixture()
        mutations = {
            "raw lock ignored": text.replace("16'h7FFF","16'h7777"),
            "reset ignored": text.replace("16'hFF33","16'hFF00"),
            "bootstrap self clock": text.replace(r"\clk_reference~inputclkctrl_outclk",fpga_pll.SYSTEM_NET),
            "wrong sampler clock": text.replace(fpga_pll.SYSTEM_NET,r"\other_clock"),
            "wrong reference": text.replace(r"{gnd,\clk_reference~input_o}",r"{gnd,\pixel_clock}"),
            "wrong reset polarity": text.replace(".areset(!", ".areset("),
            "event functional fanout": text + r"dffeas bad (.clk(\raw0));",
            "extra raw driver": text + r"dffeas bad (.q(\raw0));",
            "aliased raw": text + r"assign extra = \raw0;",
            "sample stage bypassed": text.replace(r".d(\u_clocking|u_reset|lock_samples[0])", ".d(vcc)"),
            "constant changed": text.replace("assign vcc = 1'b1", "assign vcc = 1'b0"),
        }
        for name,mutated in mutations.items():
            with self.subTest(name=name),self.assertRaises(ValueError):
                fpga_lock.verify_parallel(mutated,checks,"clocking_proof")
        with self.assertRaises(ValueError):
            fpga_lock.verify_parallel(text,checks+checks,"clocking_proof")


class MergeDiagnosticTests(unittest.TestCase):
    """Quartus 25.1 names the PLL pair in either order; the classification matches the set."""
    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        parent = Path(__file__).resolve().parents[3] / "workdir" / "fpga-unit-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        verified = patch.object(fpga_pll, "verify")
        verified.start()
        self.addCleanup(verified.stop)
        self.definition = {"module": "n2m_pixel_pll", "input_ps": 20000, "multiply": 63, "divide": 125, "system_divide": 2}

    def line(self, first, second, name, suffix=" Line: 93"):
        path = (self.folder / "db" / name).resolve().as_posix()
        return (f"Warning (176127): The parameters of the PLL {first} and the PLL {second} do not have the same values"
                f" - hence these PLLs cannot be merged File: {path}{suffix}")

    def test_either_order_and_either_generated_file_are_one_explained_line(self):
        pixel, system = fpga_pll.MERGE_PAIR
        for first, second, name in ((pixel, system, "n2m_pixel_pll_altpll.v"), (system, pixel, "n2m_system_pll_altpll.v"),
                                    (system, pixel, "n2m_pixel_pll_altpll.v")):
            text = "Info (1): before\n" + self.line(first, second, name) + "\nInfo (2): after\n"
            explained = fpga_pll.explained_diagnostics(text, self.folder, self.definition)
            self.assertEqual([item["code"] for item in explained], ["176127"])
            self.assertEqual(explained[0]["text"], self.line(first, second, name))
        self.assertEqual(fpga_pll.explained_diagnostics("Info (1): quiet\n", self.folder, self.definition), [])
        self.assertEqual(fpga_pll.explained_diagnostics(self.line(system, pixel, "n2m_system_pll_altpll.v"), self.folder,
                                                        dict(self.definition, system_divide=None)), [])

    def test_other_pairs_files_counts_and_text_stay_unexplained(self):
        pixel, system = fpga_pll.MERGE_PAIR
        good = self.line(system, pixel, "n2m_system_pll_altpll.v")
        for bad in (good + "\n" + good,
                    self.line(system, system, "n2m_system_pll_altpll.v"),
                    self.line(system, pixel.replace("u_pll", "u_other"), "n2m_system_pll_altpll.v"),
                    self.line(system, pixel, "n2m_adc_pll_altpll.v"),
                    self.line(system, pixel, "../n2m_system_pll_altpll.v"),
                    good.replace("cannot be merged", "were merged"),
                    good.replace(" Line: 93", ""),
                    good + " trailing"):
            with self.assertRaises(ValueError):
                fpga_pll.explained_diagnostics(bad, self.folder, self.definition)
