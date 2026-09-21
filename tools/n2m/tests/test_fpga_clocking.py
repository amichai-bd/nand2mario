"""Independent synthetic netlists challenge the narrow vendor-event classification."""
import ast
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from tools.n2m import fpga_lock, fpga_constraints, fpga, fpga_clocking, fpga_pll
from tools.n2m.records import file_hash
from tools.n2m.tests.fit_reports import no_clock_table


# The single-PLL definition the cache fixtures declare; the family selects the
# clocking implementation that names the generated files.
SINGLE_PLL = {"module": "n2m_pixel_pll", "input_ps": 20000, "multiply": 63, "divide": 125}


def fixture():
    # Construct an abstract evidence fixture, not a copied vendor implementation.
    pll, reset = fpga_lock.PLL, fpga_lock.RESET
    cells = ["wire gnd;", "wire vcc;", "assign gnd = 1'b0;", "assign vcc = 1'b1;", "tri1 devclrn;", "tri1 devpor;"]
    def cell(kind, name, **ports):
        cells.append(kind + " \\" + name + " (" + ",".join(f".{p}({v})" for p, v in ports.items()) + ");")
        if kind == "dffeas":
            param(name, "is_wysiwyg", '"true"')
            param(name, "power_up", '"low"')
        elif kind == "fiftyfivenm_clkctrl":
            param(name, "clock_type", '"global clock"')
            param(name, "ena_register_mode", '"none"')
        elif kind == "fiftyfivenm_lcell_comb":
            param(name, "sum_lutc_input", '"datac"')
    def param(name, key, value):
        cells.append("defparam \\" + name + f" .{key} = {value};")
    raw, q, release = "\\raw", "\\" + pll + "pll_lock_sync~q", "\\release"
    data = "\\" + pll + "pll_lock_sync~feeder_combout"
    cell("fiftyfivenm_pll", pll + "pll1", locked=raw, areset="!\\reset_buffer")
    cell("dffeas", pll + "pll_lock_sync", clk=raw, d=data, asdata="vcc", clrn="\\reset_buffer",
         aload="gnd", sclr="gnd", sload="gnd", ena="vcc", devclrn="devclrn", devpor="devpor", q=q, prn="vcc")
    cell("fiftyfivenm_lcell_comb", pll + "pll_lock_sync~feeder", dataa="gnd", datab="gnd", datac="gnd", datad="gnd", cin="gnd", combout=data)
    param(pll + "pll_lock_sync~feeder", "lut_mask", "16'hFFFF")
    cell("dffeas", reset + "pll_areset", q=release, clk="\\system_clock")
    cell("fiftyfivenm_clkctrl", reset + "pll_areset~clkctrl", ena="vcc", clkselect="2'b00", inclk="{vcc,vcc,vcc," + release + "}", outclk="\\reset_buffer")
    cell("fiftyfivenm_lcell_comb", reset + "lock_reset~0", dataa=q, datab=release, datac=raw, datad="gnd", cin="gnd", combout="\\lock_gate")
    param(reset + "lock_reset~0", "lut_mask", "16'h7F7F")
    cell("fiftyfivenm_clkctrl", reset + "lock_reset~0clkctrl", ena="vcc", clkselect="2'b00", inclk="{vcc,vcc,vcc,\\lock_gate}", outclk="\\lock_buffer")
    for i in (0, 1):
        cell("dffeas", reset + f"lock_samples[{i}]", clrn="!\\lock_buffer", clk="\\system_clock")
    return "\n".join(cells), no_clock_table([fpga_lock.ROW])


# The accepted inventory a single-PLL target resolves: this one lock event and
# nothing else. The checker is handed it rather than restating it.
ROWS = [(fpga_lock.ROW, fpga_lock.REGISTER_REASON)]


