"""Corruption and artifact checks for the baseline report, not simulated RTL evidence."""
import csv
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import baseline
from n2m.records import file_hash


class BaselineTests(unittest.TestCase):
    def setUp(self):
        base = baseline.ROOT / "workdir/builds/baseline-unit"
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.trace = self.root / "transactions.csv"

    def rows(self):
        return [dict(zip(baseline.FIELDS, (31, index, 0, 0, 0, 0, 0))) for index in range(1, 76)]

    def write_trace(self, rows):
        with self.trace.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, baseline.FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_exact_trace_and_comparison(self):
        rows = self.rows()
        self.write_trace(rows)
        actual = baseline.trace_rows(self.trace, 31, False)
        baseline.compare_traces(rows, actual)
        actual[7]["operand"] = 99
        with self.assertRaisesRegex(ValueError, "backend trace cycle=8 expected=.*actual="):
            baseline.compare_traces(rows, actual)
        with self.assertRaisesRegex(ValueError, "length"):
            baseline.compare_traces(rows, rows[:-1])

    def test_missing_extra_seed_order_and_mismatch(self):
        for mutation in ("missing", "extra", "seed", "cycle", "actual", "operand"):
            rows = self.rows()
            if mutation == "missing": rows.pop()
            elif mutation == "extra": rows.append(rows[-1])
            elif mutation == "operand": rows[0][mutation] = 256
            else: rows[0][mutation] += 1
            self.write_trace(rows)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                baseline.trace_rows(self.trace, 31, False)

    def test_only_intended_broken_transaction_is_accepted(self):
        rows = self.rows()[:6]
        rows[-1]["actual"] = 128
        self.write_trace(rows)
        self.assertEqual(len(baseline.trace_rows(self.trace, 31, True)), 6)
        rows[-1]["actual"] = 129
        self.write_trace(rows)
        with self.assertRaisesRegex(ValueError, "wrong deliberate defect"):
            baseline.trace_rows(self.trace, 31, True)

    def test_malformed_header_and_unknown_values(self):
        self.trace.write_text("cycle,actual\n1,0\n")
        with self.assertRaisesRegex(ValueError, "header"):
            baseline.trace_rows(self.trace, 31, False)
        rows = self.rows(); rows[0]["actual"] = "x"
        self.write_trace(rows)
        with self.assertRaises(ValueError):
            baseline.trace_rows(self.trace, 31, False)

    def test_manifest_cannot_hide_missing_wave_or_wrong_raw_exit(self):
        folder = self.root / "workdir/builds/case"
        folder.mkdir(parents=True)
        self.trace = folder / "transactions.csv"
        self.write_trace(self.rows())
        for name, text in (("baseline.vcd", "wave"), ("sim.log", "pass"), ("bins.txt", "bins=ff")):
            (folder / name).write_text(text)
        manifest = {"status": "PASS", "seed": 31, "commands": [{"exit_code": 0}],
                    "artifacts": {p.relative_to(self.root).as_posix(): file_hash(p) for p in folder.iterdir()}}
        path = folder / "manifest.json"
        path.write_text(json.dumps(manifest))
        baseline.evidence(self.root, "case", 31, False)
        manifest["commands"][0]["exit_code"] = 1
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "raw simulator exit"):
            baseline.evidence(self.root, "case", 31, False)
        manifest["commands"][0]["exit_code"] = 0
        del manifest["artifacts"]["workdir/builds/case/baseline.vcd"]
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "missing nonempty artifact"):
            baseline.evidence(self.root, "case", 31, False)

    def test_budget_overrun_retains_finished_child_and_fails_suite(self):
        plan = self.root / "plan.json"
        data = baseline.load_plan(baseline.MANIFEST)
        data["levels"]["smoke"]["budget_seconds"] = 1
        plan.write_text(json.dumps(data))
        # The child may finish after the budget; its exit/evidence must not turn
        # the over-budget suite into a pass or trigger another child.
        clock = [0.0]
        def child(*args, **kwargs):
            clock[0] = 2.0
            return SimpleNamespace(returncode=0, stdout="finished", stderr="")
        with patch.object(baseline, "ROOT", self.root), patch.object(baseline, "MANIFEST", plan), \
             patch.object(sys, "argv", ["baseline", "--sim", "portable", "--tag", "budget"]), \
             patch.object(baseline.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(baseline.subprocess, "run", side_effect=child) as run, \
             patch.object(baseline, "evidence", return_value=self.rows()):
            self.assertEqual(baseline.main(), 1)
        run.assert_called_once()
        report = json.loads((self.root / "workdir/builds/budget/regression.json").read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["runs"][0]["exit_code"], 0)
        self.assertIn("budget exhausted", report["error"])

    def test_plan_cannot_omit_cases_or_use_empty_invalid_seed_sets(self):
        original = baseline.load_plan(baseline.MANIFEST)
        mutations = [lambda p: p.update(version=True),
                     lambda p: p.update(targets=["baseline-good"]),
                     lambda p: p["levels"]["smoke"].update(seeds=[]),
                     lambda p: p["levels"]["smoke"].update(seeds=[1, 1]),
                     lambda p: p["levels"]["smoke"].update(seeds=[True]),
                     lambda p: p["levels"]["smoke"].update(seeds=[2147483648]),
                     lambda p: p["levels"]["smoke"].update(budget_seconds=0)]
        path = self.root / "plan.json"
        for mutate in mutations:
            data = copy.deepcopy(original)
            mutate(data)
            path.write_text(json.dumps(data))
            with self.subTest(mutation=mutations.index(mutate)), self.assertRaises(ValueError):
                baseline.load_plan(path)


if __name__ == "__main__":
    unittest.main()
