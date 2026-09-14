"""Unit tests for the FPGA netlist identity compare over synthetic build trees."""
import json
from pathlib import Path
import tempfile
import unittest

import fpga_netlist_compare as compare

SUMMARY = "Fitter Status : Successful - Tue Sep 15 00:10:44 2026\nDevice : 10M50DAF484C7G\nTotal PLLs : 1 / 4 ( 25 % )\n"


def table(title, rows):
    lines = [f"; {title} ;", "+---+---+", "; Compilation Hierarchy Node ; Logic Cells ;", "+---+---+"]
    lines += [f"; {name} ; {cells} ;" for name, cells in rows]
    lines += ["+---+---+", ""]
    return "\n".join(lines)


def map_report(rows):
    return table("Analysis & Synthesis Resource Usage Summary", [("Total logic elements", "12")]) + \
        table("Analysis & Synthesis Resource Utilization by Entity", rows)


def fit_report(rows):
    return table("Fitter Resource Usage Summary", [("Total logic elements", "12")]) + \
        table("Fitter Resource Utilization by Entity", rows)


class SyntheticTree:
    def __init__(self, root, tag, definitions):
        self.root, self.tag = Path(root), tag
        (self.root / "src/fpga/de10_lite").mkdir(parents=True)
        (self.root / "src/fpga/de10_lite/targets.json").write_text(json.dumps({"targets": definitions}))

    def build(self, target, *, status="PASS", rows=(("|top", "12 (12)"),), reports=True, netlist="cell a;\n", error=""):
        attempt = self.root / "workdir/builds" / self.tag / "fpga" / target / "attempts/abc123"
        (attempt / "output").mkdir(parents=True)
        record = {"status": status, "attempt_result": (attempt / "result.json").relative_to(self.root).as_posix(),
                  "evidence_directory": attempt.relative_to(self.root).as_posix(), "error": error}
        if reports:
            (attempt / "output/design.fit.summary").write_text(SUMMARY)
            (attempt / "output/design.map.rpt").write_text(map_report(list(rows)))
            (attempt / "output/design.fit.rpt").write_text(fit_report(list(rows)))
        if netlist is not None:
            (attempt / "simulation/questa").mkdir(parents=True)
            (attempt / "simulation/questa/design.vo").write_text("// generated Tue\n\n" + netlist)
        (self.root / "workdir/builds" / self.tag / "fpga" / target / "result.json").write_text(json.dumps(record))


class NetlistCompareTests(unittest.TestCase):
    definitions = {"plain": {"sources": ["src/dv/builder/fpga_smoke.sv"]},
                   "memory": {"sources": ["src/rtl/common/n2m_intel_ram.sv"]},
                   "clocked": {"sources": ["src/x.sv"], "pll": {"module": "n2m_pixel_pll"}}}

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.baseline = SyntheticTree(base / "baseline", "b", self.definitions)
        self.head = SyntheticTree(base / "head", "h", self.definitions)

    def tearDown(self):
        self.temporary.cleanup()

    def run_compare(self):
        return compare.compare(self.baseline.root, "b", self.head.root, "h")

    def test_identical_trees_pass_and_record_compared_fields(self):
        for tree in (self.baseline, self.head):
            tree.build("plain", netlist=None)
            tree.build("memory")
            tree.build("clocked", netlist="cell b;\n")
        report = self.run_compare()
        self.assertEqual(report["status"], "PASS")
        self.assertIn("netlist_sha256", report["targets"]["memory"]["compared_fields"])
        self.assertIn("fit_entity_rows", report["targets"]["plain"]["compared_fields"])

    def test_missing_report_fails_a_pass_record(self):
        self.baseline.build("plain", netlist=None)
        self.head.build("plain", netlist=None, reports=False)
        self.baseline.build("memory"); self.head.build("memory")
        self.baseline.build("clocked"); self.head.build("clocked")
        report = self.run_compare()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["targets"]["plain"]["status"], "FAIL")
        self.assertIn("missing report design.fit.summary", report["targets"]["plain"]["reason"])

    def test_missing_netlist_fails_targets_that_retain_one(self):
        self.baseline.build("plain", netlist=None); self.head.build("plain", netlist=None)
        self.baseline.build("memory"); self.head.build("memory", netlist=None)
        self.baseline.build("clocked"); self.head.build("clocked", netlist=None)
        report = self.run_compare()
        self.assertEqual(report["targets"]["memory"]["status"], "FAIL")
        self.assertIn("missing post-fit netlist", report["targets"]["memory"]["reason"])
        self.assertEqual(report["targets"]["clocked"]["status"], "FAIL")

    def test_hierarchy_row_and_netlist_mismatches_fail(self):
        self.baseline.build("plain", netlist=None); self.head.build("plain", netlist=None, rows=(("|top", "13 (13)"),))
        self.baseline.build("memory"); self.head.build("memory", netlist="cell c;\n")
        self.baseline.build("clocked"); self.head.build("clocked")
        report = self.run_compare()
        self.assertEqual(report["targets"]["plain"]["status"], "FAIL")
        self.assertEqual(report["targets"]["plain"]["field"], "map_entity_rows")
        self.assertEqual(report["targets"]["memory"]["status"], "FAIL")
        self.assertEqual(report["targets"]["memory"]["field"], "netlist_sha256")
        self.assertEqual(report["targets"]["clocked"]["status"], "PASS")

    def test_identical_deliberate_failures_pass(self):
        for tree in (self.baseline, self.head):
            tree.build("plain", status="FAIL", reports=False, netlist=None, error="negative clock period")
            tree.build("memory"); tree.build("clocked")
        report = self.run_compare()
        self.assertEqual(report["targets"]["plain"]["status"], "PASS")
        self.assertIn("deliberate", report["targets"]["plain"]["note"])

    def test_summary_rows_strip_timestamp(self):
        self.assertEqual(compare.summary_rows(SUMMARY)[0], "Fitter Status : Successful")


if __name__ == "__main__":
    unittest.main()
