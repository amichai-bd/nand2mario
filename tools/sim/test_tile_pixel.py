"""Runner exit/evidence contract tests; HDL behavior is checked in simulation."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import tile_pixel

PASS = "PASS pixel_cases=524288 palette_cases=8192 cycles=532521 seed=none"
MISMATCH = ("MISMATCH cycle=5 phase=after-edge expected=10110 actual=10111 "
            "low=00 high=01 x=7 palette=e4 seed=none")


class RunnerTests(unittest.TestCase):
    def setUp(self):
        scratch = tile_pixel.ROOT / "workdir/builds"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="runner spaces ", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "tools/sim/tile_pixel.py"
        self.script.parent.mkdir(parents=True)
        self.script.write_text("runner", encoding="utf-8")
        (self.root / "src").mkdir()
        helper = self.root / "tools/n2m/hdl.py"
        helper.parent.mkdir()
        helper.write_text("helper")
        self.source = self.root / "src/unit.sv"
        self.source.write_text("source", encoding="utf-8")

    def invoke(self, responder=None, missing=False, simulator="questa"):
        def normal(argv, **kwargs):
            if "+corrupt" in argv:
                return subprocess.CompletedProcess(argv, 1, MISMATCH)
            return subprocess.CompletedProcess(argv, 0, PASS)

        with patch.multiple(tile_pixel, ROOT=self.root, SOURCES=[self.source], __file__=str(self.script)), \
             patch("sys.argv", ["tile_pixel.py", "--sim", simulator, "--tag", "test"]), \
             patch("tile_pixel.shutil.which", return_value=None if missing else "/tool path/bin"), \
             patch("tile_pixel.subprocess.check_output", side_effect=["abc\n", ""]), \
             patch("tile_pixel.subprocess.run", side_effect=responder or normal) as run, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = tile_pixel.main()
        manifest = json.loads((self.root / "workdir/builds/test/manifest.json").read_text())
        return code, manifest, run

    def test_success_and_paths_with_spaces(self):
        code, manifest, run = self.invoke()
        self.assertEqual((code, manifest["status"]), (0, "PASS"))
        self.assertEqual(run.call_count, 9)
        self.assertIn(str(self.source), manifest["commands"][2]["argv"])

    def test_header_manifest_and_missing_dependency_fail_before_tools(self):
        self.source.write_text('`include "src/shared.svh"\n')
        header = self.root / "src/shared.svh"
        header.write_text('// shared\n')
        code, manifest, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertIn("src/shared.svh", manifest["inputs"])
        command = manifest["commands"][2]["argv"]
        self.assertIn("+incdir+" + str(self.root), command)

    def test_missing_header_retains_failure_manifest(self):
        self.source.write_text('`include "src/missing.svh"\n')
        code, manifest, run = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn("missing", manifest["error"])
        run.assert_not_called()

    def test_missing_tool_records_failure(self):
        code, manifest, run = self.invoke(missing=True)
        self.assertEqual(code, 1)
        self.assertIn("missing tools", manifest["error"])
        run.assert_not_called()

    def test_questa_finish_and_failure_commands(self):
        code, manifest, _ = self.invoke(simulator="questa")
        self.assertEqual(code, 0)
        entries = [entry for entry in manifest["commands"]
                   if "work.tb_dmg_tile_pixel" in entry["argv"]]
        commands = [entry["argv"] for entry in entries]
        self.assertEqual(len(commands), 2)
        for argv in commands:
            self.assertEqual(argv[argv.index("-onfinish") + 1], "stop")
            self.assertEqual(argv[-1], "do run.do")
        for entry in entries:
            macro = (self.root / "workdir/builds/test" / entry["cwd"] / "run.do").read_text()
            self.assertEqual(macro.splitlines(), [
                "onbreak {if {[lindex [runStatus -full] 2] eq {$finish}} "
                "{quit -code 0} else {quit -code 1}}",
                "onerror {quit -code 1}", "run -all", "quit -code 1"])
        self.assertNotIn("+corrupt", commands[0])
        self.assertIn("+corrupt", commands[1])

    def test_existing_tag_rejected(self):
        self.invoke()
        with self.assertRaises(SystemExit) as caught:
            self.invoke()
        self.assertEqual(caught.exception.code, 2)

    def test_compile_warning_fails(self):
        code, manifest, _ = self.invoke(lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "warning: bad width"))
        self.assertEqual(code, 1)
        self.assertIn("warning", manifest["error"])

    def test_unrelated_failure_is_not_checker_proof(self):
        def wrong_failure(argv, **kwargs):
            if "+corrupt" in argv:
                return subprocess.CompletedProcess(argv, 1, "unrelated failure")
            return subprocess.CompletedProcess(argv, 0, PASS)
        code, manifest, _ = self.invoke(wrong_failure)
        self.assertEqual(code, 1)
        self.assertEqual(manifest["status"], "FAIL")

    def test_questa_corruption_requires_nonzero_exit(self):
        code, manifest, _ = self.invoke(
            lambda argv, **kwargs: subprocess.CompletedProcess(
                argv, 0, MISMATCH if "+corrupt" in argv else PASS), simulator="questa")
        self.assertEqual(code, 1)
        self.assertEqual(manifest["commands"][-1]["exit_code"], 0)
        self.assertIn("unexpected result", manifest["error"])

    def test_questa_corruption_requires_full_diagnostic(self):
        def incomplete(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, "MISMATCH cycle=5") if "+corrupt" in argv else \
                subprocess.CompletedProcess(argv, 0, PASS)
        code, manifest, _ = self.invoke(incomplete, simulator="questa")
        self.assertEqual(code, 1)
        self.assertIn("unexpected result", manifest["error"])

    def test_questa_macro_warning_overrides_pass(self):
        def warning(argv, **kwargs):
            output = PASS
            if "work.tb_dmg_tile_pixel" in argv:
                output += "\n# ** Warning: onbreak command for use within macro"
            return subprocess.CompletedProcess(argv, 0, output)
        code, manifest, _ = self.invoke(warning, simulator="questa")
        self.assertEqual(code, 1)
        self.assertIn("unexplained warning", manifest["error"])

    def test_questa_error_overrides_pass(self):
        def error(argv, **kwargs):
            output = PASS
            if "work.tb_dmg_tile_pixel" in argv:
                output += "\n# ** Error: unexpected scoreboard failure\n# Errors: 1, Warnings: 0"
            return subprocess.CompletedProcess(argv, 0, output)
        code, manifest, _ = self.invoke(error, simulator="questa")
        self.assertEqual(code, 1)
        self.assertIn("unexpected diagnostic", manifest["error"])

    def test_questa_extra_error_is_not_corruption_proof(self):
        def error(argv, **kwargs):
            if "+corrupt" in argv:
                return subprocess.CompletedProcess(argv, 1, MISMATCH + "\nErrors: 2, Warnings: 0")
            return subprocess.CompletedProcess(argv, 0, PASS)
        code, manifest, _ = self.invoke(error, simulator="questa")
        self.assertEqual(code, 1)
        self.assertIn("unexpected error count", manifest["error"])

    def test_questa_nonzero_warning_summary_fails(self):
        code, manifest, _ = self.invoke(
            lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "Errors: 0, Warnings: 1"),
            simulator="questa")
        self.assertEqual(code, 1)
        self.assertIn("unexplained warning", manifest["error"])

    def test_timeout_preserves_partial_output(self):
        def timeout(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 180, output=b"partial evidence")
        code, manifest, _ = self.invoke(timeout)
        self.assertEqual(code, 1)
        self.assertTrue(manifest["commands"][0]["timeout"])
        log = self.root / "workdir/builds/test" / manifest["commands"][0]["log"]
        self.assertEqual(log.read_text(), "partial evidence")


if __name__ == "__main__":
    unittest.main()
