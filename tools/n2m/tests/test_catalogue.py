"""Catalogue contract tests: coverage, selection, validation and deliberate recording."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import catalogue as module
from n2m import cpu_budget
from n2m.cli import main

ROOT = Path(__file__).resolve().parents[3]

# A cheap declared host unit, for the closure-trace command test.
TRACED_UNIT = "tools/n2m/tests/test_fpga_hold.py"

ENTRY = {"kind": "sim", "level": 1, "labels": ["cpu"], "duration_seconds": None}
# A host unit nothing has measured, so its budget is the default rather than a multiple.
UNMEASURED = {"labels": [], "duration_seconds": None}
# Spends its own CPU until it has spent that much, however fast or busy the host is.
BURN = ("import time, unittest\n\nclass T(unittest.TestCase):\n"
        "    def test_burn(self):\n"
        "        deadline = time.process_time() + {0}\n"
        "        while time.process_time() < deadline:\n            pass\n")
# Spends wall and no CPU, the way a unit waiting for a core does.
WAIT = ("import time, unittest\n\nclass T(unittest.TestCase):\n"
        "    def test_wait(self):\n        time.sleep({0})\n")

# Skipped, never degraded, where the OS reports no per-child CPU: a test that tolerates
# `cpu_seconds` being None passes just as well when the reaping hook has stopped working.
measures_cpu = unittest.skipUnless(hasattr(module.os, "wait4"), "no per-child CPU time here")
# One sitting's conditions, in the form `tests record` writes them.
MEASURED = {"at": "2026-09-20T14:29Z", "commit": "f70fb078b67b", "host": "Linux-x86_64",
            "wall_cpu": 1.03}


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
                                "cpu-flags": dict(ENTRY, duration_seconds=17.61, measured=MEASURED),
                                "cpu-halt": dict(ENTRY, duration_seconds=0.5,
                                                 measured=dict(MEASURED, wall_cpu=None)),
                                "tools/x/test_a.py": {"kind": "unit", "level": 0, "labels": [],
                                                      "duration_seconds": None}},
                         not_runnable={"tools/x/test_b.py": 'a "quoted" reason'})
        self.assertEqual(module.read_yaml(module.format_document(original)), original)
        self.assertIn('measured: {at: "2026-09-20T14:29Z", commit: "f70fb078b67b", '
                      'host: "Linux-x86_64", wall_cpu: 1.03}',
                      module.format_document(original))


class Validation(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src/dv/builder").mkdir(parents=True)
        (self.root / "src/dv/builder/targets.json").write_text(
            json.dumps({"cpu-alu": {"sources": ["src/rtl/cpu/n2m_cpu.sv"], "simulators": ["verilator"]}}), encoding="utf-8")
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

    def test_host_inputs_and_external_imports_round_trip_and_are_validated(self):
        unit = {"kind": "unit", "level": 0, "labels": [], "duration_seconds": None, "inputs": ["src/dv/builder", ".github/x.yml"]}
        document = model(units={"cpu-alu": dict(ENTRY), "src/dv/builder/test_a.py": unit}) | {
            "external_imports": {"serial": "tools/n2m/host/THIRD_PARTY.md records pySerial 3.5."}}
        self.write(document)
        (self.root / "src/dv/builder/test_a.py").write_text("import unittest\n", encoding="utf-8")
        (self.root / ".github").mkdir()
        (self.root / ".github/x.yml").write_text("", encoding="utf-8")
        loaded, path = module.load(self.root)
        self.assertEqual(loaded["external_imports"], document["external_imports"])
        # The formatter writes the declaration sorted, so a rebase onto another author's row stays mechanical.
        self.assertEqual(loaded["units"]["src/dv/builder/test_a.py"]["inputs"], sorted(unit["inputs"]))
        self.assertEqual(module.read_yaml(module.format_document(loaded)),
                         {key: value for key, value in loaded.items() if key != "retired"})
        self.assertIn("inputs: [.github/x.yml, src/dv/builder]", path.read_text(encoding="utf-8"))
        self.assertEqual(module.coverage(self.root, loaded), [])
        # The duration write-back keeps the declaration.
        module.record_durations(path, {"src/dv/builder/test_a.py": 0.5})
        self.assertEqual(module.load(self.root)[0]["units"]["src/dv/builder/test_a.py"]["inputs"], sorted(unit["inputs"]))
        for units, extra, message in (
                ({"cpu-alu": dict(ENTRY, inputs=[])}, {}, "its inputs live in targets.json"),
                ({"src/dv/builder/test_a.py": dict(unit, inputs=["src", "src"])}, {}, "inputs must be a set"),
                ({"src/dv/builder/test_a.py": dict(unit, inputs=["../x"])}, {}, "not a repository-relative path"),
                ({"src/dv/builder/test_a.py": dict(unit, inputs=["src/"])}, {}, "not a repository-relative path"),
                ({"src/dv/builder/test_a.py": dict(unit, inputs=["/etc/passwd"])}, {}, "not a repository-relative path"),
                ({"cpu-alu": dict(ENTRY)}, {"external_imports": {"serial": " "}}, "requires a recorded provenance"),
                ({"cpu-alu": dict(ENTRY)}, {"external_imports": {"not-a-module": "x"}}, "requires a recorded provenance")):
            with self.subTest(message=message):
                self.write(model(units=units) | extra)
                with self.assertRaisesRegex(ValueError, message):
                    module.load(self.root)
        # Shapes the canonical formatter cannot write are still refused when read.
        for text, message in (('version: 1\nlabels:\n  cpu: "c"\nexternal_imports:\n  - serial\nunits:\n'
                               '  cpu-alu: {kind: sim, level: 1, labels: [], duration_seconds: null}\nnot_runnable: {}\n',
                               "must be a mapping"),
                              ('version: 1\nlabels:\n  cpu: "c"\nunits:\n  src/dv/builder/test_a.py: '
                               '{kind: unit, level: 0, labels: [], duration_seconds: null, inputs: src}\nnot_runnable: {}\n',
                               "inputs must be a set")):
            with self.subTest(message=message):
                (self.root / module.CATALOGUE).write_text(text, encoding="utf-8", newline="\n")
                with self.assertRaisesRegex(ValueError, message):
                    module.load(self.root)

    def test_coverage_rejects_an_undeclared_import_and_an_inconsistent_declaration(self):
        (self.root / "src/dv/builder/test_a.py").write_text(
            "from pathlib import Path\nimport helper\nDATA = Path(__file__).with_name('data.json')\n", encoding="utf-8")
        (self.root / "src/dv/builder/helper.py").write_text("import serial\n", encoding="utf-8")
        (self.root / "src/dv/builder/data.json").write_text("{}", encoding="utf-8")
        unit = {"kind": "unit", "level": 0, "labels": [], "duration_seconds": None}
        self.write(model(units={"cpu-alu": dict(ENTRY), "src/dv/builder/test_a.py": unit}))
        loaded, _ = module.load(self.root)
        self.assertEqual(module.coverage(self.root, loaded), [
            "unit src/dv/builder/test_a.py: undeclared import serial at line 1 of src/dv/builder/helper.py"])
        self.write(model(units={"cpu-alu": dict(ENTRY), "src/dv/builder/test_a.py": dict(unit, inputs=[])})
                   | {"external_imports": {"serial": "pySerial 3.5"}})
        loaded, _ = module.load(self.root)
        self.assertEqual(module.coverage(self.root, loaded), [
            "unit src/dv/builder/test_a.py references an undeclared input: src/dv/builder/data.json"])
        self.write(model(units={"cpu-alu": dict(ENTRY), "src/dv/builder/test_a.py": dict(unit, inputs=["src/dv/builder/data.json"])})
                   | {"external_imports": {"serial": "pySerial 3.5"}})
        loaded, _ = module.load(self.root)
        self.assertEqual(module.coverage(self.root, loaded), [])

    def test_a_preload_targets_fixture_inputs_are_a_coverage_check(self):
        """Either testbench kind fails coverage by name when it would refuse to run."""
        self.write(model())
        loaded, _ = module.load(self.root)
        self.assertEqual(module.coverage(self.root, loaded), [])

        registry = self.root / "src/dv/builder/targets.json"
        registry.write_text(json.dumps({"cpu-alu": {"sources": [], "simulators": ["verilator"],
                                                    "preload": "menu", "preload_inputs": ["src/dv/builder/targets.json"]}}),
                            encoding="utf-8")

        def refuse(root, target, name=None, cache=None):
            raise ValueError(f"{name}: preload_inputs omit fixture inputs: src/sw/menu/assets/design/x.json")

        with patch("n2m.python_tb.validate_fixture", refuse):
            self.assertEqual(module.coverage(self.root, loaded),
                             ["registry cpu-alu: preload_inputs omit fixture inputs: "
                              "src/sw/menu/assets/design/x.json"])
        # A Python testbench carries the same fixture inputs in python.inputs.
        registry.write_text(json.dumps({"cpu-alu": {"sources": [], "simulators": ["verilator"],
                                                    "testbench": "python", "preload": "menu",
                                                    "python": {"module": "probe", "test": "run",
                                                               "inputs": ["src/sw/menu/main.asm"]}}}),
                            encoding="utf-8")
        with patch("n2m.python_tb.fixture_inputs",
                   lambda root, preload: {"src/sw/menu/main.asm", "src/sw/menu/assets/design/x.json"}):
            self.assertEqual(module.coverage(self.root, loaded),
                             ["registry cpu-alu: python inputs omit fixture inputs: "
                              "src/sw/menu/assets/design/x.json"])

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
                 "not a valid unit identifier"),
                # A wall is only usable with the sitting behind it, so the
                # conditions are validated as strictly as the wall.
                ({"cpu-alu": dict(ENTRY, measured=MEASURED)},
                 "measured conditions without a duration_seconds"),
                ({"cpu-alu": dict(ENTRY, duration_seconds=1.0, measured=dict(MEASURED, at="2026-09-20"))},
                 "measured at must be a UTC minute"),
                ({"cpu-alu": dict(ENTRY, duration_seconds=1.0, measured=dict(MEASURED, host="two words"))},
                 "measured host must be a single token"),
                ({"cpu-alu": dict(ENTRY, duration_seconds=1.0, measured=dict(MEASURED, wall_cpu=0))},
                 "measured wall_cpu must be null or a positive ratio")):
            with self.subTest(message=message):
                self.write(model(units=units))
                with self.assertRaisesRegex(ValueError, message):
                    module.load(self.root)
        # Shapes the canonical formatter cannot write are still refused when read.
        for entry, message in (("{kind: sim, level: 1}", "requires exactly"),
                               ("{kind: sim, level: 1, labels: [], duration_seconds: 1.0, "
                                'measured: {at: "2026-09-20T14:29Z", commit: "abcdef123456"}}',
                                "measured requires exactly at, commit, host, wall_cpu"),
                               ("{kind: sim, level: 1, labels: [], duration_seconds: 1.0, measured: null}",
                                "measured requires exactly at, commit, host, wall_cpu"),
                               ("{kind: sim, level: 1, labels: [], duration_seconds: 1.0, "
                                'measured: {at: "2026-09-20T14:29Z", commit: "abcdef123456", '
                                'host: "Linux-x86_64", wall_cpu: 1.0, build: 2.0}}',
                                "measured build must be a share of its own wall")):
            with self.subTest(entry=entry):
                (self.root / module.CATALOGUE).write_text(
                    'version: 1\nlabels:\n  cpu: "c"\nunits:\n  cpu-alu: ' + entry + '\n'
                    'not_runnable: {}\n', encoding="utf-8", newline="\n")
                with self.assertRaisesRegex(ValueError, message):
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
        registry.write_text(json.dumps({"cpu-alu": {"simulators": ["questa"]}, "ppu-access": {"simulators": ["verilator"]}}), encoding="utf-8")
        self.assertEqual(module.coverage(self.root, loaded),
                         [f"registry target ppu-access is missing from {module.CATALOGUE}"])
        registry.write_text(json.dumps({}), encoding="utf-8")
        self.assertEqual(module.coverage(self.root, loaded),
                         ["catalogue target cpu-alu is not a registered simulation target"])

    def test_a_test_owned_by_a_registry_target_needs_no_entry_of_its_own(self):
        registry = self.root / "src/dv/builder/targets.json"
        registry.write_text(json.dumps({"cpu-alu": {"sources": [], "simulators": ["verilator"], "python": {
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

    def test_retired_names_a_reason_and_may_not_stay_registered_or_catalogued(self):
        reason = "A two-state simulator cannot witness X."
        self.write(model(units={"cpu-alu": dict(ENTRY)}) | {"retired": {"ppu-shift-unknown": reason}})
        loaded, _ = module.load(self.root)
        self.assertEqual(loaded["retired"], {"ppu-shift-unknown": reason})
        self.assertEqual(module.coverage(self.root, loaded), [])
        self.assertIn("retired:\n  ppu-shift-unknown:", module.format_document(loaded))
        self.write(model(units={"tools/x/test_a.py": {"kind": "unit", "level": 0, "labels": [],
                                                      "duration_seconds": None}})
                   | {"retired": {"cpu-alu": reason}})
        loaded, _ = module.load(self.root)
        self.assertIn("retired target cpu-alu is still registered in targets.json",
                      module.coverage(self.root, loaded))
        self.write(model() | {"retired": {"cpu-alu": " "}})
        with self.assertRaisesRegex(ValueError, "requires a recorded reason"):
            module.load(self.root)
        self.write(model(units={"cpu-alu": dict(ENTRY)}) | {"retired": {"cpu-alu": reason}})
        with self.assertRaisesRegex(ValueError, "both a unit and retired"):
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


class Recording(unittest.TestCase):
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

    def test_a_measured_wall_is_never_recorded_as_zero(self):
        # 0.00 is reserved for an entry nothing measured, so validate can flag it.
        self.assertEqual(module.measured_duration(0.0001), 0.01)
        self.assertEqual(module.measured_duration(1.2345), 1.23)

    def test_conditions_are_replaced_with_the_wall_they_describe(self):
        """Conditions describe one wall, so a new wall never keeps the old ones."""
        self.assertEqual(module.record_durations(self.path, {"a": 4.0}, {"a": MEASURED}), 1)
        self.assertEqual(module.read_yaml(self.path.read_text(encoding="utf-8"))["units"]["a"],
                         dict(ENTRY, duration_seconds=4.0, measured=MEASURED))
        self.assertEqual(module.record_durations(self.path, {"a": 5.0}), 1)
        self.assertEqual(module.read_yaml(self.path.read_text(encoding="utf-8"))["units"]["a"],
                         dict(ENTRY, duration_seconds=5.0))

    def build(self, tag, relative, record):
        """Write one retained run record under a build tag, as a run publishes it."""
        root = Path(self.temp.name)
        (root / "src/dv/builder").mkdir(parents=True, exist_ok=True)
        (root / module.CATALOGUE).write_text(module.format_document(self.model),
                                             encoding="utf-8", newline="\n")
        destination = root / "workdir/builds" / tag / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(record), encoding="utf-8")
        return root

    def entries(self, root):
        return module.read_yaml((root / module.CATALOGUE).read_text(encoding="utf-8"))["units"]

    def test_a_retained_sim_test_is_recorded_only_when_asked_and_carries_its_sitting(self):
        passed = {"status": "PASS", "cache": "BUILT", "requested": {"target": "a"},
                  "timing": {"locked_seconds": 74.567, "locked_cpu_seconds": 72.4,
                             "build_seconds": 70.1},
                  "finished": "2026-09-20T14:29:07.101010+00:00",
                  "commit": "f70fb078b67bd8fd4675baafa3ac414f8e28cdf1", "os": "Linux"}
        root = self.build("smoke", "manifest.json", passed)
        report = module.record_from_run(root, "smoke")
        self.assertEqual((report["status"], report["durations_written"]), ("PASS", 1))
        recorded = self.entries(root)["a"]
        self.assertEqual(recorded["duration_seconds"], 74.57)
        # The sitting travels with the wall: its UTC minute, the commit it
        # measured, the host family and how much of its wall was work. A
        # simulation's wall is nearly all compile, so the compile travels with
        # it and the next reader can see what the figure paid for.
        self.assertEqual(recorded["measured"], {"at": "2026-09-20T14:29Z",
                                                "commit": "f70fb078b67b",
                                                "host": "Linux-" + platform.machine(),
                                                "wall_cpu": 1.03, "build": 70.1})
        self.assertEqual(self.entries(root)["b"]["duration_seconds"], 9.0)
        # A cache hit times the cache check, a failure has no trustworthy wall,
        # and a target outside the catalogue has nowhere to record one.
        for record, reason in (({**passed, "cache": "CACHED"}, "no wall"),
                               ({**passed, "status": "FAIL"}, "no wall"),
                               ({**passed, "timing": {}}, "no wall"),
                               ({**passed, "requested": {"target": "absent"}}, "not a unit")):
            with self.subTest(reason=reason):
                root = self.build("smoke", "manifest.json", record)
                report = module.record_from_run(root, "smoke")
                self.assertEqual(report["durations_written"], 0)
                self.assertIsNone(self.entries(root)["a"]["duration_seconds"])

    def test_no_measured_wall_is_refused_for_the_state_of_the_host(self):
        """The ratio is recorded and never judged. No measurement here separates
        a busy sitting from a quiet one: four spinners moved a wall 1.96x and its
        CPU 1.30x, a simulation's parallel compile sits below 1 whatever the
        load, and a unit that sleeps sits at 3.76 while computing nothing. So a
        wall is refused only when it describes no work, and the operator reads
        the conditions rather than a verdict."""
        for wall, cpu, ratio in ((60.0, 20.0, 3.0),     # a unit that waits or sleeps
                                 (15.57, 43.0, 0.36),   # a simulation compiling in parallel
                                 (0.18, 0.08, 2.25)):   # a wall too short for the ratio to mean much
            with self.subTest(wall=wall):
                record = {"status": "PASS", "measured_walls": {"a": {"wall": wall, "cpu": cpu}},
                          "finished": "2026-09-20T14:29:07+00:00", "commit": "abcdef123456",
                          "os": "Linux"}
                root = self.build("selection", "tests/summary.json", record)
                report = module.record_from_run(root, "selection")
                self.assertEqual((report["durations_written"], report["not_recorded"]), (1, {}))
                self.assertEqual(self.entries(root)["a"]["duration_seconds"], round(wall, 2))
                self.assertEqual(self.entries(root)["a"]["measured"]["wall_cpu"], ratio)

    def test_a_recording_names_the_figure_it_replaced(self):
        """A recording that writes 195 s over 26 without a word is the silence
        this command exists to end, so every write says what it replaced."""
        from n2m.cli import recorded_lines
        record = {"status": "PASS", "commit": "abcdef123456", "os": "Linux",
                  "finished": "2026-09-20T14:29:07+00:00",
                  "measured_walls": {"a": {"wall": 17.97, "cpu": 49.9, "build": 17.62},
                                     "b": {"wall": 9.6, "cpu": 9.5}}}
        root = self.build("selection", "tests/summary.json", record)
        report = module.record_from_run(root, "selection")
        # `a` has no recorded wall at all; `b` records 9.0, which 9.6 is close to.
        self.assertEqual(report["drift"], ["a"])
        self.assertEqual(recorded_lines(report), [
            "Recorded DRIFT a 17.97s against no recorded wall, wall/CPU 0.36, 17.62s of it compile",
            "Recorded b 9.60s against 9.00s recorded, 1.1x higher, wall/CPU 1.01"])
        # A wall that shrank is named by its own multiple, never as 0.0x.
        report["recorded"]["b"].update(seconds=0.18, was=48.2)
        self.assertIn("0.18s against 48.20s recorded, 267.8x lower", recorded_lines(report)[1])

    def test_a_wall_far_from_the_recorded_figure_is_named_rather_than_written(self):
        """The gaps that matter here are whole multiples: 0.41 recorded against a
        measured 17.97, and 26 against 195. A run names the gap and leaves the
        catalogue to a person."""
        from n2m.cli import drift_lines
        self.assertTrue(module.drifted(17.97, 0.41))
        self.assertTrue(module.drifted(195.28, 26.0))
        self.assertFalse(module.drifted(0.16, 0.13))
        self.assertFalse(module.drifted(195.28, 76.62 * 1.3))
        # A unit with no recorded wall at all has nothing to stand against.
        self.assertTrue(module.drifted(1.0, None))
        report = {"tag": "level0", "drift": ["a"], "measured_walls": {"a": {"wall": 17.61, "cpu": 17.2}},
                  "units": {"a": {"recorded_seconds": 48.2}}}
        self.assertEqual(drift_lines(report),
                         ["a: measured 17.61s against 48.20s recorded, wall/CPU 1.02",
                          f"{module.CATALOGUE} is unchanged. Record this sitting if the host was "
                          "quiet: python tools/build.py tests record --tag level0"])
        self.assertEqual(drift_lines({"drift": []}), [])

    def test_a_host_without_per_child_cpu_records_an_unknown_ratio(self):
        record = {"status": "PASS", "measured_walls": {"a": {"wall": 12.0, "cpu": None}},
                  "finished": "2026-09-20T14:29:07+00:00", "commit": "abcdef123456", "os": "Windows"}
        root = self.build("selection", "tests/summary.json", record)
        self.assertEqual(module.record_from_run(root, "selection")["durations_written"], 1)
        self.assertIsNone(self.entries(root)["a"]["measured"]["wall_cpu"])

    def test_recording_a_tag_that_left_no_run_record_fails_by_name(self):
        self.build("selection", "tests/summary.json", {"status": "PASS"})
        with self.assertRaisesRegex(ValueError, "no retained run record for tag absent"):
            module.record_from_run(Path(self.temp.name), "absent")
        report = module.record_from_run(Path(self.temp.name), "selection")
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("records no wall that describes actual work", report["error"])


class UnmeasuredDuration(unittest.TestCase):
    def test_a_zero_duration_is_flagged_and_null_is_not(self):
        for duration, expected in ((0.0, ["unit cpu-alu records duration_seconds 0.00; run it so the "
                                          "catalogue carries its measured wall, or restore null"]),
                                   (None, []), (0.01, [])):
            with self.subTest(duration=duration):
                self.assertEqual(module.unmeasured(
                    model(units={"cpu-alu": dict(ENTRY, duration_seconds=duration)})), expected)

    def test_the_measuring_run_is_not_blocked_by_the_entry_it_fixes(self):
        # coverage() gates `tests run`; a zero duration must not stop the run
        # that writes the real wall back.
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "src/dv/builder").mkdir(parents=True)
        (root / "src/dv/builder/targets.json").write_text(
            json.dumps({"cpu-alu": {"simulators": ["verilator"]}}), encoding="utf-8")
        (root / module.CATALOGUE).write_text(module.format_document(
            model(units={"cpu-alu": dict(ENTRY, duration_seconds=0.0)})),
            encoding="utf-8", newline="\n")
        loaded, _ = module.load(root)
        self.assertEqual(module.coverage(root, loaded), [])


class SimulatorCapabilities(unittest.TestCase):
    def test_a_target_without_a_valid_simulator_fails_validation(self):
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "src/dv/builder").mkdir(parents=True)
        (root / module.CATALOGUE).write_text(module.format_document(model()), encoding="utf-8", newline="\n")
        loaded, _ = module.load(root)
        for row in ({}, {"simulators": []}, {"simulators": ["icarus"]},
                    {"simulators": ["verilator", "verilator"]}, {"simulators": None}):
            (root / "src/dv/builder/targets.json").write_text(json.dumps({"cpu-alu": row}), encoding="utf-8")
            self.assertEqual(module.coverage(root, loaded),
                             ["registry target cpu-alu must declare simulators as a nonempty unique list drawn from verilator, questa"])

    def test_an_unsupported_backend_is_skipped_by_name_and_never_launched(self):
        """An area run names the unsupported pair as SKIPPED unsupported-backend;
        the supported rows still run and the selection is neither failed nor
        silently passed for the skipped one."""
        args = type("Args", (), {"seed": 1, "rebuild": False, "verilator_bin": None,
                                 "questa_bin": None, "intel_sim_lib": None, "sim": "questa",
                                 "level": 0, "label": [], "broader": False})()
        loaded, path = module.load(ROOT)
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temp.cleanup)
        copy = Path(temp.name) / "catalogue.yaml"
        shutil.copy(path, copy)
        # builder-smoke declares both backends; the tile-pixel Python driver is Verilator-only.
        loaded["units"] = {name: loaded["units"][name] for name in ("builder-smoke", "tile-pixel")}
        launched = []

        def fake_supervise(command, root, tag, *, target=None, ceiling=None):
            launched.append(target)
            return 0, json.dumps({"status": "PASS", "cache": "BUILT"}) + "\n"

        with patch("n2m.catalogue.supervise", side_effect=fake_supervise):
            record = module.run_selection(ROOT, loaded, copy, "tag", args, 300, {})
        self.assertEqual(launched, ["builder-smoke"])
        self.assertEqual((record["status"], record["failed"], record["skipped"]), ("PASS", [], ["tile-pixel"]))
        self.assertEqual(record["units"]["builder-smoke"]["status"], "PASS")
        self.assertEqual(record["units"]["tile-pixel"],
                         {"status": "SKIPPED", "reason": "unsupported-backend",
                          "error": "target tile-pixel does not support simulator questa; supported: verilator"})
        # A skip never ran, so it leaves no wall in the run's record, and the
        # run writes nothing into the catalogue whatever it measured.
        self.assertEqual(sorted(record["measured_walls"]), ["builder-smoke"])
        self.assertEqual(copy.read_bytes(), path.read_bytes())

    def test_a_cached_simulation_reports_its_cache_hit(self):
        args = type("Args", (), {"seed": 1, "rebuild": False, "verilator_bin": "/tools/bin",
                                 "questa_bin": None, "intel_sim_lib": None, "sim": "verilator"})()
        with patch("n2m.catalogue.supervise",
                   return_value=(0, json.dumps({"status": "PASS", "cache": "CACHED"}) + "\n")) as run:
            outcome = module.run_simulation(ROOT, "tag", "builder-smoke", args, 100)
        self.assertEqual((outcome["status"], outcome["cache"]), ("PASS", "CACHED"))
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--verilator-bin") + 1], "/tools/bin")
        self.assertNotIn("--questa-bin", command)

    def test_a_real_simulation_failure_is_still_a_failure(self):
        args = type("Args", (), {"seed": 1, "rebuild": False, "verilator_bin": None,
                                 "questa_bin": None, "intel_sim_lib": None, "sim": "verilator"})()
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

    def test_closure_trace_of_one_declared_unit_summarizes_and_exits_zero(self):
        # The human summary path is the one that used to index the validate-only
        # keys, so this runs the command without --json and reads its record back.
        tag = "closure-trace-cli-unit-test"
        code, text = self.run_cli("tests", "closure-trace", "--unit", TRACED_UNIT, "--tag", tag)
        self.assertEqual(code, 0, text)
        self.assertIn("1 of 1 units traced, 0 problems", text)
        record = json.loads((ROOT / "workdir/builds" / tag / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((record["status"], record["problems"], record["traced"]), ("PASS", [], 1))
        self.assertEqual(record["units"][TRACED_UNIT]["status"], "PASS")
        self.assertNotIn("not_runnable", record)
        shutil.rmtree(ROOT / "workdir/builds" / tag, ignore_errors=True)

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

    def test_a_units_budget_is_the_default_or_a_multiple_of_its_own_measured_wall(self):
        """One number for every unit is sized by the slowest and then bounds nothing else."""
        default, factor = module.UNIT_CPU_BUDGET, module.UNIT_CPU_FACTOR
        self.assertEqual(module.unit_cpu_budget({"duration_seconds": None}), default)
        self.assertEqual(module.unit_cpu_budget({}), default)
        self.assertEqual(module.unit_cpu_budget({"duration_seconds": default / factor / 2}), default)
        # Only a unit that measured more than the default's own share of the factor gets more.
        self.assertEqual(module.unit_cpu_budget({"duration_seconds": default}), factor * default)
        # A drift report arrives before a budget failure, so growth is named before it blocks.
        self.assertGreater(factor, module.DRIFT_FACTOR)

    @measures_cpu
    def test_a_unit_that_waits_for_a_core_passes_while_one_that_grows_fails(self):
        """Same wall, opposite verdicts: the bound is the work the unit did, not its waiting."""
        self.write(WAIT.format(2.0))
        with patch.object(module, "UNIT_CPU_BUDGET", 1):
            waited = module.run_unit(self.root, "suite/test_one.py", UNMEASURED)
            self.write(BURN.format(2.0))
            grown = module.run_unit(self.root, "suite/test_one.py", UNMEASURED)
        self.assertEqual(waited["status"], "PASS", waited)
        self.assertGreaterEqual(waited["elapsed_seconds"], 2.0)
        self.assertLess(waited["cpu_seconds"], 1)
        self.assertEqual(waited["cpu_budget_seconds"], 1)
        self.assertEqual(grown["status"], "FAIL")
        self.assertGreater(grown["cpu_seconds"], 1)
        self.assertRegex(grown["error"], r"^unit used \d+ s of CPU, over its 1-second CPU budget "
                                         r"\(wall \d+ s, [\d.]+x its CPU\)$")

    @measures_cpu
    def test_a_unit_measured_above_the_default_is_bounded_against_its_own_wall(self):
        """The proportional bound has to raise the budget and still fail growth past it."""
        entry = {"labels": [], "duration_seconds": 1.0}
        self.write(BURN.format(1.5))
        with patch.object(module, "UNIT_CPU_BUDGET", 1), patch.object(module, "UNIT_CPU_FACTOR", 2):
            inside = module.run_unit(self.root, "suite/test_one.py", entry)
            self.write(BURN.format(3.0))
            outside = module.run_unit(self.root, "suite/test_one.py", entry)
        # 1.5 s of CPU is over the 1-second default and inside this unit's own 2 seconds.
        self.assertEqual((inside["status"], inside["cpu_budget_seconds"]), ("PASS", 2))
        self.assertGreater(inside["cpu_seconds"], 1)
        self.assertEqual(outside["status"], "FAIL")
        self.assertIn("over its 2-second CPU budget", outside["error"])

    def test_a_unit_that_stops_making_progress_fails_on_the_wall_ceiling(self):
        self.write(WAIT.format(60))
        with patch.object(module, "UNIT_CPU_BUDGET", 1), patch.object(module, "UNIT_WALL_STRETCH", 1):
            outcome = module.run_unit(self.root, "suite/test_one.py", UNMEASURED)
        self.assertEqual(outcome["status"], "FAIL")
        self.assertIsNone(outcome["exit_code"])
        self.assertRegex(outcome["error"], r"^unit made no progress: it ran \d+ s, past the 1-second "
                                           r"wall ceiling, for (\d+ s of|an unmeasured amount of) CPU$")

    def test_a_unit_whose_cpu_time_cannot_be_read_is_judged_on_its_wall(self):
        """The fail-safe path, exercised rather than argued: a host without `os.wait4`, and a
        CPython release that renamed the reaping hook, both land here. Neither may pass silently."""
        self.write(WAIT.format(2.0))
        with patch.object(module, "UNIT_CPU_BUDGET", 1):
            measured = module.run_unit(self.root, "suite/test_one.py", UNMEASURED)
            with patch.object(cpu_budget, "Child", subprocess.Popen):
                unmeasured = module.run_unit(self.root, "suite/test_one.py", UNMEASURED)
        # The same unit the measured run passes fails here, on the wall, and says why.
        self.assertEqual(measured["status"], "PASS", measured)
        self.assertNotIn("cpu_seconds", unmeasured)
        self.assertEqual(unmeasured["status"], "FAIL")
        self.assertRegex(unmeasured["error"], r"^unit ran \d+ s, over its 1-second budget; this host "
                                              r"reports no per-child CPU time, so a busy machine can fail it$")

    def test_a_cocotb_unit_is_skipped_by_name_when_its_interpreter_is_absent(self):
        self.write("import unittest\n")
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": ["needs-cocotb"]})
        self.assertEqual((outcome["status"], outcome["reason"]), ("SKIPPED", "cocotb-environment"))

    def test_a_wiki_unit_runs_on_the_pinned_environment_or_is_skipped_by_name(self):
        self.write("import unittest\n")
        # No tools/wiki/check.py in this root: a tracked file is missing, so this
        # is a broken checkout and it fails rather than skipping.
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": ["needs-wiki-env"]})
        self.assertEqual(outcome["status"], "FAIL")
        self.assertIn("tools/wiki/check.py", outcome["error"])
        shutil.copytree(ROOT / "tools/wiki", self.root / "tools/wiki",
                        ignore=shutil.ignore_patterns("__pycache__", "assets", "board_frames"))
        # The rule comes from check.py, so the located directory is the one it builds.
        self.assertIsNone(module.wiki_python(self.root))
        directory, interpreter, _ = self.wiki_check().environment(self.root)
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text("", encoding="utf-8")
        self.assertIsNone(module.wiki_python(self.root))  # built but never marked ready
        (directory / ".ready").write_text(directory.name + "\n", encoding="utf-8")
        self.assertEqual(module.wiki_python(self.root), str(interpreter))
        command = module.unit_command(self.root, "suite/test_one.py", {"labels": ["needs-wiki-env"]},
                                      module.wiki_python(self.root))
        self.assertEqual(command[0], str(interpreter))

    def wiki_check(self):
        spec = importlib.util.spec_from_file_location("wiki_check_fixture",
                                                      self.root / "tools/wiki/check.py")
        check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check)
        return check


# A check.py double: it answers the two questions the catalogue asks and records
# every build, so the contract is exercised without a venv or the network.
# `installed` reads the lock file first, exactly as the real one hashes it, so
# removing `requirements.txt` reproduces the broken-checkout case for real.
STUB_CHECK = '''\
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def interpreter(root):
    return Path(root) / "workdir/tools/wiki/python-stub/bin/python"


def installed(root=ROOT):
    (Path(root) / "tools/wiki/requirements.txt").read_text(encoding="utf-8")
    found = interpreter(root)
    return found if found.is_file() else None


def build(root=ROOT, *, browser=False, capture=False):
    log = Path(root) / "build-calls.log"
    log.write_text((log.read_text(encoding="utf-8") if log.is_file() else "") + "call\\n",
                   encoding="utf-8")
    if (Path(root) / "offline").is_file():
        raise RuntimeError("no network")
    found = interpreter(root)
    found.parent.mkdir(parents=True, exist_ok=True)
    found.write_text("", encoding="utf-8")
    return found
'''


# A check.py double whose environment is already BUILT: `installed` names a real
# interpreter, so preparation reports PRESENT and `build` must not be reached.
BUILT_CHECK = """\
import sys
from pathlib import Path


