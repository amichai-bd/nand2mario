"""Explicit backend, isolated libraries, diagnostics, and cache failure tests."""
import contextlib
import io
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_builder
from n2m.cli import main
from n2m.records import read_json
from n2m.simulator import Simulator, ToolError


class FakeQuesta(test_builder.FakeSimulator):
    backend, compiler, runtime = "questa", "vlog", "vsim"

    def __init__(self):
        super().__init__()
        self.info = {"backend": "questa", "tools": {"vsim": {"path": "/tools/vsim", "version": "2025.2"}}}
        self.tools = {name: name for name in ("vlib", "vmap", "vlog", "vsim")}
        self.output = "PASS builder-smoke\nErrors: 0, Warnings: 0"
        self.exit_code = 0

    def run(self, argv, cwd=None):
        self.calls.append(argv)
        if argv[0] == "vlib":
            (cwd / "work").mkdir()
        if argv[0] == "vmap" and "-c" in argv:
            (cwd / "modelsim.ini").write_text("local mappings")
        if argv[0] == self.compiler:
            (cwd / "work/design.bin").write_text("compiled")
        if argv[0] != self.runtime:
            return SimpleNamespace(returncode=0, stdout="Errors: 0, Warnings: 0")
        if self.timeout:
            raise ToolError("runtime timed out", "partial Questa transcript")
        (cwd / "waves/smoke.vcd").write_text("wave")
        return SimpleNamespace(returncode=self.exit_code, stdout=self.output)


class QuestaTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def test_explicit_discovery_paths_hashes_and_no_fallback(self):
        directory = self.root / "tools with spaces"
        directory.mkdir()
        suffix = ".exe" if os.name == "nt" else ""
        for name in ("vlib", "vmap", "vlog", "vsim"):
            (directory / (name + suffix)).write_bytes(name.encode())
        def which(candidate):
            return candidate if Path(candidate).is_file() else None
        with patch("n2m.simulator.shutil.which", side_effect=which) as find, \
                patch.object(Simulator, "run", return_value=SimpleNamespace(
                    returncode=0, stdout="Questa 2025.2")) as run:
            simulator = Simulator("questa", questa_bin=str(directory))
            self.assertEqual(simulator.backend, "questa")
            self.assertEqual(len(run.call_args_list), 3)
            first_hash = simulator.info["tools"]["vsim"]["sha256"]
            (directory / ("vsim" + suffix)).write_bytes(b"new executable")
            changed = Simulator("questa", questa_bin=str(directory))
            self.assertNotEqual(first_hash, changed.info["tools"]["vsim"]["sha256"])
            (directory / ("vlog" + suffix)).unlink()
            with self.assertRaisesRegex(ToolError, "missing vlog"):
                Simulator("questa", questa_bin=str(directory))
            self.assertTrue(all(Path(call.args[0]).parent == directory for call in find.call_args_list))
        for backend, directory_arg in (("auto", str(directory)), ("questa", ""),
                                       ("questa", str(directory / "absent"))):
            with self.assertRaises(ToolError):
                Simulator(backend, questa_bin=directory_arg)
        with self.assertRaisesRegex(ToolError, "Icarus or WSL"):
            Simulator("questa", iverilog="iverilog")

    def test_bad_version_warning_and_timeout_fail_discovery(self):
        with patch("n2m.simulator.shutil.which", return_value=str(self.root / "tools/build.py")):
            for output, code in (("not Questa", 1), ("Other tool", 0), ("Questa\nWarning: bad", 0)):
                with patch.object(Simulator, "run", return_value=SimpleNamespace(returncode=code, stdout=output)):
                    with self.assertRaises(ToolError):
                        Simulator("questa")
            with patch.object(Simulator, "run", side_effect=ToolError("timed out", "partial")):
                with self.assertRaises(ToolError):
                    Simulator("questa")

    def test_isolated_macros_libraries_and_backend_cache(self):
        self.run_stage()
        self.sim = FakeQuesta()
        first = self.run_stage()
        self.assertEqual((first["status"], first["cache"]), ("PASS", "BUILT"))
        self.assertTrue(any("compile/questa/" in path for path in first["artifacts"]))
        macro = next(path for path in first["artifacts"] if path.endswith("run.do"))
        self.assertIn("runStatus -full", (self.root / macro).read_text())
        command = first["commands"][-1]["argv"]
        self.assertEqual(command[-2:], ["-do", "do run.do"])
        self.assertEqual(command[command.index("-onfinish") + 1], "stop")
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        self.assertEqual(len(self.sim.calls), 7)
        (self.root / macro).write_text("damaged macro")
        rebuilt = self.run_stage()
        self.assertEqual(rebuilt["cache"], "BUILT")
        self.assertNotEqual(first["commands"][1]["cwd"], rebuilt["commands"][1]["cwd"])
        self.sim.info["tools"]["vsim"]["version"] = "new version"
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.sim.info["tools"]["vsim"]["path"] = "/other/vsim"
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_diagnostics_signature_timeout_and_failed_rerun(self):
        self.sim = FakeQuesta()
        self.assertEqual(self.run_stage()["status"], "PASS")
        self.args.rebuild = True
        for output in ("PASS builder-smoke\nWarning: bad", "PASS builder-smoke\nWarnings: 1",
                       "PASS builder-smoke\n** Error: bad", "PASS builder-smoke\nErrors: 2",
                       "normal exit without signature"):
            self.sim.output = output
            self.assertEqual(self.run_stage()["status"], "FAIL")
        self.sim.timeout = True
        failed = self.run_stage()
        self.assertEqual(failed["status"], "FAIL")
        self.assertTrue(any("partial Questa transcript" in (self.root / path).read_text()
                            for path in failed["artifacts"] if path.endswith("sim.log")))
        self.sim.timeout = False
        self.sim.output = "PASS builder-smoke"
        self.args.rebuild = False
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_expected_corruption_requires_full_signature_and_nonzero(self):
        for owner in ("src/rtl/display", "src/dv/display"):
            shutil.copytree(Path(__file__).resolve().parents[3] / owner, self.root / owner)
        self.sim = FakeQuesta()
        self.args.target = "tile-pixel-corrupt"
        signature = read_json(self.root / "src/dv/builder/targets.json")[self.args.target]["signature"]
        for code, output, expected in ((1, "MISMATCH unrelated", "FAIL"), (0, signature, "FAIL"),
                                       (1, "** Fatal: " + signature + "\nErrors: 2", "FAIL"),
                                       (1, "** Fatal: " + signature + "\nErrors: 1, Warnings: 0", "PASS")):
            self.sim.exit_code, self.sim.output = code, output
            self.assertEqual(self.run_stage()["status"], expected)
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        self.args.target = "builder-smoke-fail"
        self.assertEqual(self.run_stage()["status"], "FAIL")

    def test_cli_selection_and_missing_tool_invalidate_success(self):
        self.sim = FakeQuesta()
        command = ["sim", "test", "builder-smoke", "--sim", "questa", "--questa-bin", "tools with spaces",
                   "--tag", "questa-cli", "--json"]
        with patch("n2m.cli.Simulator", return_value=self.sim) as discover, \
                patch("n2m.cli.git_state", return_value={}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(command, self.root), 0)
            self.assertEqual(discover.call_args.args, ("questa", None, None, None, "tools with spaces"))
            with patch("n2m.cli.Simulator", side_effect=ToolError("missing vsim", "partial discovery")):
                self.assertEqual(main(command + ["--rebuild"], self.root), 1)
            current = self.root / "workdir/builds/questa-cli/sim/test/builder-smoke/result.json"
            self.assertEqual(read_json(current)["status"], "FAIL")
            self.assertIn("partial discovery", (current.parents[3] / "discovery.log").read_text())


if __name__ == "__main__":
    unittest.main()
