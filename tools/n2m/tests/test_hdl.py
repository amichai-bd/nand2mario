"""Dependency parsing is conservative across preprocessor branches."""
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.hdl import dependencies


class HdlTests(unittest.TestCase):
    def test_literal_module_include_and_cycle(self):
        parent = Path(__file__).resolve().parents[3] / "workdir/builds/hdl-tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root = Path(folder)
            (root / "src").mkdir()
            (root / "src/wrapper.sv").write_text('`define SYNTHESIS\n`include "src/product.sv"\n`undef SYNTHESIS\n')
            product = root / "src/product.sv"
            product.write_text('module product; endmodule\n')
            self.assertEqual(dependencies(root, ["src/wrapper.sv"]), ["src/wrapper.sv", "src/product.sv"])
            for invalid in ('`include "src/wrapper.sv"', '`include "src/../outside.sv"',
                            '`include "src/missing.sv"', '`include "src/product.sv" trailing'):
                product.write_text(invalid)
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    dependencies(root, ["src/wrapper.sv"])

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

    def test_synthesis_file_io_guards_and_conservative_unknowns(self):
        parent = Path(__file__).resolve().parents[3] / "workdir/builds/hdl-tests"
        parent.mkdir(parents=True, exist_ok=True)
        read = '$readmemh("rom.hex", storage);\n'
        continued = "\\\n"
        cases = [
            ('`define UNUSED_A ' + continued + '`ifndef SYNTHESIS\n' + read
             + '`define UNUSED_B ' + continued + '`endif\n', False),
            ('`define REGISTER(Q, D) ' + continued + 'always_ff @(posedge clk) ' + continued
             + 'Q <= D;\n`ifndef SYNTHESIS\n' + read + '`endif\n', True),
            ('`define GUARD `ifndef SYNTHESIS\n' + read + '`endif\n', False),
            ('`ifndef SYNTHESIS\n' + read + '`endif\n', True),
            ('`ifdef SYNTHESIS\nwire ready;\n`else\n' + read + '`endif\n', True),
            ('`ifdef UNKNOWN\nwire ready;\n`elsif SYNTHESIS\nwire other;\n`else\n' + read + '`endif\n', True),
            ('`ifndef SYNTHESIS\n`ifdef UNKNOWN\n' + read + '`endif\n`endif\n', True),
            ('`ifdef SYNTHESIS\n' + read + '`endif\n', False),
            ('`ifndef SYNTHESIS\nwire ready;\n`else\n' + read + '`endif\n', False),
            ('`ifdef UNKNOWN\n' + read + '`endif\n', False),
            ('`ifdef UNKNOWN\nwire ready;\n`else\n' + read + '`endif\n', False),
            ('`ifndef SYNTHESIS\nwire ready;\n`elsif UNKNOWN\n' + read + '`endif\n', False),
            ('`undef SYNTHESIS\n`ifndef SYNTHESIS\n' + read + '`endif\n', False),
            ('`define SYNTHESIS\n', False),
            ('`undefineall\n', False),
            ('`ifndef SYNTHESIS\n' + read, False),
            ('`ifdef SYNTHESIS\n`else\n`else\n`endif\n', False),
            ('`ifdef UNKNOWN\n`else\n`elsif OTHER\n`endif\n', False),
            ('`ifndef SYNTHESIS\nwire ready; `else\n' + read + '`endif\n', False),
        ]
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root = Path(folder)
            (root / "src").mkdir()
            source = root / "src/test.sv"
            for text, allowed in cases:
                source.write_text(text)
                with self.subTest(text=text, allowed=allowed):
                    if allowed:
                        self.assertEqual(dependencies(root, ["src/test.sv"], synthesis=True), ["src/test.sv"])
                    else:
                        with self.assertRaises(ValueError):
                            dependencies(root, ["src/test.sv"], synthesis=True)
            source.write_text('`ifndef SYNTHESIS\n/* preserve\nlines */\n' + read + '`include "src/sim.svh"\n`endif\n')
            (root / "src/sim.svh").write_text('// still fingerprinted\n')
            self.assertEqual(dependencies(root, ["src/test.sv"], synthesis=True), ["src/test.sv", "src/sim.svh"])
