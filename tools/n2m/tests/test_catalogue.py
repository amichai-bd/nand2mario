"""Catalogue contract tests: coverage, selection, validation and write-back."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import catalogue as module
from n2m.cli import main

ROOT = Path(__file__).resolve().parents[3]

ENTRY = {"kind": "sim", "level": 1, "labels": ["cpu"], "duration_seconds": None}


def model(units=None, labels=None, not_runnable=None):
    return {"version": 1, "labels": labels or {"cpu": "SM83 core behavior."},
            "units": units if units is not None else {"cpu-alu": dict(ENTRY)},
            "not_runnable": not_runnable or {}}


class YamlSubset(unittest.TestCase):
    def test_reads_block_flow_scalars_and_whole_line_comments(self):
        text = ("# a comment\nversion: 1\nlabels:\n  cpu: \"SM83 core.\"\n"
                "units:\n  cpu-alu: {kind: sim, level: 1, labels: [cpu, fault], duration_seconds: 2.50}\n"
                "  tools/x/test_a.py: {kind: unit, level: 0, labels: [], duration_seconds: null}\n"
                "not_runnable: {}\n")
        self.assertEqual(module.read_yaml(text), {
            "version": 1, "labels": {"cpu": "SM83 core."},
            "units": {"cpu-alu": {"kind": "sim", "level": 1, "labels": ["cpu", "fault"],
                                  "duration_seconds": 2.5},
                      "tools/x/test_a.py": {"kind": "unit", "level": 0, "labels": [],
                                            "duration_seconds": None}},
            "not_runnable": {}})

    def test_block_sequences_true_false_and_single_quotes(self):
        self.assertEqual(module.read_yaml("a:\n  - 1\n  - 'it''s'\nb: true\nc: false\n"),
                         {"a": [1, "it's"], "b": True, "c": False})

    def test_malformed_documents_are_refused(self):
        for text, message in (("a: 1\n\tb: 2\n", "tabs"),
                              ("a: 1\n  b: 2\n", "indentation"),
                              ("a: 1\na: 2\n", "duplicate key"),
                              ("just text\n", "expected 'key: value'"),
                              ("a: [1, 2\n", "unterminated flow"),
                              ("a: {1}\n", "needs a key"),
                              ("a: \"open\n", "unterminated quoted"),
                              ("a:\n  - 1\n  b: 2\n", "sequence and a mapping")):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                module.read_yaml(text)

    def test_format_document_round_trips_through_the_reader(self):
        original = model(units={"cpu-alu": dict(ENTRY, duration_seconds=1.5),
                                "tools/x/test_a.py": {"kind": "unit", "level": 0, "labels": [],
                                                      "duration_seconds": None}},
                         not_runnable={"tools/x/test_b.py": 'a "quoted" reason'})
        self.assertEqual(module.read_yaml(module.format_document(original)), original)


class Validation(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src/dv/builder").mkdir(parents=True)
        (self.root / "src/dv/builder/targets.json").write_text(
            json.dumps({"cpu-alu": {"sources": ["src/rtl/cpu/n2m_cpu.sv"]}}), encoding="utf-8")
        self.write(model())

    def write(self, value):
        (self.root / module.CATALOGUE).write_text(module.format_document(value),
                                                  encoding="utf-8", newline="\n")

    def test_repository_catalogue_is_valid_and_covers_the_tree(self):
        loaded, path = module.load(ROOT)
        self.assertEqual(path, ROOT / module.CATALOGUE)
        self.assertEqual(module.coverage(ROOT, loaded), [])
        self.assertEqual(module.format_document(loaded),
                         path.read_text(encoding="utf-8"),
                         "the catalogue is not in its canonical written form")

    def test_undeclared_label_fails_validation(self):
        self.write(model(units={"cpu-alu": dict(ENTRY, labels=["cpu", "ppu"])}))
        with self.assertRaisesRegex(ValueError, "undeclared label: ppu"):
            module.load(self.root)

    def test_schema_faults_each_fail_with_their_own_message(self):
        for units, message in (
                ({"cpu-alu": {"kind": "peer", "level": 1, "labels": [], "duration_seconds": None}}, "kind must be"),
                ({"cpu-alu": dict(ENTRY, level=3)}, "level must be"),
                ({"cpu-alu": dict(ENTRY, labels=["cpu", "cpu"])}, "labels must be a set"),
                ({"cpu-alu": dict(ENTRY, duration_seconds=-1)}, "duration_seconds must be"),
                ({"Cpu Alu": dict(ENTRY)}, "not a valid sim identifier"),
                ({"tools/n2m/tests/nope.txt": dict(ENTRY, kind="unit")},
                 "not a valid unit identifier")):
            with self.subTest(message=message):
                self.write(model(units=units))
                with self.assertRaisesRegex(ValueError, message):
                    module.load(self.root)
        (self.root / module.CATALOGUE).write_text(
            'version: 1\nlabels:\n  cpu: "c"\nunits:\n  cpu-alu: {kind: sim, level: 1}\n'
            'not_runnable: {}\n', encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ValueError, "requires exactly"):
            module.load(self.root)

    def test_a_test_in_the_tree_but_not_in_the_catalogue_is_a_coverage_failure(self):
        loaded, _ = module.load(self.root)
        self.assertEqual(module.coverage(self.root, loaded), [])
        (self.root / "src/dv/builder/test_new.py").write_text("import unittest\n", encoding="utf-8")
        self.assertEqual(module.coverage(self.root, loaded),
                         [f"test file src/dv/builder/test_new.py is missing from {module.CATALOGUE}"])

    def test_registry_and_catalogue_must_name_the_same_targets(self):
        loaded, _ = module.load(self.root)
        registry = self.root / "src/dv/builder/targets.json"
        registry.write_text(json.dumps({"cpu-alu": {}, "ppu-access": {}}), encoding="utf-8")
        self.assertEqual(module.coverage(self.root, loaded),
                         [f"registry target ppu-access is missing from {module.CATALOGUE}"])
        registry.write_text(json.dumps({}), encoding="utf-8")
        self.assertEqual(module.coverage(self.root, loaded),
                         ["catalogue target cpu-alu is not a registered simulation target"])

    def test_a_test_owned_by_a_registry_target_needs_no_entry_of_its_own(self):
        registry = self.root / "src/dv/builder/targets.json"
        registry.write_text(json.dumps({"cpu-alu": {"sources": [], "python": {
            "inputs": ["src/dv/builder/test_driven.py"]}}}), encoding="utf-8")
        (self.root / "src/dv/builder/test_driven.py").write_text("import cocotb\n", encoding="utf-8")
        loaded, _ = module.load(self.root)
        self.assertEqual(module.coverage(self.root, loaded), [])

    def test_not_runnable_records_a_reason_and_must_name_a_real_file(self):
        self.write(model(not_runnable={"src/dv/builder/test_absent.py": "gone"}))
        loaded, _ = module.load(self.root)
        self.assertEqual(module.coverage(self.root, loaded),
                         ["catalogue entry src/dv/builder/test_absent.py names no file in the tree"])
        self.write(model(not_runnable={"src/dv/builder/test_absent.py": " "}))
        with self.assertRaisesRegex(ValueError, "requires a recorded reason"):
            module.load(self.root)

    def test_generated_output_and_other_checkouts_are_not_the_tree(self):
        for hidden in ("workdir", "worktrees", "__pycache__"):
            (self.root / hidden).mkdir()
            (self.root / hidden / "test_ignored.py").write_text("import unittest\n", encoding="utf-8")
        self.assertNotIn("workdir/test_ignored.py", module.discovered_tests(self.root))
        self.assertEqual(module.discovered_tests(self.root), [])


class Selection(unittest.TestCase):
    def setUp(self):
        self.model = model(
            labels={"cpu": "c", "ppu": "p", "fault": "f", "unused": "u"},
            units={"a": {"kind": "sim", "level": 0, "labels": ["cpu"], "duration_seconds": 1.0},
                   "b": {"kind": "sim", "level": 1, "labels": ["cpu", "fault"], "duration_seconds": None},
                   "c": {"kind": "sim", "level": 2, "labels": ["ppu"], "duration_seconds": 3.0}})

    def test_level_is_ordered_and_includes_everything_below_it(self):
        self.assertEqual(module.select(self.model, 0)[0], ["a"])
        self.assertEqual(module.select(self.model, 1)[0], ["a", "b"])
        self.assertEqual(module.select(self.model, 2)[0], ["a", "b", "c"])

    def test_labels_select_and_compose_with_each_other_and_with_level(self):
        self.assertEqual(module.select(self.model, None, ["cpu"])[0], ["a", "b"])
        self.assertEqual(module.select(self.model, None, ["cpu", "fault"])[0], ["b"])
        self.assertEqual(module.select(self.model, 0, ["cpu"]), (["a"], "--level 0 --label cpu"))

    def test_a_selection_matching_nothing_fails_and_names_the_selector(self):
        with self.assertRaisesRegex(ValueError, r"matched no tests: --level 0 --label fault"):
            module.select(self.model, 0, ["fault"])
        with self.assertRaisesRegex(ValueError, r"nothing carries unused"):
            module.select(self.model, None, ["unused"])

    def test_an_undeclared_selector_label_fails_before_anything_runs(self):
        with self.assertRaisesRegex(ValueError, "unknown label: typo"):
            module.select(self.model, None, ["typo"])

    def test_a_selection_needs_at_least_one_selector(self):
        with self.assertRaisesRegex(ValueError, "requires --level, --label or both"):
            module.select(self.model)


class WriteBack(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "catalogue.yaml"
        self.model = model(units={"a": dict(ENTRY), "b": dict(ENTRY, duration_seconds=9.0)})
        self.path.write_text(module.format_document(self.model), encoding="utf-8", newline="\n")

    def test_a_label_sharing_a_unit_name_is_never_rewritten(self):
        # `vga` and `snapshot` are both registered targets and declared labels.
        self.path.write_text(module.format_document(
            model(labels={"a": "a label whose name is also a unit"},
                  units={"a": dict(ENTRY, labels=["a"])})), encoding="utf-8", newline="\n")
        self.assertEqual(module.record_durations(self.path, {"a": 4.0}), 1)
        written = module.read_yaml(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["labels"]["a"], "a label whose name is also a unit")
        self.assertEqual(written["units"]["a"]["duration_seconds"], 4.0)

    def test_only_the_measured_lines_change_and_comments_survive(self):
        self.assertEqual(module.record_durations(self.path, {"a": 1.25}), 1)
        written = module.read_yaml(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["units"]["a"]["duration_seconds"], 1.25)
        self.assertEqual(written["units"]["b"]["duration_seconds"], 9.0)
        self.assertEqual(written["units"]["a"]["labels"], ["cpu"])
        self.assertIn(module.HEADER.splitlines()[0], self.path.read_text(encoding="utf-8"))
        self.assertEqual(module.record_durations(self.path, {}), 0)


class Contention(unittest.TestCase):
    def test_a_refused_questa_seat_is_contention_and_never_a_defect(self):
        self.assertTrue(module.contended(1, "** Error: License checkout has been disallowed"))
        self.assertTrue(module.contended(module.CONTENTION_EXIT, "anything"))
        self.assertFalse(module.contended(1, "BASELINE_MISMATCH cycle=6"))

    def test_a_contended_simulation_is_skipped_by_name_without_failing(self):
        args = type("Args", (), {"seed": 1, "rebuild": False, "questa_bin": None,
                                 "intel_sim_lib": None})()
        refusal = (1, json.dumps({"status": "FAIL",
                                  "error": "License checkout has been disallowed"}) + "\n")
        with patch("n2m.catalogue.supervise", return_value=refusal):
            outcome = module.run_simulation(ROOT, "tag", "builder-smoke", args, 100)
        self.assertEqual(outcome["status"], "SKIPPED")
        self.assertEqual(outcome["reason"], "questa-contention")

    def test_a_refusal_reaches_the_runner_only_through_the_child_s_log(self):
        """The worker reports `unexpected exit 12; see <path>`, never the text."""
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        log = root / "workdir/builds/t/sim/test/x/attempts/a/sim.log"
        log.parent.mkdir(parents=True)
        log.write_text("** Error: License checkout has been disallowed because\n", encoding="utf-8")
        error = "unexpected exit 12; see workdir\\builds\\t\\sim\\test\\x\\attempts\\a\\sim.log"
        self.assertIn("disallowed", module.referenced_log(root, error))
        self.assertEqual(module.referenced_log(root, "no log here"), "")
        self.assertEqual(module.referenced_log(root, "see ../../outside.log"), "")
        args = type("Args", (), {"seed": 1, "rebuild": False, "questa_bin": None,
                                 "intel_sim_lib": None})()
        with patch("n2m.catalogue.supervise",
                   return_value=(1, json.dumps({"status": "FAIL", "error": error}) + "\n")):
            outcome = module.run_simulation(root, "t", "x", args, 100)
        self.assertEqual((outcome["status"], outcome["reason"]), ("SKIPPED", "questa-contention"))

    def test_a_cached_simulation_reports_its_cache_hit(self):
        args = type("Args", (), {"seed": 1, "rebuild": False, "questa_bin": None,
                                 "intel_sim_lib": None})()
        with patch("n2m.catalogue.supervise",
                   return_value=(0, json.dumps({"status": "PASS", "cache": "CACHED"}) + "\n")):
            outcome = module.run_simulation(ROOT, "tag", "builder-smoke", args, 100)
        self.assertEqual((outcome["status"], outcome["cache"]), ("PASS", "CACHED"))

    def test_a_real_simulation_failure_is_still_a_failure(self):
        args = type("Args", (), {"seed": 1, "rebuild": False, "questa_bin": None,
                                 "intel_sim_lib": None})()
        with patch("n2m.catalogue.supervise",
                   return_value=(1, json.dumps({"status": "FAIL", "error": "signature absent"}) + "\n")):
            outcome = module.run_simulation(ROOT, "tag", "builder-smoke", args, 100)
        self.assertEqual(outcome["status"], "FAIL")
        self.assertEqual(outcome["error"], "signature absent")


class Runner(unittest.TestCase):
    """The public entry points, run against the repository's own catalogue."""

    def run_cli(self, *argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(argv), root=ROOT)
        return code, output.getvalue()

    def test_validate_passes_on_the_repository_and_reports_its_size(self):
        code, text = self.run_cli("tests", "validate", "--json")
        report = json.loads(text)
        self.assertEqual((code, report["status"], report["problems"]), (0, "PASS", []))
        self.assertGreater(report["units"], 500)

    def test_list_selects_and_composes_without_running_anything(self):
        code, text = self.run_cli("tests", "list", "--level", "0", "--json")
        level0 = json.loads(text)
        self.assertEqual((code, level0["status"]), (0, "PASS"))
        code, text = self.run_cli("tests", "list", "--level", "2", "--json")
        self.assertGreater(json.loads(text)["selected"], level0["selected"])
        code, text = self.run_cli("tests", "list", "--level", "0", "--label", "builder", "--json")
        composed = json.loads(text)
        self.assertLess(composed["selected"], level0["selected"])
        self.assertEqual(composed["selector"], "--level 0 --label builder")

    def test_a_zero_selection_exits_non_zero_and_names_the_selector(self):
        code, text = self.run_cli("tests", "list", "--level", "0", "--label", "milestone", "--json")
        self.assertEqual(code, 1)
        self.assertIn("--level 0 --label milestone", json.loads(text)["error"])

    def test_an_unknown_label_exits_non_zero_and_names_it(self):
        code, text = self.run_cli("tests", "list", "--label", "typo", "--json")
        self.assertEqual(code, 1)
        self.assertIn("unknown label: typo", json.loads(text)["error"])

    def test_a_budget_above_the_ordinary_aggregate_must_declare_itself(self):
        arguments = type("Args", (), {"budget": 1200, "broader": False})()
        with self.assertRaisesRegex(ValueError, "--broader"):
            module.budget_for(arguments)
        arguments.broader = True
        self.assertEqual(module.budget_for(arguments), 1200)
        arguments.budget = 5
        with self.assertRaisesRegex(ValueError, "at least 13 seconds"):
            module.budget_for(arguments)

    def test_the_three_migrated_subsets_resolve_through_catalogue_labels(self):
        from n2m.regress import load_subsets
        subsets, _ = load_subsets(ROOT)
        self.assertEqual(sorted(subsets), ["builder-fault", "composed-smoke", "pre-merge"])
        self.assertEqual(subsets["pre-merge"]["targets"], ["builder-smoke", "tile-pixel"])
        self.assertEqual(subsets["builder-fault"]["targets"], ["builder-smoke", "builder-smoke-fail"])
        self.assertEqual(subsets["composed-smoke"]["targets"], ["python-v05-timer"])
        self.assertNotIn("targets", json.loads(
            (ROOT / "src/dv/builder/regressions.json").read_text(encoding="utf-8"))["subsets"]["pre-merge"])


