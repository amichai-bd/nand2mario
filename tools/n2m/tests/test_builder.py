"""Failure and cache contract tests; fake execution is not RTL evidence."""
import contextlib
import io
import json
import os
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
from n2m.progress import Progress, powershell_command
from n2m.simulation import prepare, simulate
from n2m.simulator import Simulator, ToolError

ROOT = Path(__file__).resolve().parents[3]


class FakeSimulator:
    """A Verilator double: one build call creates obj_dir/sim, one run call
    writes the harness wave and answers with a transcript."""
    backend = "verilator"
    compiler = "verilator"

    def __init__(self):
        self.info = {"backend": "verilator", "tools": {"verilator": {"path": "/tools/verilator", "version": "Verilator 5.052"}}}
        self.tools = {"verilator": "verilator", "cxx": "g++"}
        self.calls = []
        self.fail = False
        self.warning = False
        self.signature = True
        self.timeout = False

    def path(self, value):
        return str(value)

    def command(self, argv):
        return argv

    def run(self, argv, cwd=None, timeout=60, env=None):
        self.calls.append(argv)
        if argv[0] == self.compiler:
            (cwd / "obj_dir").mkdir(exist_ok=True)
            (cwd / "obj_dir/sim").write_text("compiled")
            return SimpleNamespace(returncode=0, stdout="%Warning-WIDTH: test\n" if self.warning else "")
        if self.timeout:
            raise ToolError("runtime timed out", "last emitted diagnostic")
        (cwd / "waves/simulation.fst").write_text("wave")
        return SimpleNamespace(returncode=1 if self.fail else 0,
                               stdout="PASS builder-smoke" if self.signature and not self.fail else "FAIL expected=7 actual=3")