def installed(root=None):
    return Path(sys.executable)


def build(root=None, *, browser=False, capture=False):
    raise AssertionError('a built environment must not be rebuilt')
"""


class WikiEnvironmentPreparation(unittest.TestCase):
    """The pinned wiki interpreter is built before the clock, never skipped past."""

    def setUp(self):
        base = ROOT / "workdir/builds/catalogue-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def install_stub(self):
        path = self.root / "tools/wiki/check.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STUB_CHECK, encoding="utf-8")
        self.lock().write_text("Markdown==3.10.3\n", encoding="utf-8")

    def lock(self):
        return self.root / "tools/wiki/requirements.txt"

    def builds(self):
        log = self.root / "build-calls.log"
        return log.read_text(encoding="utf-8").count("call") if log.is_file() else 0

    def test_preparation_without_check_py_reports_a_broken_checkout(self):
        """A tracked file that is gone is this repository's defect, not the host's."""
        record = module.prepare_wiki_environment(self.root)
        self.assertEqual(record["status"], "BROKEN")
        self.assertIn("tools/wiki/check.py", record["error"])
        self.assertIn("broken checkout", record["error"])
        with self.assertRaises(module.WikiEnvironmentDefect):
            module.wiki_python(self.root)

    def test_a_missing_environment_is_built_once_so_the_unit_runs_for_real(self):
        self.install_stub()
        self.assertIsNone(module.wiki_python(self.root))
        record = module.prepare_wiki_environment(self.root)
        self.assertEqual(record["status"], "BUILT")
        self.assertGreaterEqual(record["elapsed_seconds"], 0)
        self.assertEqual(module.wiki_python(self.root), record["interpreter"])
        self.assertEqual(self.builds(), 1)
        # A second run finds it present and builds nothing again.
        again = module.prepare_wiki_environment(self.root)
        self.assertEqual((again["status"], again["interpreter"]), ("PRESENT", record["interpreter"]))
        self.assertEqual(self.builds(), 1)
        command = module.unit_command(self.root, "suite/test_one.py",
                                      {"labels": ["needs-wiki-env"]}, module.wiki_python(self.root))
        self.assertEqual(command[0], record["interpreter"])

    def test_a_build_that_cannot_complete_is_reported_and_the_unit_is_skipped(self):
        """The one host condition that degrades: the lock is there, the network is not."""
        self.install_stub()
        (self.root / "offline").write_text("", encoding="utf-8")
        record = module.prepare_wiki_environment(self.root)
        self.assertEqual(record["status"], "UNAVAILABLE")
        self.assertIn("could not be built here", record["error"])
        self.assertIn("no network", record["error"])
        self.assertEqual(self.builds(), 1)
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": ["needs-wiki-env"]})
        self.assertEqual((outcome["status"], outcome["reason"]), ("SKIPPED", "wiki-environment"))

    def test_a_missing_lock_file_is_broken_not_unavailable_and_fails_the_unit(self):
        """The two meanings are separated here: a checkout the host cannot fix.

        An offline host gets a named skip because building is the only thing
        missing. A lock file that is gone is a tracked file that is gone, which
        no host can supply, so it fails rather than degrading."""
        self.install_stub()
        self.lock().unlink()
        record = module.prepare_wiki_environment(self.root)
        self.assertEqual(record["status"], "BROKEN")
        self.assertIn("could not be located", record["error"])
        self.assertIn("requirements.txt", record["error"])
        self.assertEqual(self.builds(), 0)          # nothing is built over a broken checkout
        with self.assertRaises(module.WikiEnvironmentDefect):
            module.wiki_python(self.root)
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": ["needs-wiki-env"]})
        self.assertEqual(outcome["status"], "FAIL")
        self.assertNotIn("reason", outcome)         # never dressed as a skip
        self.assertIn("requirements.txt", outcome["error"])

    def test_a_check_py_that_cannot_be_read_is_broken_not_unavailable(self):
        """A check.py that raises on import is the same class of defect."""
        path = self.root / "tools/wiki/check.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("raise RuntimeError('broken check')\n", encoding="utf-8")
        record = module.prepare_wiki_environment(self.root)
        self.assertEqual(record["status"], "BROKEN")
        self.assertIn("broken check", record["error"])
        with self.assertRaises(module.WikiEnvironmentDefect):
            module.wiki_python(self.root)
        outcome = module.run_unit(self.root, "suite/test_one.py", {"labels": ["needs-wiki-env"]})
        self.assertEqual(outcome["status"], "FAIL")
        self.assertNotIn("reason", outcome)

    def narrowed_selection(self, unit="suite/test_one.py"):
        """A catalogue holding exactly one `needs-wiki-env` unit, as `--label` gives."""
        entry = {"kind": "unit", "level": 0, "labels": ["needs-wiki-env"],
                 "duration_seconds": None}
        selection = {"version": 1,
                     "labels": {"needs-wiki-env": "Imports the pinned Python-Markdown."},
                     "units": {unit: entry}, "not_runnable": {}}
        path = self.root / module.CATALOGUE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(module.format_document(selection), encoding="utf-8")
        args = type("Args", (), {"seed": 1, "rebuild": False, "verilator_bin": None,
                                 "questa_bin": None, "intel_sim_lib": None, "sim": "verilator",
                                 "level": 0, "label": ["needs-wiki-env"], "broader": False})()
        return selection, path, args

    def write_unit(self, body="import unittest\n"):
        suite = self.root / "suite"
        suite.mkdir(exist_ok=True)
        (suite / "test_one.py").write_text(body, encoding="utf-8")

    def test_a_narrowed_selection_fails_on_a_broken_checkout_and_skips_when_offline(self):
        """The green-without-running path is closed, and only that path.

        Both halves are asserted on the same selection, which is the one the
        acceptance criterion names: `--level 0 --label needs-wiki-env`. Neither
        verdict depends on any other unit being selected."""
        self.install_stub()
        self.write_unit()
        selection, path, args = self.narrowed_selection()
        # Offline, lock present: the owner-approved named skip, and it passes.
        (self.root / "offline").write_text("", encoding="utf-8")
        record = module.run_selection(self.root, selection, path, "tag", args, 300, {})
        self.assertEqual(record["status"], "PASS")
        self.assertEqual((record["failed"], record["skipped"]), ([], ["suite/test_one.py"]))
        self.assertEqual(record["preparation"]["wiki-environment"]["status"], "UNAVAILABLE")
        self.assertEqual(record["units"]["suite/test_one.py"]["reason"], "wiki-environment")
        # Lock removed: the same selection now fails and names the broken checkout.
        self.lock().unlink()
        record = module.run_selection(self.root, selection, path, "tag", args, 300, {})
        self.assertEqual(record["status"], "FAIL")
        self.assertEqual((record["failed"], record["skipped"]), (["suite/test_one.py"], []))
        self.assertEqual(record["preparation"]["wiki-environment"]["status"], "BROKEN")
        self.assertIn("broken checkout", record["preparation"]["wiki-environment"]["error"])
        self.assertIn("requirements.txt", record["units"]["suite/test_one.py"]["error"])
        # No wall is written for a unit that never ran.
        self.assertNotIn("elapsed_seconds", record["units"]["suite/test_one.py"])

    def test_a_broken_dependency_in_a_built_environment_fails_and_never_skips(self):
        """The property level 0 turns on: once the environment exists, a genuine
        import failure inside it is a FAIL. Were it a skip, the selection could go
        green while `test_site.py` never ran, which is the whole point of building
        the environment rather than labelling the unit past it."""
        (self.root / "tools/wiki").mkdir(parents=True, exist_ok=True)
        (self.root / "tools/wiki/check.py").write_text(BUILT_CHECK, encoding="utf-8")
        suite = self.root / "suite"
        suite.mkdir()
        # Stands in for `site.py` importing the pinned Python-Markdown.
        (suite / "test_one.py").write_text(
            "import unittest\nimport n2m_absent_pinned_package\n", encoding="utf-8")
        self.assertEqual(module.prepare_wiki_environment(self.root)["status"], "PRESENT")
        # The interpreter is there, so the skip branch is not even reachable:
        # whatever run_unit reports, it cannot be the absent-environment skip.
        self.assertEqual(module.wiki_python(self.root), sys.executable)
        entry = {"kind": "unit", "level": 0, "labels": ["needs-wiki-env"],
                 "duration_seconds": None}
        outcome = module.run_unit(self.root, "suite/test_one.py", entry)
        self.assertEqual(outcome["status"], "FAIL")
        self.assertNotIn("reason", outcome)          # a FAIL is never dressed as a skip
        self.assertIn("n2m_absent_pinned_package", outcome["output"])
        self.assertEqual(outcome["command"][0], sys.executable)
        # And the selection carrying it fails rather than passing with a skip.
        catalogue_path = self.root / module.CATALOGUE
        catalogue_path.parent.mkdir(parents=True, exist_ok=True)
        selection = {"version": 1,
                     "labels": {"needs-wiki-env": "Imports the pinned Python-Markdown."},
                     "units": {"suite/test_one.py": entry}, "not_runnable": {}}
        catalogue_path.write_text(module.format_document(selection), encoding="utf-8")
        args = type("Args", (), {"seed": 1, "rebuild": False, "verilator_bin": None,
                                 "questa_bin": None, "intel_sim_lib": None,
                                 "sim": "verilator", "level": 0, "label": [],
                                 "broader": False})()
        record = module.run_selection(self.root, selection, catalogue_path, "tag", args, 300, {})
        self.assertEqual(record["status"], "FAIL")
        self.assertEqual((record["failed"], record["skipped"]), (["suite/test_one.py"], []))
        self.assertEqual(record["preparation"]["wiki-environment"]["status"], "PRESENT")

    def test_the_only_state_that_skips_a_wiki_unit_is_a_host_that_cannot_build_it(self):
        """Pin the whole skip surface, not one case of it.

        Four states make the environment unusable. Exactly one of them is a host
        condition the owner approved degrading, and it is the only one allowed to
        skip. A refactor that widens the skip back over any other row fails here
        with `SKIPPED != FAIL`."""
        self.write_unit()
        entry = {"labels": ["needs-wiki-env"]}
        path = self.root / "tools/wiki/check.py"
        path.parent.mkdir(parents=True, exist_ok=True)

        def outcome():
            return module.run_unit(self.root, "suite/test_one.py", entry)

        self.assertEqual(outcome()["status"], "FAIL")                    # no check.py
        path.write_text("raise RuntimeError('broken check')\n", encoding="utf-8")
        self.assertEqual(outcome()["status"], "FAIL")                    # check.py raises
        self.install_stub()
        self.lock().unlink()
        self.assertEqual(outcome()["status"], "FAIL")                    # lock file gone
        self.install_stub()
        (self.root / "offline").write_text("", encoding="utf-8")
        module.prepare_wiki_environment(self.root)
        skipped = outcome()                                              # cannot build here
        self.assertEqual((skipped["status"], skipped["reason"]), ("SKIPPED", "wiki-environment"))

    def test_a_selection_prepares_the_environment_only_when_a_unit_needs_it(self):
        args = type("Args", (), {"seed": 1, "rebuild": False, "verilator_bin": None,
                                 "questa_bin": None, "intel_sim_lib": None, "sim": "verilator",
                                 "level": 0, "label": [], "broader": False})()
        loaded, path = module.load(ROOT)
        copy = self.root / "catalogue.yaml"
        shutil.copy(path, copy)
        needy = "tools/wiki/test_site.py"
        self.assertIn("needs-wiki-env", loaded["units"][needy]["labels"])
        prepared = {"status": "BUILT", "elapsed_seconds": 1.0, "interpreter": "/stub/python"}
        for units, expected in ((["tools/n2m/tests/test_fpga_hold.py"], {}),
                                ([needy], {"wiki-environment": prepared})):
            selection = {**loaded, "units": {name: loaded["units"][name] for name in units}}
            with patch("n2m.catalogue.prepare_wiki_environment", return_value=prepared) as prepare, \
                    patch("n2m.catalogue.run_unit", return_value={"status": "PASS"}):
                record = module.run_selection(ROOT, selection, copy, "tag", args, 300, {})
            self.assertEqual(record["preparation"], expected)
            self.assertEqual(prepare.call_count, 0 if expected == {} else 1)


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
