"""An undeclared transitive Python import fails validation; explained exclusions pass."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from n2m import python_tb

ROOT = Path(__file__).resolve().parents[3]


class ImportCheckTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/builder-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="space ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("tools/n2m/__init__.py", "")
        self.write("tools/n2m/records.py", "")
        self.write("tools/n2m/host/__init__.py", "")
        self.write("tools/n2m/host/client.py", "")
        self.write("tools/sw/package.py", "from .linker import link\n")
        self.write("tools/sw/linker.py", "")
        # The test module reaches the springtrail model through its own sys.path edit,
        # a package import, a relative import and a branch it never takes.
        self.write("src/dv/python/integration/test_unit.py",
                   "import sys\nfrom pathlib import Path\n"
                   "ROOT = Path(__file__).resolve().parents[3]\n"
                   "sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'src/dv/springtrail')]\n"
                   "from n2m.records import file_hash\n"
                   "from n2m.host.client import Client\n"
                   "import helper\n"
                   "def unused():\n    from unit_reference import Check\n")
        self.write("src/dv/python/integration/helper.py", "from model import step\n")
        self.write("src/dv/springtrail/model.py", "import json\n")
        self.write("src/dv/springtrail/unit_reference.py", "from model import step\n")
        self.write("src/dv/springtrail/unit_program.py",
                   "def build(root):\n    from sw.package import package\n")
        self.write("src/dv/v05/model.py", "raise AssertionError('shadowed out-of-scope module')\n")
        self.declared = ["src/dv/python/integration/test_unit.py", "src/dv/python/integration/helper.py",
                         "src/dv/springtrail/model.py", "tools/n2m/host/__init__.py", "tools/n2m/host/client.py"]

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def target(self, inputs, excluded=None):
        python = {"module": "test_unit", "test": "unit", "inputs": list(inputs)}
        if excluded is not None:
            python["excluded_imports"] = excluded
        return {"testbench": "python", "top": "tb_unit", "expected_exit": "zero", "python": python}

    def test_undeclared_transitive_import_names_target_and_module(self):
        with self.assertRaisesRegex(ValueError, r"python-unit: undeclared transitive Python inputs: "
                                                r"src/dv/springtrail/unit_reference\.py$"):
            python_tb.validate(self.root, self.target(self.declared), "python-unit")
        missing = [p for p in self.declared if p != "src/dv/springtrail/model.py"]
        with self.assertRaisesRegex(ValueError, r"src/dv/springtrail/model\.py, src/dv/springtrail/unit_reference\.py"):
            python_tb.validate(self.root, self.target(missing), "python-unit")
        # A package import loads the package's __init__ as well as the module.
        missing = [p for p in self.declared if not p.startswith("tools/n2m/host/")]
        with self.assertRaisesRegex(ValueError, r"tools/n2m/host/__init__\.py, tools/n2m/host/client\.py"):
            python_tb.validate(self.root, self.target(missing, {"src/dv/springtrail/unit_reference.py": "unused"}),
                               "python-unit")

    def test_explained_exclusion_prunes_the_branch(self):
        excluded = {"src/dv/springtrail/unit_reference.py": "test_unit.unused is never called"}
        python_tb.validate(self.root, self.target(self.declared, excluded), "python-unit")
        # The excluded module's own imports are pruned with it, so an omission behind
        # it stays invisible until the exclusion is removed.
        self.write("src/dv/springtrail/unit_reference.py", "from extra import x\n")
        self.write("src/dv/springtrail/extra.py", "")
        python_tb.validate(self.root, self.target(self.declared, excluded), "python-unit")
        with self.assertRaisesRegex(ValueError, r"src/dv/springtrail/extra\.py"):
            python_tb.validate(self.root, self.target(self.declared), "python-unit")

    def test_exclusions_must_be_explained_reached_and_undeclared(self):
        for excluded, message in (
                (["src/dv/springtrail/unit_reference.py"], "must map each path to the reason"),
                ({"src/dv/springtrail/unit_reference.py": ""}, "must map each path to the reason"),
                ({"src/dv/springtrail/unit_reference.py": 1}, "must map each path to the reason"),
                ({"src/dv/v05/model.py": "out of scope"}, "not an in-scope module: src/dv/v05/model.py"),
                ({"src/dv/springtrail/absent.py": "missing"}, "not an in-scope module: src/dv/springtrail/absent.py"),
                ({"src/dv/springtrail/model.py": "declared"}, "also a declared input: src/dv/springtrail/model.py"),
                ({"src/dv/springtrail/unit_reference.py": "unused", "tools/sw/linker.py": "never loaded"},
                 "never reached: tools/sw/linker.py")):
            with self.assertRaisesRegex(ValueError, "python-unit: .*" + message):
                python_tb.validate(self.root, self.target(self.declared, excluded), "python-unit")

    def test_fixture_builder_imports_are_checked(self):
        target = {**self.target(self.declared, {"src/dv/springtrail/unit_reference.py": "unused"}),
                  "preload": "hud300-s"}
        with patch.dict(python_tb.FIXTURE_BUILDERS, {"hud300-s": "src/dv/springtrail/unit_program.py"}):
            with self.assertRaisesRegex(ValueError, r"undeclared transitive Python inputs: "
                                                    r"tools/sw/linker\.py, tools/sw/package\.py$"):
                python_tb.check_imports(self.root, target, "python-unit")
            target["python"]["inputs"] += ["tools/sw/package.py", "tools/sw/linker.py"]
            python_tb.check_imports(self.root, target, "python-unit")
        with self.assertRaisesRegex(ValueError, "python-unit: preload zz-new has no registered fixture builder"):
            python_tb.check_imports(self.root, {**target, "preload": "zz-new"}, "python-unit")

    def test_registered_builders_exist_and_the_tree_resolves(self):
        for preload, builder in python_tb.FIXTURE_BUILDERS.items():
            self.assertTrue((ROOT / builder).is_file(), f"{preload}: {builder}")
        loaded = python_tb.loaded_modules(ROOT, ROOT / "src/dv/springtrail/hud_reference.py")
        self.assertLessEqual({"src/dv/springtrail/blocks_reference.py", "src/dv/springtrail/movement_reference.py"},
                             loaded)
        self.assertTrue(all(path.startswith(python_tb.IMPORT_SCOPE) for path in loaded), loaded)


if __name__ == "__main__":
    unittest.main()