def migrate(root, *names):
    """Mark registry targets as Verilator in a test copy of the registry."""
    registry = Path(root) / "src/dv/builder/targets.json"
    targets = read_json(registry)
    for name in names:
        targets[name]["simulators"] = ["verilator"]
    atomic_json(registry, targets)


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

    def test_publication_denial_does_not_execute_or_cache_unpublished_success(self):
        self.run_stage()
        current = self.build / "sim/test/builder-smoke/verilator/result.json"
        old = current.read_bytes()
        self.args.rebuild = True
        self.sim.calls.clear()
        error = PermissionError("injected Windows access denial")
        error.winerror = 5
        with patch("n2m.records.os.replace", side_effect=error), patch("time.sleep"):
            with self.assertRaises(PermissionError):
                self.run_stage()
        self.assertEqual(self.sim.calls, [])
        self.assertEqual(current.read_bytes(), old)

        real_replace = os.replace
        def deny_final(source, destination):
            if destination == current and read_json(source).get("status") == "PASS":
                raise error
            real_replace(source, destination)
        with patch("n2m.records.os.replace", side_effect=deny_final), patch("time.sleep"):
            with self.assertRaises(PermissionError):
                self.run_stage()
        self.assertEqual(read_json(current)["status"], "RUNNING")
        self.args.rebuild = False
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.assertEqual(self.run_stage()["cache"], "CACHED")

    def test_bounded_target_runtime_timeout_and_cache_identity(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        original_run = self.sim.run
        seen = []
        def run(argv, cwd=None, timeout=60, env=None):
            seen.append((argv[0], timeout))
            return original_run(argv, cwd=cwd)
        self.sim.run = run
        targets["builder-smoke"]["timeout_seconds"] = 180
        atomic_json(registry, targets)
        result = self.run_stage()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(seen[-1][1], 180)
        self.assertTrue(seen[-1][0].endswith("sim"))
        # The C++ build gets the target's whole selected wall, not the 60-second default.
        self.assertEqual([bound for _, bound in seen[:-1]], [300])
        self.assertEqual(result["commands"][-1]["timeout_seconds"], 180)
        self.assertEqual(result["commands"][0]["timeout_seconds"], 300)
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
        self.assertIn("+incdir+" + str(self.root), next(argv for argv in self.sim.calls if argv[0] == "verilator"))
        second.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.run_stage()

    def test_cache_reuse_and_rebuild(self):
        self.assertEqual(self.run_stage()["status"], "PASS")
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        self.assertEqual(len(self.sim.calls), 2)
        self.args.rebuild = True
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.assertEqual(len(self.sim.calls), 4)

    def test_stale_sources_runner_config_seed_tools(self):
        self.run_stage()
        for file in ("src/dv/builder/builder_smoke.sv", "tools/n2m/cli.py", "src/dv/builder/targets.json"):
            path = self.root / file
            path.write_text(path.read_text() + "\n")
            self.assertEqual(self.run_stage()["cache"], "BUILT", file)
        self.args.seed = 22
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.sim.info["tools"]["verilator"]["version"] = "Verilator 13.0"
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        self.sim.info["tools"]["verilator"]["path"] = "/other/verilator"
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_missing_and_tampered_artifacts(self):
        first = self.run_stage()
        artifact = next(p for p in first["artifacts"] if p.endswith("obj_dir/sim"))
        (self.root / artifact).unlink()
        self.assertEqual(self.run_stage()["cache"], "BUILT")
        current = self.run_stage()
        artifact = next(p for p in current["artifacts"] if p.endswith("simulation.fst"))
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
        current = self.build / "sim/test/builder-smoke/verilator/result.json"
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
                ["sim"], 60, output=b"last emitted diagnostic")):
            with self.assertRaises(ToolError) as caught:
                tool.run(["sim"])
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
        migrate(self.root, "tile-pixel", "tile-pixel-corrupt")
        targets = json.loads((self.root / "src/dv/builder/targets.json").read_text())
        corrupt = targets["tile-pixel-corrupt"]["signature"]
        normal = targets["tile-pixel"]["signature"]
        original_run = self.sim.run

        def result_for(code, output):
            def run(argv, cwd=None, timeout=60, env=None):
                result = original_run(argv, cwd)
                if argv[0] != self.sim.compiler:
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
        current = self.build / "sim/test/builder-smoke/verilator/result.json"
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
        with patch("n2m.doctor.verilator", side_effect=ToolError("missing compiler")), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            status = main(["doctor", "--tag", "missing", "--json"], self.root)
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "FAIL")
        self.assertEqual(latest.read_text(), "previous\n")
        self.assertEqual(read_json(self.root / "workdir/builds/missing/status.json")["status"], "FAIL")

    def test_missing_executable(self):
        with self.assertRaises(ToolError):
            Simulator("verilator", verilator_bin=str(self.root / "missing-verilator"))

    def test_discovery_failure_invalidates_previous_success(self):
        with patch("n2m.cli.Simulator", return_value=self.sim), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()):
            command = ["sim", "test", "builder-smoke", "--tag", "discovery", "--json"]
            self.assertEqual(main(command, self.root), 0)
            with patch("n2m.cli.Simulator", side_effect=ToolError("missing runtime")):
                self.assertEqual(main(command + ["--rebuild"], self.root), 1)
            current = self.root / "workdir/builds/discovery/sim/test/builder-smoke/verilator/result.json"
            self.assertEqual(read_json(current)["status"], "FAIL")
            backend_log = current.with_name("sim.log")
            mirror_log = current.parent.parent / "sim.log"
            self.assertEqual(backend_log.read_text(), mirror_log.read_text())
            self.assertIn("missing runtime", backend_log.read_text())
            self.assertNotIn("PASS builder-smoke", backend_log.read_text())
            self.assertEqual(main(command, self.root), 0)
            self.assertEqual(len(self.sim.calls), 4)

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

    def test_cli_text_guides_build_cache_and_failure(self):
        with patch("n2m.cli.Simulator", return_value=self.sim), \
                patch("n2m.cli.git_state", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            command = ["sim", "test", "builder-smoke", "--tag", "human"]
            self.assertEqual(main(command, self.root), 0)
        text = output.getvalue()
        ordered = ["Simulation: target builder-smoke; backend verilator",
                   "[....] Discover Verilator tools", "[done] Discover Verilator tools",
                   "[....] Compile and elaborate", "[done] Compile and elaborate",
                   "[....] Run simulation", "[done] Run simulation",
                   "[....] Check simulation result", "[PASS] Check simulation result",
                   "Result: PASS (BUILT)", "Compile log:", "Simulation log:",
                   "Result record:", "Waveform (FST):", "Next (Windows PowerShell):"]
        positions = [text.index(fragment) for fragment in ordered]
        self.assertEqual(positions, sorted(positions), text)
        self.assertIn("--quartus-bin '<Quartus-bin>'", text)
        self.assertIn("--tag fpga-v05", text)

        with patch("n2m.cli.Simulator", return_value=self.sim), \
                patch("n2m.cli.git_state", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(command, self.root), 0)
        self.assertIn("[CACHED] Compile and elaborate — reused checked result", output.getvalue())

        self.sim.fail = True
        with patch("n2m.cli.Simulator", return_value=self.sim), \
                patch("n2m.cli.git_state", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(command + ["--rebuild"], self.root), 1)
        text = output.getvalue()
        self.assertIn("[FAIL] Run simulation", text)
        self.assertIn("Result: FAIL (BUILT)", text)
        self.assertIn("Diagnostic: ", text)
        self.assertNotIn("Next (Windows PowerShell):", text)

    def test_python_evidence_failure_precedes_result_stage_failure(self):
        requirements = self.root / "src/dv/python"
        requirements.mkdir(parents=True)
        for name in ("requirements.txt", "THIRD_PARTY.md"):
            (requirements / name).write_text("fixture\n")
        target = {"args": [], "expected_exit": "zero", "signature": "PASS builder-smoke",
                  "sources": ["src/dv/builder/builder_smoke.sv"], "top": "builder_smoke",
                  "testbench": "python", "python": {"module": "python_tb", "test": "fixture",
                                                        "inputs": ["tools/n2m/python_tb.py"]}}
        registry = self.root / "src/dv/builder/targets.json"

        def commands(simulator, root, definition, seed, compile_dir, attempt, **kwargs):
            return [([simulator.compiler], compile_dir, compile_dir / "build.log", "zero"),
                    (["sim"], attempt, attempt / "sim.log", "zero")]

        output = io.StringIO()
        with patch("n2m.simulation.load_target", return_value=(target, registry)), \
                patch("n2m.simulation.verilator_commands", side_effect=commands), \
                patch("n2m.simulation.python_tb.discover", return_value={"path": "fixture"}), \
                patch("n2m.simulation.python_tb.environment", return_value={}), \
                patch("n2m.simulation.python_tb.results", return_value={"status": "PASS"}), \
                patch("n2m.simulation.python_tb.evidence", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()):
            result = simulate(self.root, self.build, self.args, self.sim,
                              progress=Progress(stream=output))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["error"], "incomplete Python test evidence")
        text = output.getvalue()
        self.assertIn("[FAIL] Check simulation result", text)
        self.assertNotIn("[PASS] Check simulation result", text)

    def fake_prepare_files(self, backend, root, target, attempt, **_):
        (attempt / "fixture.bin").write_bytes(b"prepared fixture")

    def test_prepared_attempt_is_adopted_once_under_the_lock_with_split_walls(self):
        with patch("n2m.simulation.prepare_files", side_effect=self.fake_prepare_files):
            receipt = prepare(self.root, self.build, self.args, self.sim)
        self.assertEqual(receipt["status"], "PREPARED")
        attempt = self.build / "sim/test/builder-smoke/verilator/attempts" / receipt["prepared"]
        self.assertEqual(receipt["files"], {"fixture.bin": __import__("hashlib").sha256(b"prepared fixture").hexdigest()})
        self.assertIn("src/dv/builder/builder_smoke.sv", receipt["inputs"])
        self.assertGreaterEqual(receipt["prepare_seconds"], 0)
        # No tag lock, no stage record, no prepare lock left behind.
        self.assertFalse((self.build / ".lock").exists())
        self.assertFalse((attempt / ".lock").exists())
        self.assertFalse((self.build / "sim/test/builder-smoke/verilator/result.json").exists())
        self.assertEqual(json.loads((attempt / "prepared.json").read_text())["status"], "PREPARED")

        self.args.prepared = receipt["prepared"]
        with patch("n2m.simulation.prepare_files", side_effect=AssertionError("must not prepare again")):
            record = self.run_stage()
        self.assertEqual((record["status"], record["cache"]), ("PASS", "BUILT"))
        self.assertEqual(record["prepared"], {"id": receipt["prepared"], "mode": "adopted",
                                              "prepared_started": receipt["started"], "prepared_finished": receipt["finished"]})
        self.assertEqual(record["timing"]["prepare_seconds"], receipt["prepare_seconds"])
        self.assertEqual(set(record["timing"]), {"prepare_seconds", "build_seconds", "run_seconds", "locked_seconds"})
        self.assertGreater(record["timing"]["locked_seconds"], 0)
        self.assertIn("lock_acquired", record)
        self.assertIn((attempt / "fixture.bin").relative_to(self.root).as_posix(), record["artifacts"])
        self.assertTrue((attempt / "adopted.json").is_file())
        self.assertEqual(len(self.sim.calls), 2)
        # Single use: the same prepared attempt is refused by name afterwards.
        self.args.rebuild = True
        with self.assertRaisesRegex(ValueError, f"prepared attempt {receipt['prepared']}: already adopted"):
            self.run_stage()
        self.assertEqual(len(self.sim.calls), 2)

    def test_changed_inputs_files_or_request_refuse_the_prepared_attempt(self):
        with patch("n2m.simulation.prepare_files", side_effect=self.fake_prepare_files):
            receipt = prepare(self.root, self.build, self.args, self.sim)
        attempt = self.build / "sim/test/builder-smoke/verilator/attempts" / receipt["prepared"]
        self.args.prepared = receipt["prepared"]
        source = self.root / "src/dv/builder/builder_smoke.sv"
        original = source.read_bytes()
        source.write_bytes(original + b"\n// edited after preparation\n")
        with self.assertRaisesRegex(ValueError, "inputs changed: src/dv/builder/builder_smoke.sv"):
            self.run_stage()
        source.write_bytes(original)
        (attempt / "fixture.bin").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "inputs changed: .*attempts/.*/fixture.bin"):
            self.run_stage()
        (attempt / "fixture.bin").write_bytes(b"prepared fixture")
        (attempt / "extra.bin").write_bytes(b"added")
        with self.assertRaisesRegex(ValueError, "inputs changed: .*/extra.bin"):
            self.run_stage()
        (attempt / "extra.bin").unlink()
        self.args.seed = 2
        with self.assertRaisesRegex(ValueError, "prepared for builder-smoke/verilator seed 1"):
            self.run_stage()
        self.args.seed = 1
        self.sim.info = {**self.sim.info, "tools": {"verilator": {"path": "/other", "version": "Verilator 5.999"}}}
        with self.assertRaisesRegex(ValueError, "tools or options changed since preparation"):
            self.run_stage()
        self.sim.info = FakeSimulator().info
        incomplete = json.loads((attempt / "prepared.json").read_text())
        atomic_json(attempt / "prepared.json", {**incomplete, "status": "PREPARING"})
        with self.assertRaisesRegex(ValueError, "no complete preparation receipt \\(status PREPARING\\)"):
            self.run_stage()
        self.args.prepared = "not-an-id"
        with self.assertRaisesRegex(ValueError, "not a prepared attempt id"):
            self.run_stage()
        # Nothing ran and no stage record was published by any refusal.
        self.assertEqual(self.sim.calls, [])
        self.assertFalse((self.build / "sim/test/builder-smoke/verilator/result.json").exists())
        # A failed preparation leaves a FAIL receipt no run can adopt.
        with patch("n2m.simulation.prepare_files", side_effect=ValueError("fixture build failed")):
            failed = prepare(self.root, self.build, self.args, self.sim)
        self.assertEqual((failed["status"], failed["error"]), ("FAIL", "fixture build failed"))
        self.args.prepared = failed["prepared"]
        with self.assertRaisesRegex(ValueError, "no complete preparation receipt \\(status FAIL\\)"):
            self.run_stage()

    def test_cli_prepare_takes_no_tag_lock_and_writes_no_tag_records(self):
        latest = self.root / "workdir/latest.txt"
        latest.write_text("elsewhere\n")
        with patch("n2m.cli.Simulator", return_value=self.sim), patch("n2m.cli.git_state", return_value={}), \
                patch("n2m.simulation.prepare_files", side_effect=self.fake_prepare_files), \
                workspace(self.root, "prep") as held, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            # Another command holds the tag for its whole run; preparation
            # still completes beside it.
            self.assertEqual(main(["sim", "prepare", "builder-smoke", "--tag", "prep", "--json"], self.root), 0)
            self.assertEqual(sorted(p.name for p in held.iterdir()), [".lock", "sim"])
        report = json.loads(output.getvalue())
        self.assertEqual((report["status"], report["tag"]), ("PASS", "prep"))
        self.assertTrue((self.root / report["prepared_record"]).is_file())
        self.assertEqual(sorted(p.name for p in held.iterdir()), ["sim"])
        self.assertEqual(latest.read_text(), "elsewhere\n")
        self.assertEqual(self.sim.calls, [])
        with patch("n2m.cli.Simulator", return_value=self.sim), patch("n2m.cli.git_state", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["sim", "test", "builder-smoke", "--tag", "prep", "--prepared", report["prepared"], "--json"], self.root), 0)
        result = json.loads(output.getvalue())
        self.assertEqual((result["status"], result["prepared"]["mode"]), ("PASS", "adopted"))
        self.assertEqual(read_json(held / "manifest.json")["prepared"]["id"], report["prepared"])
        with patch("n2m.cli.Simulator", return_value=self.sim), patch("n2m.cli.git_state", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["sim", "test", "builder-smoke", "--tag", "prep", "--prepared", report["prepared"], "--rebuild", "--json"], self.root), 1)
        refused = json.loads(output.getvalue())
        self.assertIn("already adopted", refused["error"])
        # The refusal is a stage failure like any preparation failure.
        self.assertEqual(read_json(held / "sim/test/builder-smoke/verilator/result.json")["status"], "FAIL")

    def test_cli_json_has_no_human_progress_and_powershell_quotes_paths(self):
        with patch("n2m.cli.Simulator", return_value=self.sim), \
                patch("n2m.cli.git_state", return_value={}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["sim", "test", "builder-smoke", "--tag", "machine", "--json"],
                                  self.root), 0)
        payload = output.getvalue()
        self.assertEqual(json.loads(payload)["status"], "PASS")
        self.assertNotIn("[....]", payload)
        self.assertEqual(powershell_command(["python", "--sof", "a path/with an 'apostrophe/design.sof"]),
                         "python --sof 'a path/with an ''apostrophe/design.sof'")


if __name__ == "__main__":
    unittest.main()