class ClockingEvidenceTests(unittest.TestCase):
    def test_pll_cache_requires_generated_netlist_and_checked_constraints(self):
        scratch = Path(__file__).resolve().parents[3] / "workdir/fpga-clock-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root = Path(temporary)
            build = root / "workdir/builds/test"
            folder = build / "attempt"
            inventory = ["output/" + name for name in fpga.REQUIRED_REPORTS + tuple(fpga_pll.required_reports())]
            inventory += ["n2m_pixel_pll.v", "generate-pll.log", "simulation/questa/design.vo", "netlist.log",
                          "design.qpf", "design.qsf", "audit.tcl", "compile.log", "audit.log", "checked.sdc"]
            for name in inventory:
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic evidence")
            record = {"status": "PASS", "fingerprint": "request", "artifacts": {p.relative_to(root).as_posix(): file_hash(p) for p in folder.rglob("*") if p.is_file()},
                      "attempt_result": (folder / "result.json").relative_to(root).as_posix(),
                      "evidence_directory": folder.relative_to(root).as_posix(), "evidence": {}}
            (folder / "result.json").write_text(json.dumps(record))
            with patch.object(fpga, "timing_evidence", return_value={}):
                self.assertTrue(fpga.complete_cache(record, "request", root, build, {"family": "MAX 10", "pll": SINGLE_PLL, "timing": {}}))
                for missing in ("n2m_pixel_pll.v", "simulation/questa/design.vo", "checked.sdc", "output/chain_pix_release_hold.rpt"):
                    truncated = {**record, "artifacts": {k: v for k, v in record["artifacts"].items() if k != (folder / missing).relative_to(root).as_posix()}}
                    (folder / "result.json").write_text(json.dumps(truncated))
                    with self.subTest(missing=missing):
                        self.assertFalse(fpga.complete_cache(truncated, "request", root, build, {"family": "MAX 10", "pll": SINGLE_PLL, "timing": {}}))
    def test_only_documented_lock_event_is_classified(self):
        text, checks = fixture()
        self.assertEqual(fpga_lock.verify(text, checks, rows=ROWS)["endpoint"], fpga_lock.ROW)

    def test_plain_primitive_parameter_owner_keeps_strict_grammar(self):
        text, checks = fixture()
        plain = '\ndffeas frame_read (.clk(gnd), .d(gnd), .q(frame_value));\ndefparam frame_read.is_wysiwyg = "true";'
        self.assertEqual(fpga_lock.verify(text + plain, checks, rows=ROWS)["endpoint"], fpga_lock.ROW)
        for bad in (plain + '\ndefparam frame_read.is_wysiwyg = "true";',
                    plain.replace('frame_read.is_wysiwyg', 'frame_read..is_wysiwyg'),
                    plain.replace('frame_read.is_wysiwyg', '9bad.is_wysiwyg')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                fpga_lock.verify(text + bad, checks, rows=ROWS)

    def test_topology_mutations_are_not_classified(self):
        text, checks = fixture()
        mutations = [text.replace("16'hFFFF", "16'hFFFE"),
                     text.replace("16'h7F7F", "16'hFFFF"),
                     text.replace(".areset(!\\reset_buffer)", ".areset(!\\other_reset)"),
                     text.replace(".clk(\\raw)", ".clk(\\system_clock)"),
                     text + "\ndffeas \\bad (.d(\\" + fpga_lock.PLL + "pll_lock_sync~q ));",
                     text + "\ndffeas \\bad (.d(\\lock_buffer));",
                     text + "\ndffeas bad (.d(\\lock_buffer));",
                     text + "\n  dffeas bad (.d(\\lock_buffer ));",
                     text + '\ndffeas #(.power_up("low")) bad (.d(\\lock_buffer ));',
                     text + " dffeas bad (.d(\\lock_buffer ));",
                     text + "\ncustom bad (.q(\\lock_buffer ));",
                     text + "\ndffeas bad (.q(\\lock_buffer ));",
                     text + "\nassign \\lock_buffer = bad;",
                     text + "\ndffeas bad (.d(func(\\lock_buffer)));",
                     text + "\nassign bad = \\lock_buffer ;"]
        for mutated in mutations:
            with self.subTest(mutated=mutated[-80:]), self.assertRaises(ValueError):
                fpga_lock.verify(mutated, checks, rows=ROWS)

    def test_extra_or_wrong_no_clock_row_fails(self):
        text, checks = fixture()
        for report in (checks + checks, checks.replace(fpga_lock.ROW, "functional_register"), ""):
            with self.assertRaises(ValueError):
                fpga_lock.verify(text, report, rows=ROWS)

    def test_primitive_modes_and_constant_drivers_are_closed(self):
        text, checks = fixture()
        mutations = [text.replace('sum_lutc_input = "datac"', 'sum_lutc_input = "cin"'),
                     text.replace('ena_register_mode = "none"', 'ena_register_mode = "falling edge"'),
                     text.replace('power_up = "low"', 'power_up = "high"'),
                     text.replace("assign vcc = 1'b1", "assign vcc = 1'b0"),
                     text.replace("assign vcc = 1'b1", "wire other; assign {vcc, other} = 1'b1"),
                     text.replace("tri1 devpor", "tri0 devpor"),
                     text.replace("wire vcc", "tri0 vcc"),
                     text + "\nassign vcc = 1'b0;",
                     text + "\nassign vcc[0] = 1'b0;",
                     text + "\ndffeas bad (.q(vcc));",
                     text + '\ndefparam \\' + fpga_lock.PLL + 'pll_lock_sync .invert_clock = "true";',
                     text + '\ndefparam \\' + fpga_lock.PLL + 'pll_lock_sync .sclr_over_ena = "true";']
        for mutated in mutations:
            with self.subTest(mutated=mutated[-100:]), self.assertRaises(ValueError):
                fpga_lock.verify(mutated, checks, rows=ROWS)

    def test_checked_constraints_reject_broad_or_executable_endpoints(self):
        for endpoint in ("*|clrn", "cell|q", "cell|clrn;source extra.sdc", "cell|clrn\nsource extra.sdc"):
            with self.assertRaises(ValueError):
                fpga_constraints.validate({"reference_ns": "20.000", "async_reset_pins": [endpoint],
                                           "output_delays": [{"clock": "clk", "ports": ["count[*]"], "count": 8}]})


# Quartus prints junction temperatures with a degree sign, which is the byte
# 0xb0 in the encoding it writes; utf-8 refuses it.
DEGREE = "\N{DEGREE SIGN}"
PARALLEL_PLL = {**SINGLE_PLL, "system_divide": 2}
STA_HEADER = ("; Clock Name ; Type ; Period ; Frequency ; Rise ; Fall ; Duty Cycle ; Divide by ; Multiply by ;"
              " Phase ; Offset ; Edge List ; Edge Shift ; Inverted ; Master ; Source ; Targets ;")


def fit_prologue():
    """The report preamble that carries the non-ASCII byte."""
    return ("+-------------------------------------+\n"
            "; Operating Settings and Conditions   ;\n"
            f"; Core Junction Temperature ; 85 {DEGREE}C ;\n"
            f"; Low Junction Temperature  ; 0 {DEGREE}C  ;\n")


def fit_row(fields):
    return "; " + " ; ".join(fields) + " ;"


def usage_row(source, clock, divide, multiply, frequency, counter):
    """One fitted PLL output row, in the 15-column usage-summary shape."""
    return fit_row([source + "|wire_pll1_clk[0]", "clock0", divide, multiply, frequency, "0 (0 ps)", "",
                    "50/50", "C0", counter, "", "", "", "", clock])


def single_fit():
    """A single-PLL MAX 10 fit report in the shape verify_fit accepts."""
    values = {"PLL mode": "Normal", "Compensate clock": "clock0", "Input frequency 0": "50.0 MHz",
              "Nominal PFD frequency": "10.0 MHz", "Nominal VCO frequency": "630.0 MHz",
              "M value": "63", "N value": "5", "Inclk0 signal type": "Dedicated Pin"}
    lines = [fit_row([key, value]) for key, value in values.items()]
    lines.append(usage_row("n2m_clocking:u_clocking|n2m_pixel_pll:u_pll", fpga_pll.PIXEL_CLOCK,
                          "63", "125", "25.2 MHz", "25"))
    return fit_prologue() + "\n".join(lines) + "\n"


def parallel_fit():
    """A system/pixel MAX 10 fit report in the shape verify_parallel_fit accepts."""
    columns = (fpga_pll.SYSTEM_PLL, fpga_pll.PIXEL_PLL)
    values = {"PLL mode": ("Normal", "Normal"), "Compensate clock": ("clock0", "clock0"),
              "Input frequency 0": ("50.0 MHz", "50.0 MHz"),
              "Nominal PFD frequency": ("6.3 MHz", "10.0 MHz"),
              "Nominal VCO frequency": ("650.0 MHz", "630.0 MHz"),
              "M value": ("104", "63"), "N value": ("8", "5"),
              "Inclk0 signal type": ("Dedicated Pin", "Dedicated Pin")}
    lines = [fit_row(("SDC pin name",) + columns)]
    lines += [fit_row((key,) + pair) for key, pair in values.items()]
    lines.append(usage_row("n2m_clocking:u_clocking|n2m_system_pll:u_system_pll", fpga_pll.SYSTEM_CLOCK,
                           "1", "2", "25.0 MHz", "26"))
    lines.append(usage_row("n2m_clocking:u_clocking|n2m_pixel_pll:u_pll", fpga_pll.PIXEL_CLOCK,
                           "63", "125", "25.2 MHz", "25"))
    return fit_prologue() + "\n".join(lines) + "\n"


def sta_report(rows):
    lines = [STA_HEADER]
    for name, kind, period, ratio, master in rows:
        duty, divide, multiply = ratio or ("", "", "")
        lines.append(f"; {name} ; {kind} ; {period} ; ; ; ; {duty} ; {divide} ; {multiply} ; ; ; ; ; false ; {master} ; ; ;")
    return "\n".join(lines) + "\n"


def single_sta():
    return sta_report([("clk_sys", "Base", "20.000", None, ""),
                       (fpga_pll.PIXEL_CLOCK, "Generated", "39.683", ("50.00", "125", "63"), "clk_sys")])


def parallel_sta():
    return sta_report([("clk_reference", "Base", "20.000", None, ""),
                       (fpga_pll.SYSTEM_CLOCK, "Generated", "40.000", ("50.00", "2", "1"), "clk_reference"),
                       (fpga_pll.PIXEL_CLOCK, "Generated", "39.683", ("50.00", "125", "63"), "clk_reference")])


class FitReportEncodingTests(unittest.TestCase):
    """The fit report is decoded as Quartus writes it, not as the host guesses.

    Both MAX 10 reader sites are covered, each with a report carrying the
    degree sign. Before the fix these reads used utf-8 off Windows and every
    DE10-Lite PLL target raised UnicodeDecodeError here.
    """

    def build(self, fit, sta, total):
        scratch = Path(__file__).resolve().parents[3] / "workdir/fpga-clock-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        folder = Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch)))
        output = folder / "output"
        output.mkdir()
        (output / "design.fit.rpt").write_text(fit, encoding=fpga_pll.FIT_ENCODING)
        (output / "design.sta.rpt").write_text(sta, encoding="utf-8")
        (output / "design.fit.summary").write_text(f"Total PLLs : {total} / 4 ( 50 % )\n", encoding="utf-8")
        for name in fpga_pll.required_reports():
            path = output / name
            if name.startswith("chain_"):
                chain, check = name.removeprefix("chain_").removesuffix(".rpt").rsplit("_", 1)
                path.write_text(f"Report Timing: Found 1 {check} paths (0 violated).  Worst case slack is 0.500\n"
                                f"u_reset|{chain}[0] -> u_reset|{chain}[1]\n", encoding="utf-8")
            else:
                path.write_text("synthetic report\n", encoding="utf-8")
        return folder

    def case(self, parallel):
        pll = PARALLEL_PLL if parallel else SINGLE_PLL
        fit, sta, total = (parallel_fit(), parallel_sta(), 2) if parallel else (single_fit(), single_sta(), 1)
        folder = self.build(fit, sta, total)
        return folder, {"pll": pll, "timing": {"reference_ns": "20.000"}, "top": "clocking_proof"}

    def test_both_reader_sites_accept_a_report_with_a_non_ascii_byte(self):
        for parallel in (False, True):
            with self.subTest(parallel=parallel):
                folder, target = self.case(parallel)
                raw = (folder / "output/design.fit.rpt").read_bytes()
                self.assertIn(b"\xb0", raw)
                fpga_pll.verify_fit(folder, target)

    def test_the_host_chosen_utf8_read_is_what_used_to_fail(self):
        """The defect, stated as a test: the same bytes are undecodable as utf-8."""
        folder, _ = self.case(True)
        path = folder / "output/design.fit.rpt"
        with self.assertRaises(UnicodeDecodeError):
            path.read_text(encoding="utf-8")

    def test_the_encoding_is_the_one_windows_already_used(self):
        """Criterion 4 at the decode boundary: same bytes, same text, so same evidence.

        The pre-fix expression chose cp1252 on Windows and utf-8 elsewhere. The
        constant is that cp1252, so a report decodes to the string Windows
        already had and every downstream check sees identical input.
        """
        # The pre-fix reads took cp1252 when os.name was "nt"; the constant is
        # that same Windows branch, now stated for every host.
        windows_branch = "cp1252"
        self.assertEqual(fpga_pll.FIT_ENCODING, windows_branch)
        folder, _ = self.case(True)
        path = folder / "output/design.fit.rpt"
        self.assertEqual(path.read_text(encoding=fpga_pll.FIT_ENCODING),
                         path.read_text(encoding=windows_branch))

    def test_both_families_read_the_report_through_one_stated_fact(self):
        for family in fpga_clocking.IMPLEMENTATIONS:
            with self.subTest(family=family):
                self.assertIs(fpga_clocking.implementation(family).FIT_ENCODING, fpga_clocking.FIT_ENCODING)


# Every module that reads the report, with the number of reads it owns: eight
# reads across seven modules. There is no pending site. `fpga_adc.py` was the
# last reader to decode by host locale and it now states the encoding like the
# rest, so the inventory is exact and a new adopter cannot appear unnoticed.
FIT_REPORT_READERS = {"n2m/fpga_pll.py": 2, "n2m/fpga_pll_cyclonev.py": 1, "n2m/fpga_vga.py": 1,
                      "n2m/fpga_v05.py": 1, "n2m/fpga_intel_memory.py": 1,
                      "n2m/fpga_memory_stores.py": 1, "n2m/fpga_adc.py": 1,
                      "n2m/fpga_uart_cyclonev.py": 1}
TOOLS = Path(__file__).resolve().parents[2]


class FitReportReaderInventoryTests(unittest.TestCase):
    """Every fit-report read states the one encoding, so none can drift back.

    `fpga_intel_memory.py` and `fpga_v05.py` have no folder-level fit fixture and
    no target that fits on a host whose Intel model differs from the reviewed
    one, so this inventory is their proof that they read through the constant.

    Reach, stated exactly so it is not trusted further than it goes: every `.py`
    file under `tools/`, and within those, reads whose own call names the report.
    A read that reaches the file through a variable is invisible here.
    `tools/fpga_netlist_compare.py` is one such reader: it takes the name from
    `SECTIONS`, and it is host-independent already, so nothing is hidden by that
    limit today. A new reader that names the file is caught wherever it lands.
    """

    def readers(self):
        """Each read that names `design.fit.rpt` under `tools/`, with its encoding."""
        found = {}
        for path in sorted(TOOLS.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=path.name)
            for node in ast.walk(tree):
                if (not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute)
                        or node.func.attr != "read_text"):
                    continue
                segment = ast.get_source_segment(source, node) or ""
                if "design.fit.rpt" not in segment:
                    continue
                encoding = [k.value for k in node.keywords if k.arg == "encoding"]
                name = path.relative_to(TOOLS).as_posix()
                found.setdefault(name, []).append(encoding[0] if encoding else None)
        return found

    def test_every_fit_report_read_states_the_one_encoding(self):
        found = self.readers()
        self.assertEqual({name: len(v) for name, v in found.items()}, FIT_REPORT_READERS,
                         "a fit-report read appeared or moved; state its encoding and update this inventory")
        for name, count in FIT_REPORT_READERS.items():
            for index, value in enumerate(found[name]):
                with self.subTest(module=name, read=index):
                    self.assertIsInstance(value, ast.Name, "the read must pass encoding=FIT_ENCODING")
                    self.assertEqual(value.id, "FIT_ENCODING")

    def test_no_fit_report_read_branches_on_the_host(self):
        """The defect's shape, forbidden everywhere."""
        for name, values in self.readers().items():
            for index, value in enumerate(values):
                with self.subTest(module=name, read=index):
                    source = "" if value is None else ast.unparse(value)
                    self.assertNotIn("os.name", source)

    def test_no_fit_report_read_decodes_by_host_locale(self):
        """No read leaves the encoding to the host, so none can drift back."""
        unstated = [name for name, values in self.readers().items() if any(v is None for v in values)]
        self.assertEqual(unstated, [])


if __name__ == "__main__":
    unittest.main()
