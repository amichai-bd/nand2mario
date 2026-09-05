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
        self.source = self.root / "unit.sv"
        self.source.write_text("source", encoding="utf-8")

    def invoke(self, responder=None, missing=False, simulator="icarus"):
        def normal(argv, **kwargs):
            if "+corrupt" in argv:
                return subprocess.CompletedProcess(argv, 1, "MISMATCH cycle=5")
            return subprocess.CompletedProcess(argv, 0, "PASS pixel_cases=524288 palette_cases=8192")

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
        self.assertEqual(run.call_count, 4)
        self.assertIn(str(self.source), manifest["commands"][1]["argv"])

    def test_missing_tool_records_failure(self):
        code, manifest, run = self.invoke(missing=True)
        self.assertEqual(code, 1)
        self.assertIn("missing tools", manifest["error"])
        run.assert_not_called()

    def test_questa_finish_and_failure_commands(self):
        code, manifest, _ = self.invoke(simulator="questa")
        self.assertEqual(code, 0)
        commands = [entry["argv"] for entry in manifest["commands"]
                    if "work.tb_dmg_tile_pixel" in entry["argv"]]
        self.assertEqual(len(commands), 2)
        for argv in commands:
            self.assertEqual(argv[argv.index("-onfinish") + 1], "exit")
            self.assertIn("onbreak {quit -code 1}", argv[-1])
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
            return subprocess.CompletedProcess(argv, 0, "PASS pixel_cases=524288 palette_cases=8192")
        code, manifest, _ = self.invoke(wrong_failure)
        self.assertEqual(code, 1)
        self.assertEqual(manifest["status"], "FAIL")

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
