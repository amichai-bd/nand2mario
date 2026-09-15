"""Runner exit/evidence contract tests; HDL behavior is checked in simulation."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tile_pixel
from n2m.simulator import ToolError

PASS = "PASS pixel_cases=524288 palette_cases=8192 cycles=532521 seed=none"
MISMATCH = ("MISMATCH cycle=5 phase=after-edge expected=10110 actual=10111 "
            "low=00 high=01 x=7 palette=e4 seed=none")
VERILATOR = "/tool path/bin/verilator"


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
        for name in tile_pixel.HELPERS:
            helper = self.root / name
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text("helper")
        self.source = self.root / "src/unit.sv"
        self.source.write_text("source", encoding="utf-8")

    def invoke(self, responder=None, missing=False, simulator=None):
        def normal(argv, **kwargs):
            if "+corrupt" in argv:
                return subprocess.CompletedProcess(argv, 1, MISMATCH)
            return subprocess.CompletedProcess(argv, 0, PASS)

        discovered = SimpleNamespace(tools={"verilator": VERILATOR},
                                     info={"backend": "verilator", "tools": {"verilator": {"path": VERILATOR}}},
                                     path=lambda p: str(Path(p).resolve()))
        discovery = {"side_effect": ToolError("missing verilator; select the Verilator tool directory explicitly")} \
            if missing else {"return_value": discovered}
        with patch.multiple(tile_pixel, ROOT=self.root, SOURCES=[self.source], __file__=str(self.script)), \
             patch("sys.argv", ["tile_pixel.py", "--tag", "test", *(["--sim", simulator] if simulator else [])]), \
             patch("tile_pixel.Simulator", **discovery), \
             patch("tile_pixel.subprocess.check_output", side_effect=["abc\n", ""]), \
             patch("tile_pixel.subprocess.run", side_effect=responder or normal) as run, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = tile_pixel.main()
        manifest = json.loads((self.root / "workdir/builds/test/manifest.json").read_text())
        return code, manifest, run

    def test_success_and_paths_with_spaces(self):
        code, manifest, run = self.invoke()
        self.assertEqual((code, manifest["status"]), (0, "PASS"))
        self.assertEqual(run.call_count, 3)
        self.assertIn(str(self.source), manifest["commands"][0]["argv"])
        self.assertEqual(manifest["tools"]["backend"], "verilator")
        for case in ("normal", "corrupt"):
            result = json.loads((self.root / "workdir/builds/test/sim/test/tile-pixel" / case / "result.json").read_text())
            self.assertEqual(result["wave"], "waves/simulation.fst")
        self.assertEqual(result["status"], "EXPECTED_FAILURE")

    def test_header_manifest_and_missing_dependency_fail_before_tools(self):
        self.source.write_text('`include "src/shared.svh"\n')
        header = self.root / "src/shared.svh"
        header.write_text('// shared\n')
        code, manifest, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertIn("src/shared.svh", manifest["inputs"])
        for name in tile_pixel.HELPERS:
            self.assertIn(name, manifest["inputs"])
        command = manifest["commands"][0]["argv"]
        self.assertIn("+incdir+" + str(self.root), command)

    def test_missing_header_retains_failure_manifest(self):
        self.source.write_text('`include "src/missing.svh"\n')
        code, manifest, run = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn("missing", manifest["error"])
        run.assert_not_called()

    def test_retired_backend_is_rejected(self):
        for simulator in ("questa", "icarus"):
            with self.subTest(simulator=simulator), self.assertRaises(SystemExit) as caught:
                self.invoke(simulator=simulator)
            self.assertEqual(caught.exception.code, 2)
        self.assertFalse((self.root / "workdir/builds/test").exists())

    def test_missing_tool_records_failure(self):
        code, manifest, run = self.invoke(missing=True)
        self.assertEqual(code, 1)
        self.assertIn("missing verilator", manifest["error"])
        run.assert_not_called()

    def test_verilator_build_and_run_commands(self):
        code, manifest, _ = self.invoke(simulator="verilator")
        self.assertEqual(code, 0)
        build, normal, corrupt = manifest["commands"]
        self.assertEqual(build["argv"][0], VERILATOR)
        for option in ("--cc", "--exe", "--build", "--timing", "--trace-fst", "--x-assign", "--x-initial"):
            self.assertIn(option, build["argv"])
        self.assertNotIn("-Wno-fatal", build["argv"])
        self.assertEqual(build["argv"][build["argv"].index("--top-module") + 1], "tb_dmg_tile_pixel")
        self.assertEqual(build["cwd"], "compile/verilator")
        self.assertTrue((self.root / "workdir/builds/test/compile/verilator/sim_main.cpp").is_file())
        for entry, case in ((normal, "normal"), (corrupt, "corrupt")):
            self.assertTrue(entry["argv"][0].endswith("compile/verilator/obj_dir/sim"))
            self.assertEqual(entry["argv"][1:4], ["+seed=1", "+verilator+seed+1", "+verilator+rand+reset+2"])
            self.assertEqual(entry["cwd"], "sim/test/tile-pixel/" + case)
        self.assertNotIn("+corrupt", normal["argv"])
        self.assertEqual(corrupt["argv"][-1], "+corrupt")

    def test_existing_tag_rejected(self):
        self.invoke()
        with self.assertRaises(SystemExit) as caught:
            self.invoke()
        self.assertEqual(caught.exception.code, 2)

    def test_build_warning_fails(self):
        code, manifest, _ = self.invoke(lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, "%Warning-WIDTHTRUNC: unit.sv:1:1: bad width"))
        self.assertEqual(code, 1)
        self.assertIn("unexplained simulator warning", manifest["error"])
        self.assertEqual(len(manifest["commands"]), 1)

    def test_unrelated_failure_is_not_checker_proof(self):
        def wrong_failure(argv, **kwargs):
            if "+corrupt" in argv:
                return subprocess.CompletedProcess(argv, 1, "unrelated failure")
            return subprocess.CompletedProcess(argv, 0, PASS)
        code, manifest, _ = self.invoke(wrong_failure)
        self.assertEqual(code, 1)
        self.assertEqual(manifest["status"], "FAIL")

    def test_corruption_requires_nonzero_exit(self):
        code, manifest, _ = self.invoke(
            lambda argv, **kwargs: subprocess.CompletedProcess(
                argv, 0, MISMATCH if "+corrupt" in argv else PASS))
        self.assertEqual(code, 1)
        self.assertEqual(manifest["commands"][-1]["exit_code"], 0)
        self.assertIn("unexpected result", manifest["error"])

    def test_corruption_requires_full_diagnostic(self):
        def incomplete(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, "MISMATCH cycle=5") if "+corrupt" in argv else \
                subprocess.CompletedProcess(argv, 0, PASS)
        code, manifest, _ = self.invoke(incomplete)
        self.assertEqual(code, 1)
        self.assertIn("unexpected result", manifest["error"])

    def test_run_warning_overrides_pass(self):
        def warning(argv, **kwargs):
            output = PASS
            if argv[0].endswith("obj_dir/sim"):
                output += "\n[10] %Warning: tb_dmg_tile_pixel.sv:5: uninitialized read"
            return subprocess.CompletedProcess(argv, 0, output)
        code, manifest, _ = self.invoke(warning)
        self.assertEqual(code, 1)
        self.assertIn("unexplained simulator warning", manifest["error"])

    def test_error_overrides_pass(self):
        def error(argv, **kwargs):
            output = PASS
            if argv[0].endswith("obj_dir/sim"):
                output += "\n%Error: tb_dmg_tile_pixel.sv:9: unexpected scoreboard failure"
            return subprocess.CompletedProcess(argv, 0, output)
        code, manifest, _ = self.invoke(error)
        self.assertEqual(code, 1)
        self.assertIn("unexpected simulator diagnostic", manifest["error"])

    def test_extra_error_is_not_corruption_proof(self):
        def error(argv, **kwargs):
            if "+corrupt" in argv:
                return subprocess.CompletedProcess(argv, 1, MISMATCH + "\n%Error: tb_dmg_tile_pixel.sv:9: other failure")
            return subprocess.CompletedProcess(argv, 0, PASS)
        code, manifest, _ = self.invoke(error)
        self.assertEqual(code, 1)
        self.assertIn("unexpected simulator diagnostic", manifest["error"])

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
