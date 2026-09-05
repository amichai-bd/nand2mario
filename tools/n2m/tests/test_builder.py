"""Failure and cache contract tests; fake execution is not RTL evidence."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.cli import main
from n2m.records import atomic_json, read_json, valid_tag, workspace
from n2m.simulation import simulate
from n2m.simulator import Simulator, ToolError

ROOT = Path(__file__).resolve().parents[3]


class FakeSimulator:
    backend = "questa"
    compiler = "vlog"
    runtime = "vsim"

    def __init__(self):
        self.info = {"backend": "questa", "version": "2025.2", "path": "/tools/vsim"}
        self.tools = {name: name for name in ("vlib", "vmap", "vlog", "vsim")}
        self.calls = []
        self.fail = False
        self.warning = False
        self.signature = True
        self.timeout = False

    def path(self, value):
        return str(value)

    def command(self, argv):
        return argv

    def run(self, argv, cwd=None):
        self.calls.append(argv)
        if argv[0] == "vlib":
            (cwd / "work").mkdir()
        if argv[0] == "vmap" and "-c" in argv:
            (cwd / "modelsim.ini").write_text("local mappings")
        if argv[0] == self.compiler:
            (cwd / "work/design.bin").write_text("compiled")
            return SimpleNamespace(returncode=0, stdout="warning: test\n" if self.warning else "")
        if argv[0] != self.runtime:
            return SimpleNamespace(returncode=0, stdout="")
        if self.timeout:
            raise ToolError("runtime timed out", "last emitted diagnostic")
        (cwd / "waves/smoke.vcd").write_text("wave")
        return SimpleNamespace(returncode=1 if self.fail else 0,
                               stdout="PASS builder-smoke" if self.signature and not self.fail else "FAIL expected=7 actual=3")


class BuilderTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/builder-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="space ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for owner in ("tools/n2m", "src/dv/builder"):
            shutil.copytree(ROOT / owner, self.root / owner, ignore=shutil.ignore_patterns("__pycache__", "tests"))
        shutil.copy(ROOT / "tools/build.py", self.root / "tools/build.py")
        self.build = self.root / "workdir/builds/test"
        self.build.mkdir(parents=True)
        self.args = SimpleNamespace(target="builder-smoke", seed=1, rebuild=False)
        self.sim = FakeSimulator()

    def run_stage(self):
        return simulate(self.root, self.build, self.args, self.sim)

    def test_bounded_target_runtime_timeout_and_cache_identity(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        original_run = self.sim.run
        seen = []
        def run(argv, cwd=None, timeout=60):
            seen.append((argv[0], timeout))
            return original_run(argv, cwd=cwd)
        self.sim.run = run
        targets["builder-smoke"]["timeout_seconds"] = 180
        atomic_json(registry, targets)
        result = self.run_stage()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(seen[-1], ("vsim", 180))
        self.assertTrue(all(bound == 60 for _, bound in seen[:-1]))
        self.assertEqual(result["commands"][-1]["timeout_seconds"], 180)
        targets["builder-smoke"]["timeout_seconds"] = 181
        atomic_json(registry, targets)
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        for invalid in (0, 601, True, 1.5, "180"):
            targets["builder-smoke"]["timeout_seconds"] = invalid
            atomic_json(registry, targets)
            with self.assertRaisesRegex(ValueError, "timeout_seconds"):
                self.run_stage()

    def test_transitive_headers_invalidate_cache_and_missing_never_reuses(self):
        source = self.root / "src/dv/builder/builder_smoke.sv"
        source.write_text('`include "src/one.svh"\n' + source.read_text())
        first = self.root / "src/one.svh"
        second = self.root / "src/two.svh"
        first.write_text('`include "src/two.svh"\n')
        second.write_text('// original\n')
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        second.write_text('// changed\n')
        result = self.run_stage()
        self.assertEqual(result["cache"], "BUILT")
        self.assertIn("src/two.svh", result["inputs"])
        self.assertIn("+incdir+" + str(self.root), next(argv for argv in self.sim.calls if argv[0] == "vlog"))
        second.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.run_stage()

    def test_cache_reuse_and_rebuild(self):
        self.assertEqual(self.run_stage()["status"], "PASS")
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        self.assertEqual(len(self.sim.calls), 7)
        self.args.rebuild = True
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.assertEqual(len(self.sim.calls), 14)

    def test_stale_sources_runner_config_seed_tools(self):
        self.run_stage()
        for file in ("src/dv/builder/builder_smoke.sv", "tools/n2m/cli.py", "src/dv/builder/targets.json"):
            path = self.root / file
            path.write_text(path.read_text() + "\n")
            self.assertEqual(self.run_stage()["cache"], "BUILT", file)
        self.args.seed = 22
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.sim.info["version"] = "13.0"
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.sim.info["path"] = "/other/vsim"
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_missing_and_tampered_artifacts(self):
        first = self.run_stage()
        artifact = next(p for p in first["artifacts"] if p.endswith("design.bin"))
        (self.root / artifact).unlink()
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        current = self.run_stage()
        artifact = next(p for p in current["artifacts"] if p.endswith("smoke.vcd"))
        (self.root / artifact).write_text("tampered")
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_failed_rebuild_and_interruption_not_cached(self):
        self.run_stage()
        self.args.rebuild = True
        self.sim.fail = True
        failed = self.run_stage()
        self.assertEqual(failed["status"], "FAIL")
        self.assertTrue(any("sim.log" in p for p in failed["artifacts"]))
        self.sim.fail = False
        self.args.rebuild = False
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        current = self.build / "sim/test/builder-smoke/result.json"
        record = read_json(current)
        record["status"] = "RUNNING"
        atomic_json(current, record)
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_signature_and_warning_fail(self):
        self.sim.signature = False
        self.assertEqual(self.run_stage()["status"], "FAIL")
        self.sim.signature = True
        self.sim.warning = True
        self.assertEqual(self.run_stage()["status"], "FAIL")

    def test_empty_signature_rejected_and_timeout_preserved(self):
        target = self.root / "src/dv/builder/targets.json"
        config = json.loads(target.read_text())
        for invalid in ("", "  ", None):
            config["builder-smoke"]["signature"] = invalid
            target.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "signature"):
                self.run_stage()
        config["builder-smoke"]["signature"] = "PASS builder-smoke"
        target.write_text(json.dumps(config))
        self.sim.timeout = True
        result = self.run_stage()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("last emitted diagnostic" in (self.root / p).read_text()
                            for p in result["artifacts"] if p.endswith("sim.log")))
        tool = object.__new__(Simulator)
        with patch("n2m.simulator.subprocess.run", side_effect=subprocess.TimeoutExpired(
                ["vsim"], 60, output=b"last emitted diagnostic")):
            with self.assertRaises(ToolError) as caught:
                tool.run(["vsim"])
        self.assertEqual(caught.exception.output, "last emitted diagnostic")

    def test_expected_nonzero_is_explicit(self):
        target = self.root / "src/dv/builder/targets.json"
        config = json.loads(target.read_text())
        config["builder-smoke"].update(expected_exit="nonzero", signature="FAIL expected=7 actual=3")
        target.write_text(json.dumps(config))
        self.sim.fail = True
        self.assertEqual(self.run_stage()["status"], "PASS")

    def test_tile_corruption_cannot_disguise_normal_failure(self):
        for owner in ("src/rtl/display", "src/dv/display", "src/rtl/common"):
            shutil.copytree(ROOT / owner, self.root / owner)
        targets = json.loads((self.root / "src/dv/builder/targets.json").read_text())
        corrupt = targets["tile-pixel-corrupt"]["signature"]
        normal = targets["tile-pixel"]["signature"]
        original_run = self.sim.run

        def result_for(code, output):
            def run(argv, cwd=None):
                result = original_run(argv, cwd)
                if argv[0] == self.sim.runtime:
                    result.returncode, result.stdout = code, output
                return result
            return run

        for target, code, output, expected in (
                ("tile-pixel", 1, corrupt, "FAIL"),
                ("tile-pixel-corrupt", 1, "MISMATCH unrelated failure", "FAIL"),
                ("tile-pixel-corrupt", 0, corrupt, "FAIL"),
                ("tile-pixel-corrupt", 1, corrupt, "PASS"),
                ("tile-pixel", 0, normal, "PASS")):
            self.args.target = target
            with patch.object(self.sim, "run", side_effect=result_for(code, output)):
                result = self.run_stage()
                self.assertEqual(result["status"], expected, (target, code, output))
                if expected == "PASS":
                    self.assertEqual(self.run_stage()["cache"], "CACHED")

    def test_tags_default_collision_lock_and_traversal(self):
        for tag in ("../escape", ".", "..", "UPPER", "con", "nul.txt", "a.", "x" * 49):
            self.assertFalse(valid_tag(tag), tag)
        self.assertTrue(valid_tag("smoke-01.v1"))
        with workspace(self.root, None) as first:
            self.assertRegex(first.name, r"^\d{8}t\d{6}z$")
            with self.assertRaisesRegex(ValueError, "locked"):
                with workspace(self.root, first.name):
                    pass
            with workspace(self.root, None) as second:
                self.assertNotEqual(first, second)
        self.assertFalse((first / ".lock").exists())

    def test_corrupt_cache_and_escaping_artifact(self):
        self.run_stage()
        current = self.build / "sim/test/builder-smoke/result.json"
        for invalid in ("[]", "null", "truncated"):
            current.write_text(invalid)
            self.assertEqual(self.run_stage()["cache"], "BUILT")
        record = read_json(current)
        record["artifacts"] = {"../../outside": "anything"}
        atomic_json(current, record)
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_cli_failure_json_and_latest(self):
        latest = self.root / "workdir/latest.txt"
        latest.write_text("previous\n")
        with patch("n2m.doctor.questa", side_effect=ToolError("missing compiler")), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            status = main(["doctor", "--tag", "missing", "--json"], self.root)
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "FAIL")
        self.assertEqual(latest.read_text(), "previous\n")
        self.assertEqual(read_json(self.root / "workdir/builds/missing/status.json")["status"], "FAIL")

    def test_missing_executable(self):
        with self.assertRaises(ToolError):
            Simulator(questa_bin=str(self.root / "missing-questa"))

    def test_discovery_failure_invalidates_previous_success(self):
        with patch("n2m.cli.Simulator", return_value=self.sim), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()):
            command = ["sim", "test", "builder-smoke", "--tag", "discovery", "--json"]
            self.assertEqual(main(command, self.root), 0)
            with patch("n2m.cli.Simulator", side_effect=ToolError("missing runtime")):
                self.assertEqual(main(command + ["--rebuild"], self.root), 1)
            current = self.root / "workdir/builds/discovery/sim/test/builder-smoke/result.json"
            self.assertEqual(read_json(current)["status"], "FAIL")
            self.assertEqual(main(command, self.root), 0)
            self.assertEqual(len(self.sim.calls), 14)

    def test_cli_pass_cache_fail_latest(self):
        with patch("n2m.cli.Simulator", return_value=self.sim), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()):
            command = ["sim", "test", "builder-smoke", "--tag", "cli", "--json"]
            self.assertEqual(main(command, self.root), 0)
            self.assertEqual(main(command, self.root), 0)
            latest = self.root / "workdir/latest.txt"
            latest.write_text("other-success\n")
            self.sim.fail = True
            self.assertEqual(main(command + ["--rebuild"], self.root), 1)
            self.assertEqual(latest.read_text(), "other-success\n")
            self.assertEqual(read_json(self.root / "workdir/builds/cli/manifest.json")["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
