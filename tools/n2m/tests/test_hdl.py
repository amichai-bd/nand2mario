"""Dependency parsing is conservative across preprocessor branches."""
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.hdl import dependencies


class HdlTests(unittest.TestCase):
    def test_literal_closure_comments_conditions_and_rejections(self):
        parent = Path(__file__).resolve().parents[3] / "workdir/builds/hdl-tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="path with spaces ", dir=parent) as folder:
            root = Path(folder)
            (root / "src").mkdir()
            source = root / "src/test.sv"
            header = root / "src/test.svh"
            header.write_text('// header\n')
            source.write_text('/* `include "missing" */\n// `include DYNAMIC\n'
                              '`ifdef OPTION\n`include "src/test.svh"\n`endif\n')
            self.assertEqual(dependencies(root, ["src/test.sv"]), ["src/test.sv", "src/test.svh"])
            for bad in ('`include DYNAMIC', '`include "../outside.svh"',
                        '`include "src/missing.svh"', '`include "src/test.svh" trailing',
                        '`include "src/test.svh"\n'):
                header.write_text(bad)
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    dependencies(root, ["src/test.sv"])
            header.write_text('// valid again\n')
            shadow = root / "src/src/test.svh"
            shadow.parent.mkdir()
            shadow.write_text('// ambiguous compiler search\n')
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                dependencies(root, ["src/test.sv"])
