"""Host unit closure derivation and its declaration drift guard, on a fixture tree."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import host_closure

ROOT = Path(__file__).resolve().parents[3]
EXTERNALS = {"cocotb": "pinned"}


class Fixture(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/host-closure-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="space ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("tools/n2m/__init__.py", "")
        self.write("tools/n2m/records.py", "import json\n")
        self.write("tools/n2m/host/__init__.py", "")
        self.write("tools/n2m/host/client.py", "from .. import records\n")
        self.write("src/dv/game/model.py", "VALUE = 1\n")
        self.write("src/dv/game/other.py", "VALUE = 2\n")
        self.write("src/dv/game/assets/tiles.json", "{}\n")
        self.write("src/dv/game/assets/maps.json", "{}\n")
        self.write("src/dv/other/model.py", "import cocotb\n")
        self.write("src/dv/game/test_unit.py",
                   "import sys\nfrom pathlib import Path\nROOT = Path(__file__).resolve().parents[3]\n"
                   "sys.path.insert(0, str(ROOT / 'tools'))\n"
                   "from n2m.host.client import Client\nimport model\n"
                   "def late():\n    from other import VALUE\n")
        self.cache = {}

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def derive(self, path="src/dv/game/test_unit.py", extra=()):
        return host_closure.derive(self.root, self.root / path, EXTERNALS, self.cache, extra)

    def check(self, entry, path="src/dv/game/test_unit.py"):
        return host_closure.check(self.root, path, entry, EXTERNALS, self.cache)


class Derivation(Fixture):
    def test_follows_sys_path_edits_the_test_directory_tools_and_function_imports(self):
        modules, references = self.derive()
        self.assertEqual(modules, {"src/dv/game/test_unit.py", "src/dv/game/model.py", "src/dv/game/other.py",
                                   "tools/n2m/__init__.py", "tools/n2m/host/__init__.py",
                                   "tools/n2m/host/client.py", "tools/n2m/records.py"})
        self.assertEqual(references, set())

    def test_stdlib_and_declared_external_imports_pass_and_others_are_undeclared(self):
        self.write("src/dv/game/model.py", "import json\nimport cocotb\n")
        self.assertIn("src/dv/game/model.py", self.derive()[0])
        self.write("src/dv/game/model.py", "import serial\n")
        with self.assertRaisesRegex(ValueError, r"undeclared import serial at line 1 of src/dv/game/model\.py"):
            host_closure.derive(self.root, self.root / "src/dv/game/test_unit.py", EXTERNALS, {})
        self.write("src/dv/game/model.py", "from . import nothing\n")
        with self.assertRaisesRegex(ValueError, r"undeclared import \. at line 1"):
            host_closure.derive(self.root, self.root / "src/dv/game/test_unit.py", EXTERNALS, {})

    def test_an_import_no_search_directory_serves_falls_back_to_every_tree_module_of_that_name(self):
        self.write("src/dv/game/model.py", "def load():\n    from helper import decode\n")
        self.write("src/dv/elsewhere/helper.py", "import cocotb\n")
        self.write("src/dv/other/helper.py", "")
        modules, _ = self.derive()
        self.assertLessEqual({"src/dv/elsewhere/helper.py", "src/dv/other/helper.py"}, modules)

    def test_an_unevaluable_sys_path_edit_widens_absolute_imports_to_same_named_modules(self):
        self.write("tools/n2m/records.py", "import sys\ndef enter(directory):\n    sys.path[:0] = [str(directory)]\n")
        modules, _ = self.derive()
        self.assertIn("src/dv/other/model.py", modules)
        self.assertIn("src/dv/game/model.py", modules)
        # A constant beside the caller-supplied root still names a repository directory.
        self.write("tools/n2m/records.py", "import sys\ndef enter(root):\n    sys.path.insert(0, str(root / 'tools'))\n")
        self.assertNotIn("src/dv/other/model.py", host_closure.derive(
            self.root, self.root / "src/dv/game/test_unit.py", EXTERNALS, {})[0])

    def test_anchored_references_are_evaluated_and_definitions_are_not_references(self):
        self.write("src/dv/game/test_unit.py",
                   "from pathlib import Path\nHERE = Path(__file__).resolve().parent\nASSETS = HERE / 'assets'\n"
                   "TILES = ASSETS / 'tiles.json'\n"
                   "def read():\n    return [p for p in ASSETS.glob('*.json')], TILES.read_text(),\\\n"
                   "        (Path(__file__).parents[1] / 'other/model.py').read_text(), Path(__file__).with_name('model.py')\n")
        _, references = self.derive()
        self.assertEqual(references, {"src/dv/game/assets", "src/dv/game/assets/tiles.json",
                                      "src/dv/other/model.py", "src/dv/game/model.py"})

    def test_generated_output_and_paths_outside_the_tree_are_ignored(self):
        self.write("src/dv/game/test_unit.py",
                   "from pathlib import Path\nROOT = Path(__file__).resolve().parents[3]\n"
                   "OUT = ROOT / 'workdir/builds'\nUP = ROOT.parent / 'x.json'\n"
                   "def run():\n    return OUT.read_text(), UP.read_text()\n")
        (self.root / "workdir/builds").mkdir(parents=True)
        self.assertEqual(self.derive()[1], set())


class Declaration(Fixture):
    def test_no_declaration_is_no_problem_and_no_closure(self):
        entry = {"kind": "unit", "level": 0, "labels": [], "duration_seconds": None}
        self.assertEqual(self.check(entry), [])
        with self.assertRaisesRegex(host_closure.Unknown, "no declared inputs"):
            host_closure.closure(self.root, "src/dv/game/test_unit.py", entry, EXTERNALS, self.cache, lambda d: [])

    def test_missing_redundant_and_undeclared_inputs_are_named(self):
        self.write("src/dv/game/test_unit.py",
                   "from pathlib import Path\nHERE = Path(__file__).resolve().parent\nimport model\n"
                   "def read():\n    return (HERE / 'assets/tiles.json').read_text(), list((HERE / 'assets').glob('*'))\n")
        entry = {"kind": "unit", "level": 0, "labels": [], "duration_seconds": None,
                 "inputs": ["src/dv/game/absent.json", "src/dv/game/model.py"]}
        self.assertEqual(self.check(entry), [
            "unit src/dv/game/test_unit.py declares a missing or out-of-tree input: src/dv/game/absent.json",
            "unit src/dv/game/test_unit.py declares an input its imports already reach: src/dv/game/model.py",
            "unit src/dv/game/test_unit.py references an undeclared input: src/dv/game/assets/",
            "unit src/dv/game/test_unit.py references an undeclared input: src/dv/game/assets/tiles.json"])
        entry["inputs"] = ["src/dv/game/assets"]
        self.assertEqual(self.check(entry), [])
        # A declared child narrows the directory reference; the file reference is covered exactly.
        entry["inputs"] = ["src/dv/game/assets/tiles.json"]
        self.assertEqual(self.check(entry), [])

    def test_undeclared_import_fails_with_or_without_a_declaration(self):
        self.write("src/dv/game/other.py", "import serial\n")
        for entry in ({"kind": "unit", "level": 0, "labels": [], "duration_seconds": None},
                      {"kind": "unit", "level": 0, "labels": [], "duration_seconds": None, "inputs": []}):
            self.assertEqual(self.check(entry), [
                "unit src/dv/game/test_unit.py: undeclared import serial at line 1 of src/dv/game/other.py"])

    def test_a_declared_module_is_loaded_dynamically_and_its_imports_follow(self):
        self.write("src/dv/game/test_unit.py",
                   "import importlib.util\nfrom pathlib import Path\n"
                   "spec = importlib.util.spec_from_file_location('tool', Path(__file__).with_name('tool.py'))\n")
        self.write("src/dv/game/tool.py", "import serial\n")
        entry = {"kind": "unit", "level": 0, "labels": [], "duration_seconds": None, "inputs": ["src/dv/game/tool.py"]}
        self.assertEqual(self.check(entry), [
            "unit src/dv/game/test_unit.py: undeclared import serial at line 1 of src/dv/game/tool.py"])
        self.write("src/dv/game/tool.py", "import model\n")
        self.cache = {}
        self.assertEqual(self.check(entry), [])
        closure = host_closure.closure(self.root, "src/dv/game/test_unit.py", entry, EXTERNALS, {}, lambda d: [])
        self.assertLessEqual({"src/dv/game/tool.py", "src/dv/game/model.py"}, closure)

    def test_closure_is_modules_declared_files_and_expanded_directories(self):
        entry = {"kind": "unit", "level": 0, "labels": [], "duration_seconds": None,
                 "inputs": ["src/dv/game/assets", "tools/n2m/records.py"]}
        self.assertEqual(self.check(entry), [
            "unit src/dv/game/test_unit.py declares an input its imports already reach: tools/n2m/records.py"])
        entry["inputs"] = ["src/dv/game/assets"]
        listed = []
        closure = host_closure.closure(self.root, "src/dv/game/test_unit.py", entry, EXTERNALS, self.cache,
                                       lambda d: listed.append(d) or ["src/dv/game/assets/tiles.json"])
        self.assertEqual(listed, ["src/dv/game/assets"])
        self.assertIn("src/dv/game/assets/tiles.json", closure)
        self.assertIn("src/dv/game/model.py", closure)
        self.assertIn("src/dv/game/test_unit.py", closure)


if __name__ == "__main__":
    unittest.main()
