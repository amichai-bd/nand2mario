"""Independent synthetic netlists challenge the narrow vendor-event classification."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from tools.n2m import fpga_lock, fpga_constraints, fpga, fpga_pll
from tools.n2m.records import file_hash


def fixture():
    # Construct an abstract evidence fixture, not a copied vendor implementation.
    pll, reset = fpga_lock.PLL, fpga_lock.RESET
    cells = []
    def cell(kind, name, **ports):
        cells.append(kind + " \\" + name + " (" + ",".join(f".{p}({v})" for p, v in ports.items()) + ");")
    def param(name, key, value):
        cells.append("defparam \\" + name + f" .{key} = {value};")
    raw, q, release = "\\raw", "\\" + pll + "pll_lock_sync~q", "\\release"
    data = "\\" + pll + "pll_lock_sync~feeder_combout"
    cell("fiftyfivenm_pll", pll + "pll1", locked=raw, areset="!\\reset_buffer")
    cell("dffeas", pll + "pll_lock_sync", clk=raw, d=data, asdata="vcc", clrn="\\reset_buffer",
         aload="gnd", sclr="gnd", sload="gnd", ena="vcc", devclrn="devclrn", devpor="devpor", q=q, prn="vcc")
    param(pll + "pll_lock_sync", "power_up", '"low"')
    cell("fiftyfivenm_lcell_comb", pll + "pll_lock_sync~feeder", dataa="gnd", datab="gnd", datac="gnd", datad="gnd", cin="gnd", combout=data)
    param(pll + "pll_lock_sync~feeder", "lut_mask", "16'hFFFF")
    cell("dffeas", reset + "pll_areset", q=release, clk="\\system_clock")
    cell("fiftyfivenm_clkctrl", reset + "pll_areset~clkctrl", ena="vcc", clkselect="2'b00", inclk="{vcc,vcc,vcc," + release + "}", outclk="\\reset_buffer")
    cell("fiftyfivenm_lcell_comb", reset + "lock_reset~0", dataa=q, datab=release, datac=raw, datad="gnd", cin="gnd", combout="\\lock_gate")
    param(reset + "lock_reset~0", "lut_mask", "16'h7F7F")
    cell("fiftyfivenm_clkctrl", reset + "lock_reset~0clkctrl", ena="vcc", clkselect="2'b00", inclk="{vcc,vcc,vcc,\\lock_gate}", outclk="\\lock_buffer")
    for i in (0, 1):
        cell("dffeas", reset + f"lock_samples[{i}]", clrn="!\\lock_buffer", clk="\\system_clock")
    return "\n".join(cells), "; " + fpga_lock.ROW + "; No clock feeds this register's clock port. ;"


class ClockingEvidenceTests(unittest.TestCase):
    def test_pll_cache_requires_generated_netlist_and_checked_constraints(self):
        with tempfile.TemporaryDirectory() as temporary:
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
                self.assertTrue(fpga.complete_cache(record, "request", root, build, {"pll": {}, "timing": {}}))
                for missing in ("n2m_pixel_pll.v", "simulation/questa/design.vo", "checked.sdc", "output/chain_pix_release_hold.rpt"):
                    truncated = {**record, "artifacts": {k: v for k, v in record["artifacts"].items() if k != (folder / missing).relative_to(root).as_posix()}}
                    (folder / "result.json").write_text(json.dumps(truncated))
                    with self.subTest(missing=missing):
                        self.assertFalse(fpga.complete_cache(truncated, "request", root, build, {"pll": {}, "timing": {}}))
    def test_only_documented_lock_event_is_classified(self):
        text, checks = fixture()
        self.assertEqual(fpga_lock.verify(text, checks)["endpoint"], fpga_lock.ROW)

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
                     text + "\ndffeas bad (.d(func(\\lock_buffer)));",
                     text + "\nassign bad = \\lock_buffer ;"]
        for mutated in mutations:
            with self.subTest(mutated=mutated[-80:]), self.assertRaises(ValueError):
                fpga_lock.verify(mutated, checks)

    def test_extra_or_wrong_no_clock_row_fails(self):
        text, checks = fixture()
        for report in (checks + checks, checks.replace(fpga_lock.ROW, "functional_register"), ""):
            with self.assertRaises(ValueError):
                fpga_lock.verify(text, report)

    def test_checked_constraints_reject_broad_or_executable_endpoints(self):
        for endpoint in ("*|clrn", "cell|q", "cell|clrn;source extra.sdc", "cell|clrn\nsource extra.sdc"):
            with self.assertRaises(ValueError):
                fpga_constraints.validate({"reference_ns": "20.000", "async_reset_pins": [endpoint],
                                           "output_delays": [{"clock": "clk", "ports": ["count[*]"], "count": 8}]})


if __name__ == "__main__":
    unittest.main()