class UnitExecution(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "suite").mkdir()
        shutil.copytree(ROOT / "tools/n2m", self.root / "tools/n2m",
                        ignore=shutil.ignore_patterns("__pycache__", "tests"))

    def write(self, body):
        (self.root / "suite/test_one.py").write_text(body, encoding="utf-8", newline="\n")

    def test_a_unit_runs_in_its_own_directory_and_reports_its_wall(self):
        self.write("import unittest\n\nclass T(unittest.TestCase):\n"
                   "    def test_ok(self):\n        self.assertTrue(True)\n")
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": []})
        self.assertEqual(outcome["status"], "PASS")
        self.assertGreater(outcome["elapsed_seconds"], 0)

    def test_a_failing_unit_fails_and_keeps_its_output(self):
        self.write("import unittest\n\nclass T(unittest.TestCase):\n"
                   "    def test_bad(self):\n        self.fail('deliberate')\n")
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": []})
        self.assertEqual(outcome["status"], "FAIL")
        self.assertIn("deliberate", outcome["output"])

    def test_a_failing_unit_names_the_failing_test_not_its_last_print(self):
        """A unit that prints on stdout must not have that print reported as its failure."""
        self.write("import unittest\n\nclass T(unittest.TestCase):\n"
                   "    def test_bad(self):\n"
                   "        print('a passing diagnostic')\n"
                   "        self.fail('deliberate')\n")
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": []})
        self.assertEqual(outcome["status"], "FAIL")
        self.assertTrue(outcome["error"].startswith("FAIL: test_bad"), outcome["error"])
        self.assertIn("a passing diagnostic", outcome["output"])

    def test_the_builder_packages_are_importable_from_any_unit(self):
        self.write("import unittest\nfrom n2m import catalogue\n\n"
                   "class T(unittest.TestCase):\n"
                   "    def test_import(self):\n        self.assertTrue(catalogue.LEVELS)\n")
        self.assertEqual(module.run_unit(self.root, "suite/test_one.py", {"labels": []})["status"],
                         "PASS")

    def test_a_cocotb_unit_is_skipped_by_name_when_its_interpreter_is_absent(self):
        self.write("import unittest\n")
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": ["needs-cocotb"]})
        self.assertEqual((outcome["status"], outcome["reason"]), ("SKIPPED", "cocotb-environment"))


class UnitErrorTests(unittest.TestCase):
    """The reported line names the failure, whatever the unit printed last."""

    def test_a_failure_header_wins_over_a_trailing_print(self):
        self.assertEqual(module.unit_error("FAIL: test_a (m.T.test_a)\nFAILED (failures=1)\nnoise\n"),
                         "FAIL: test_a (m.T.test_a)")

    def test_an_error_header_is_reported(self):
        self.assertEqual(module.unit_error("ERROR: test_b (m.T.test_b)\nnoise\n"),
                         "ERROR: test_b (m.T.test_b)")

    def test_the_verdict_is_reported_when_no_header_is_present(self):
        self.assertEqual(module.unit_error("boom\nFAILED (errors=1)\ntrailing print\n"),
                         "FAILED (errors=1)")

    def test_the_last_line_remains_the_fallback(self):
        self.assertEqual(module.unit_error("only this\n"), "only this")
        self.assertEqual(module.unit_error(""), "no output")


if __name__ == "__main__":
    unittest.main()
