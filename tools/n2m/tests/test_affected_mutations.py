"""Recorded mutations select their detectors: the conservativeness proof of `tests affected`.

The closure of this module is the whole tree, like test_catalogue.py, so it
stays undeclared in the catalogue.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import affected, catalogue, host_closure, mutations

closures = affected.closures

ROOT = Path(__file__).resolve().parents[3]


class RepositoryProof(unittest.TestCase):
    """Every recorded detector is selected on the real tree, and a dropped declaration is a miss by name."""

    @classmethod
    def setUpClass(cls):
        cls.model, _ = catalogue.load(ROOT)
        cls.marker, cls.rows = mutations.load(ROOT, cls.model)
        cls.known = affected.closures(ROOT, cls.model)

    def test_manifest_covers_every_kind_with_valid_rows(self):
        self.assertEqual({row["kind"] for row in self.rows}, set(mutations.KINDS))
        for row in self.rows:
            with self.subTest(mutation=row["name"]):
                self.assertTrue((ROOT / row["path"]).is_file())
                for detector in row["detectors"]:
                    self.assertIn(detector, self.model["units"])

    def test_every_recorded_detector_is_selected(self):
        self.assertEqual(mutations.misses(ROOT, self.model, self.rows, self.known), [])

    def test_only_the_recorded_detectors_are_decided(self):
        row = next(r for r in self.rows if r["kind"] == "data")
        _, units = mutations.selection(ROOT, self.model, self.known, row["path"], set(row["detectors"]))
        self.assertEqual(set(units), set(row["detectors"]))
        for detector in row["detectors"]:
            self.assertEqual(units[detector]["reasons"], ["changed inputs: " + row["path"]])

    def test_removing_a_declared_input_is_a_miss_naming_the_unit_and_path(self):
        unit = "tools/n2m/tests/test_baseline.py"
        row = next(r for r in self.rows if r["path"] == "src/dv/baseline/regression.json")
        self.assertIn(unit, row["detectors"])
        entry = copy.deepcopy(self.model["units"][unit])
        entry["inputs"] = [p for p in entry["inputs"] if p != "src/dv/baseline"]
        inputs, errors = self.known
        narrowed = dict(inputs)
        narrowed[unit] = host_closure.closure(ROOT, unit, entry, self.model["external_imports"], {},
                                              lambda d: affected.tracked_files(ROOT, d))
        found = mutations.misses(ROOT, self.model, [row], (narrowed, errors))
        self.assertEqual(found, [f"mutation {row['name']}: unit {unit} not selected for {row['path']} "
                                 "(validated declared host closure equal base)"])

    def test_real_report_on_a_mutated_clone_equals_the_in_process_decision(self):
        """`tests affected` and the proof share decide(): the same mutation, applied for real, agrees.

        An RTL change decides most simulations by their changed inputs; a data
        change leaves them undecided and validates each one, so both kinds run."""
        for kind in ("rtl", "data"):
            with self.subTest(kind=kind):
                self.real_report_equals_decision(next(r for r in self.rows if r["kind"] == kind))

    def real_report_equals_decision(self, row):
        base = ROOT / "workdir/builds/affected-mutation-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="clone ", dir=base) as temp:
            clone = mutations.clone(ROOT, Path(temp) / "tree")
            head = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"], text=True).strip()
            mutations.mutate(clone, row, self.marker)
            model, _ = catalogue.load(clone)
            derived = []
            # Capture the closures the report derives, so the in-process decision starts from the same ones.
            with patch.object(affected, "closures", side_effect=lambda *a: derived.append(closures(*a)) or derived[-1]):
                report = affected.report(clone, head)
            _, expected = mutations.selection(clone, model, derived[0], row["path"])
        self.assertEqual([c["path"] for c in report["changes"]], [row["path"]])
        self.assertEqual(report["fallback"], [])
        strip = lambda units: {n: {k: v for k, v in r.items() if k != "inputs"} for n, r in units.items()}
        self.assertEqual(strip(report["units"]), strip(expected))
        for detector in row["detectors"]:
            self.assertEqual(report["units"][detector]["decision"], "selected")
        self.assertIn("advisory only", report["scope"])
        self.assertTrue(report["required_checks"].startswith("unchanged"))


class Manifest(unittest.TestCase):
    """The manifest schema fails by row, so a record can never be silently ignored."""

    def setUp(self):
        base = ROOT / "workdir/builds/affected-mutation-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="manifest ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("src/x/data.json", '{"value": 1}\n')
        self.write("src/x/module.sv", "module m; endmodule\n")
        git = lambda *a: subprocess.check_output(["git", "-C", str(self.root), *a], stderr=subprocess.PIPE)
        git("init", "-q")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        git("add", "src/x/data.json", "src/x/module.sv")
        git("commit", "-qm", "fixture")
        self.write("src/x/untracked.json", "{}\n")
        self.model = {"units": {"unit-a": {"kind": "sim"}, "tools/test_b.py": {"kind": "unit"}}}
        self.row = {"name": "data", "kind": "data", "path": "src/x/data.json", "mutation": "append",
                    "detectors": ["unit-a"], "evidence": "confirmed"}

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def manifest(self, *rows, **overrides):
        document = {"version": 1, "marker": "@@@X@@@", "mutations": list(rows), **overrides}
        self.write(mutations.MANIFEST, json.dumps(document))

    def test_a_valid_manifest_loads_with_its_marker(self):
        replace = {**self.row, "name": "sv", "kind": "rtl", "path": "src/x/module.sv",
                   "mutation": {"replace": ["endmodule", "endmodul"]}, "detectors": ["tools/test_b.py"]}
        self.manifest(self.row, replace)
        marker, rows = mutations.load(self.root, self.model)
        self.assertEqual(marker, "@@@X@@@")
        self.assertEqual([r["name"] for r in rows], ["data", "sv"])

    def test_each_schema_fault_fails_naming_the_row(self):
        faults = [({"kind": "asset"}, "kind must be one of"),
                  ({"path": "src/x/missing.json"}, "not a tracked file"),
                  ({"path": "src/x/untracked.json"}, "not a tracked file"),
                  ({"mutation": "truncate"}, 'must be "append" or'),
                  ({"mutation": {"replace": ["absent", "x"]}}, "does not contain"),
                  ({"mutation": {"replace": ["value", "value"]}}, 'must be "append" or'),
                  ({"detectors": []}, "at least one detecting unit"),
                  ({"detectors": ["unit-z"]}, "not a catalogue unit: unit-z"),
                  ({"evidence": " "}, "record its detection evidence")]
        for change, message in faults:
            with self.subTest(fault=change):
                self.manifest({**self.row, **change})
                with self.assertRaisesRegex(ValueError, message):
                    mutations.load(self.root, self.model)
        self.manifest(self.row, self.row)
        with self.assertRaisesRegex(ValueError, "names must be unique"):
            mutations.load(self.root, self.model)
        self.manifest()
        with self.assertRaisesRegex(ValueError, "at least one mutation"):
            mutations.load(self.root, self.model)

    def test_a_faulty_manifest_is_a_catalogue_coverage_failure(self):
        with patch.object(mutations, "load", side_effect=ValueError("mutation x detector is not a catalogue unit: y")):
            problems = catalogue.coverage(ROOT, catalogue.load(ROOT)[0])
        self.assertEqual(problems, [f"{mutations.MANIFEST}: mutation x detector is not a catalogue unit: y"])

    def test_mutate_appends_the_marker_or_replaces_once(self):
        mutations.mutate(self.root, self.row, "@@@X@@@")
        self.assertEqual((self.root / "src/x/data.json").read_text(encoding="utf-8"), '{"value": 1}\n\n@@@X@@@\n')
        row = {**self.row, "path": "src/x/module.sv", "mutation": {"replace": ["module m", "modul m"]}}
        mutations.mutate(self.root, row, "@@@X@@@")
        self.assertEqual((self.root / "src/x/module.sv").read_text(encoding="utf-8"), "modul m; endmodule\n")
        with self.assertRaisesRegex(ValueError, "does not contain"):
            mutations.mutate(self.root, row, "@@@X@@@")


if __name__ == "__main__":
    unittest.main()
