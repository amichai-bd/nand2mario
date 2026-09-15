"""Verilator discovery, command shape, transcript checks, retired targets and
per-OS command ownership; host doubles only, never RTL evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_builder
from n2m import verilator
from n2m.cli import FPGA_HOST, SIMULATION_HOST, main
from n2m.records import read_json
from n2m.simulation import RETIRED_REASON, load_target
from n2m.simulator import Simulator, ToolError

VERSION = "Verilator 5.052 2026-09-05 rev v5.052"
SIGNATURE = "count cycle=3 expected=7 actual=3 seed=1"


class DiscoveryTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp

    def banner(self, argv, **_):
        return SimpleNamespace(returncode=0, stdout=VERSION if argv[0].endswith("verilator") else "g++ (GCC) 13.3.0\n")

    def test_explicit_directory_hashes_release_and_no_fallback(self):
        directory = self.root / "tools with spaces"
        directory.mkdir()
        (directory / "verilator").write_bytes(b"wrapper")
        def which(candidate):
            return candidate if Path(candidate).is_file() else "/usr/bin/g++" if candidate == "g++" else None
        with patch("n2m.simulator.shutil.which", side_effect=which), \
                patch.object(Simulator, "run", side_effect=self.banner):
            with patch("n2m.simulator.Path.read_bytes", return_value=b"bytes"):
                simulator = Simulator("verilator", verilator_bin=str(directory))
            self.assertEqual(simulator.backend, "verilator")
            identity = simulator.info["tools"]["verilator"]
            self.assertEqual((identity["version"], identity["release"]), (VERSION, "5.052"))
            self.assertEqual(Path(identity["path"]).parent, directory.resolve())
            self.assertIn("cxx", simulator.info["tools"])
        for backend, directory_arg in (("questa", str(directory)), ("verilator", ""),
                                       ("verilator", str(directory / "absent"))):
            with self.assertRaises(ToolError):
                Simulator(backend, verilator_bin=directory_arg)
        for backend in ("questa", "icarus", "auto"):
            with self.assertRaisesRegex(ToolError, "only Verilator"):
                Simulator(backend)

    def test_bad_banner_warning_and_missing_compiler_fail_discovery(self):
        with patch("n2m.simulator.shutil.which", return_value=str(self.root / "tools/build.py")):
            for output, code in (("not a simulator", 0), (VERSION, 1), (VERSION + "\n%Warning-X: bad", 0)):
                with patch.object(Simulator, "run", return_value=SimpleNamespace(returncode=code, stdout=output)):
                    with self.assertRaises(ToolError):
                        Simulator("verilator")
            with patch.object(Simulator, "run", side_effect=ToolError("timed out", "partial")):
                with self.assertRaises(ToolError):
                    Simulator("verilator")
        with patch("n2m.simulator.shutil.which", return_value=None):
            with self.assertRaisesRegex(ToolError, "missing verilator"):
                Simulator()

    def test_retired_cli_options_fail_parsing(self):
        for option in (["--sim", "questa"], ["--sim", "auto"], ["--questa-bin", "old"],
                       ["--intel-sim-lib", "old"], ["--iverilog", "old"]):
            with self.subTest(option=option), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    main(["sim", "test", "builder-smoke", *option], self.root)
                self.assertEqual(caught.exception.code, 2)
        for command in (["regress", "pre-merge"], ["tests", "run", "--level", "0"]):
            with self.subTest(command=command), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main(command + ["--questa-bin", "old"], self.root)

    def test_cli_selection_forwards_the_tool_directory(self):
        self.sim = test_builder.FakeSimulator()
        command = ["sim", "test", "builder-smoke", "--sim", "verilator", "--verilator-bin", "tools with spaces",
                   "--tag", "verilator-cli", "--json"]
        with patch("n2m.cli.Simulator", return_value=self.sim) as discover, \
                patch("n2m.cli.git_state", return_value={}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(command, self.root), 0)
        self.assertEqual(discover.call_args.args, ("verilator",))
        self.assertEqual(discover.call_args.kwargs, {"verilator_bin": "tools with spaces"})
        report = json.loads(output.getvalue())
        self.assertEqual((report["simulator"], report["os"]), ("verilator", report["provenance"]["os"]))


class DiagnosticTests(unittest.TestCase):
    def test_warnings_and_errors_fail_without_an_expected_failure(self):
        self.assertIsNone(verilator.diagnostic("PASS builder-smoke seed=1 checks=22\n- x.sv:37: Verilog $finish"))
        for output in ("%Warning-WIDTH: x.sv:3: Operator ASSIGN expects 4 bits",
                       "[100] %Warning: late", "     0.00ns WARNING  cocotb.regression  test failed",
                       "%Error: x.sv:1: syntax error", "[40000] %Fatal: x.sv:31: Assertion failed",
                       "     -.--ns ERROR    gpi  no users", "CRITICAL cocotb  boom"):
            with self.subTest(output=output):
                self.assertIsNotNone(verilator.diagnostic("ok\n" + output))

    def test_expected_failure_allows_only_its_own_fatal_and_stop(self):
        fatal = f"[40000] %Fatal: builder_smoke.sv:31: Assertion failed in builder_smoke: {SIGNATURE}\n"
        stop = "%Error: /repo/src/dv/builder/builder_smoke.sv:31: Verilog $stop\nAborting...\n"
        self.assertIsNone(verilator.diagnostic(fatal + stop, SIGNATURE))
        self.assertEqual(verilator.diagnostic(fatal + stop), "unexpected simulator diagnostic")
        self.assertEqual(verilator.diagnostic(fatal + "%Error: x.sv:2: another\n", SIGNATURE),
                         "unexpected simulator diagnostic")
        self.assertEqual(verilator.diagnostic(fatal + "%Warning-X: y\n", SIGNATURE), "unexplained simulator warning")


PEER_STOP = ("  2160.00ns WARNING  cocotb.regression                  driver.peer failed\n"
             "                                                        cocotb.regression.SimFailure: cocotb expected it would "
             "shut down the simulation, but the simulation ended prematurely. This could be due to an assertion failure.\n")


class PeerDiagnosticTests(unittest.TestCase):
    def test_cocotb_report_of_the_expected_fatal_is_part_of_that_fatal(self):
        fatal = "[2160000] %Fatal: tb.sv:36: Assertion failed in tb.endpoint: PEER_ECHO_FAULT seq=2\n%Error: /r/tb.sv:36: Verilog $stop\nAborting...\n"
        self.assertIsNone(verilator.diagnostic(fatal + PEER_STOP, "PEER_ECHO_FAULT seq=2", peer="driver"))
        # Only a driver target, only with its expected fatal present, and only for its own module.
        self.assertEqual(verilator.diagnostic(fatal + PEER_STOP, "PEER_ECHO_FAULT seq=2"), "unexplained simulator warning")
        self.assertEqual(verilator.diagnostic(PEER_STOP, "PEER_ECHO_FAULT seq=2", peer="driver"), "unexplained simulator warning")
        self.assertEqual(verilator.diagnostic(fatal + PEER_STOP.replace("driver.peer", "other.peer"), "PEER_ECHO_FAULT seq=2", peer="driver"),
                         "unexplained simulator warning")
        self.assertEqual(verilator.diagnostic(fatal + PEER_STOP + "  9.00ns WARNING  cocotb.regression  deprecated\n",
                                              "PEER_ECHO_FAULT seq=2", peer="driver"), "unexplained simulator warning")


class CommandTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp

    def test_systemverilog_target_builds_with_timing_and_runs_the_seeded_harness(self):
        target, _ = load_target(self.root, "builder-smoke-fail")
        attempt = self.build / "attempt"
        compiler = self.build / "compile"
        for folder in (attempt / "waves", compiler):
            folder.mkdir(parents=True)
        commands = verilator.commands(self.sim, self.root, target, 7, compiler, attempt)
        (build, build_cwd, build_log, expected), (run, run_cwd, run_log, run_expected) = commands
        self.assertEqual((build_cwd, build_log.name, expected), (compiler, "build.log", "zero"))
        for option in ("--timing", "--trace-fst", "--cc", "--exe", "--build"):
            self.assertIn(option, build)
        self.assertEqual(build[build.index("--x-initial") + 1], "unique")
        # Time-zero edges follow value changes only; the initialization-edge
        # emulation would clock every process once at time zero.
        self.assertNotIn("--x-initial-edge", build)
        self.assertEqual(build[build.index("--top-module") + 1], "builder_smoke")
        self.assertEqual(build[-1], verilator.HARNESS)
        harness = (compiler / verilator.HARNESS).read_text()
        self.assertIn(f'trace.open("{verilator.WAVES}")', harness)
        self.assertIn("nextTimeSlot", harness)
        self.assertNotIn("--vpi", build)
        self.assertEqual((run_cwd, run_log.name, run_expected), (attempt, "sim.log", "zero"))
        self.assertTrue(run[0].endswith("obj_dir/sim"))
        self.assertEqual(run[1:], ["+seed=7", "+verilator+seed+7", "+verilator+rand+reset+2", "+inject_failure"])

    def test_elaboration_args_are_verilated_in_and_kept_off_the_run(self):
        # Questa applied -g parameter overrides and +define+ macros at vsim
        # time; Verilator needs both at verilate time and the run never sees them.
        target, _ = load_target(self.root, "builder-smoke")
        target = {**target, "args": ["-gPRELOADED=1", "+define+PRELOADED", "-gBUILD_ID=128'h10", "+inject_failure", "+io_peek_samples=120"]}
        attempt = self.build / "attempt"
        (attempt / "waves").mkdir(parents=True)
        (build, *_), (run, *_) = verilator.commands(self.sim, self.root, target, 7, self.build, attempt)
        top = build.index("--top-module")
        self.assertEqual(build[top + 2:top + 5], ["-GPRELOADED=1", "+define+PRELOADED", "-GBUILD_ID=128'h10"])
        self.assertEqual(build[-1], verilator.HARNESS)
        self.assertEqual(run[1:], ["+seed=7", "+verilator+seed+7", "+verilator+rand+reset+2", "+inject_failure", "+io_peek_samples=120"])
        self.assertFalse(verilator.is_elaboration_arg("-g"))
        self.assertFalse(verilator.is_elaboration_arg("+defined"))

    def test_identical_retained_harness_is_left_untouched_and_a_stale_one_rewritten(self):
        target, _ = load_target(self.root, "builder-smoke")
        attempt = self.build / "attempt"
        compiler = self.build / "compile"
        for folder in (attempt / "waves", compiler):
            folder.mkdir(parents=True)
        harness = compiler / verilator.HARNESS
        verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        before = harness.stat().st_mtime_ns
        # A validator replays the plan against a retained attempt; the same
        # content must not rewrite the artifact.
        verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        self.assertEqual(harness.stat().st_mtime_ns, before)
        harness.write_text("// stale\n", encoding="utf-8")
        verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        self.assertEqual(harness.read_text(encoding="utf-8"), verilator.main_source("builder_smoke"))

    def test_python_target_builds_the_vpi_flow_and_traces_to_the_retained_wave(self):
        for owner in ("src/dv/python", "src/rtl/joypad", "src/rtl/interfaces", "src/rtl/common"):
            shutil.copytree(test_builder.ROOT / owner, self.root / owner, ignore=shutil.ignore_patterns("__pycache__"))
        target, _ = load_target(self.root, "python-joypad")
        runtime = {"library_dir": "/venv/cocotb/libs", "support": "/venv/cocotb/share/lib/verilator/verilator.cpp"}
        attempt = self.build / "attempt"
        (attempt / "waves").mkdir(parents=True)
        with patch("n2m.python_tb.prepare") as prepare:
            (build, *_), (run, *_) = verilator.commands(self.sim, self.root, target, 3, self.build, attempt, python_runtime=runtime)
        prepare.assert_called_once()
        self.assertIn("--vpi", build)
        self.assertIn("--public-flat-rw", build)
        self.assertIn("--timing", build)
        self.assertEqual(build[build.index("-LDFLAGS") + 1],
                         "-Wl,-rpath,/venv/cocotb/libs -L/venv/cocotb/libs -lcocotbvpi_verilator")
        self.assertEqual(build[-1], runtime["support"])
        self.assertEqual(run[1:4], ["--trace", "--trace-file", verilator.WAVES])
        self.assertIn("+verilator+seed+3", run)


    def test_driver_target_keeps_timing_under_the_vpi_flow_and_names_the_root(self):
        shutil.copytree(test_builder.ROOT / "src/dv/integration", self.root / "src/dv/integration",
                        ignore=shutil.ignore_patterns("__pycache__"))
        target, _ = load_target(self.root, "verilator-peer")
        runtime = {"library_dir": "/venv/cocotb/libs", "support": "/venv/cocotb/share/lib/verilator/verilator.cpp"}
        attempt = self.build / "attempt"
        (attempt / "waves").mkdir(parents=True)
        (build, *_), (run, *_) = verilator.commands(self.sim, self.root, target, 3, self.build, attempt, python_runtime=runtime)
        self.assertIn("--vpi", build)
        self.assertIn("--timing", build)
        self.assertEqual(build[-1], runtime["support"])
        self.assertEqual(run[1:4], ["--trace", "--trace-file", verilator.WAVES])
        self.assertEqual(run[-1], "+smoke_root=" + str(self.root))


class RecordTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def test_record_names_simulator_os_seed_waves_and_split_timing(self):
        with patch("n2m.simulation.platform.system", return_value="Linux"):
            record = self.run_stage()
        self.assertEqual((record["status"], record["simulator"], record["os"], record["seed"]), ("PASS", "verilator", "Linux", 1))
        self.assertEqual(record["waves"]["format"], "fst")
        self.assertIn(record["waves"]["path"], record["artifacts"])
        self.assertTrue(record["waves"]["path"].endswith("waves/simulation.fst"))
        self.assertEqual(set(record["timing"]), {"build_seconds", "run_seconds"})
        self.assertTrue(all("elapsed_seconds" in command for command in record["commands"]))
        self.assertTrue(any(path.startswith("workdir/builds/test/compile/verilator/builder-smoke/") for path in record["artifacts"]))

    def test_missing_retained_wave_fails(self):
        original = self.sim.run
        def run(argv, cwd=None, timeout=60, env=None):
            result = original(argv, cwd)
            if argv[0] != self.sim.compiler:
                (cwd / "waves/simulation.fst").unlink()
            return result
        self.sim.run = run
        result = self.run_stage()
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missing retained waves", result["error"])

    def test_expected_corruption_requires_full_signature_and_nonzero(self):
        for owner in ("src/rtl/display", "src/dv/display", "src/rtl/common"):
            shutil.copytree(Path(__file__).resolve().parents[3] / owner, self.root / owner)
        test_builder.migrate(self.root, "tile-pixel-corrupt")
        self.args.target = "tile-pixel-corrupt"
        signature = read_json(self.root / "src/dv/builder/targets.json")[self.args.target]["signature"]
        original = self.sim.run
        outcomes = {}
        def run(argv, cwd=None, timeout=60, env=None):
            result = original(argv, cwd)
            if argv[0] != self.sim.compiler:
                result.returncode, result.stdout = outcomes["code"], outcomes["output"]
            return result
        self.sim.run = run
        for code, output, expected in ((1, "MISMATCH unrelated", "FAIL"), (0, signature, "FAIL"),
                                       (1, f"[10] %Fatal: tb.sv:9: {signature}\n%Error: x: other\n", "FAIL"),
                                       (1, f"[10] %Fatal: tb.sv:9: {signature}\n%Error: /r/tb.sv:9: Verilog $stop\nAborting...\n", "PASS")):
            outcomes.update(code=code, output=output)
            self.args.rebuild = True
            self.assertEqual(self.run_stage()["status"], expected, output)
        self.args.rebuild = False
        self.assertEqual(self.run_stage()["cache"], "CACHED")

    def test_vendor_model_stays_questa_and_a_driver_needs_the_peer_module(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        pristine = dict(targets["builder-smoke"])
        (self.root / "driver.do").write_text("run -all\n")
        (self.root / "driver.py").write_text("import cocotb\n")
        access = ["tx_go", "finish_request"]
        for change, message in (({"vendor_model": "intel-memory"}, "vendor_model"),
                                ({"driver": {"script": "driver.do", "peer": "tools/build.py", "inputs": [], "access": access}}, "Verilator peer module"),
                                ({"driver": {"script": "driver.py", "peer": "tools/build.py", "inputs": []}}, "nonempty access list"),
                                ({"driver": {"script": "missing.py", "peer": "tools/build.py", "inputs": [], "access": access}}, "missing or out-of-tree driver input")):
            targets["builder-smoke"] = {**pristine, **change}
            registry.write_text(json.dumps(targets))
            with self.assertRaisesRegex(ValueError, message):
                load_target(self.root, "builder-smoke")
        # The retired Tcl script still validates on a questa target.
        targets["builder-smoke"] = {**pristine, "simulator": "questa",
                                    "driver": {"script": "driver.do", "peer": "tools/build.py", "inputs": []}}
        registry.write_text(json.dumps(targets))
        self.assertEqual(load_target(self.root, "builder-smoke")[0]["simulator"], "questa")
        targets["builder-smoke"] = {**pristine, "driver": {"script": "driver.py", "peer": "tools/build.py", "inputs": [], "access": access}}
        registry.write_text(json.dumps(targets))
        self.assertEqual(load_target(self.root, "builder-smoke")[0]["driver"]["access"], access)


class PreloadTests(unittest.TestCase):
    """The fixture pipeline on the Verilator stage: validation, preparation,
    verification before launch, the record and fingerprint invalidation."""
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def fixture_tree(self):
        for owner in ("src/dv/preload", "src/dv/integration", "tools/sw"):
            shutil.copytree(test_builder.ROOT / owner, self.root / owner, ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "src/sw/generated").mkdir(parents=True)
        shutil.copy(test_builder.ROOT / "src/sw/generated/interfaces.inc", self.root / "src/sw/generated/interfaces.inc")
        self.args.target = "preload-fixture"
        signature = read_json(self.root / "src/dv/builder/targets.json")["preload-fixture"]["signature"]
        original = self.sim.run
        def run(argv, cwd=None, timeout=60, env=None):
            result = original(argv, cwd)
            if argv[0] != self.sim.compiler:
                result.stdout = signature
                # The run's working directory is the attempt that holds the
                # prepared files, so SIM_INIT_FILE and $readmemh paths resolve.
                self.assertTrue((cwd / "preload.json").is_file(), cwd)
                for name in ("preload-rom.mif", "preload-presence.mif", "preload-crc.hex"):
                    self.assertTrue((cwd / name).is_file(), name)
            return result
        self.sim.run = run

    def test_validator_accepts_preload_under_verilator_and_rejects_unregistered_or_undeclared(self):
        self.fixture_tree()
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        target = targets["preload-fixture"]
        self.assertEqual(load_target(self.root, "preload-fixture")[0]["preload"], "integration")
        for change, message in (({"preload": "unreviewed"}, "no registered fixture builder"),
                                ({"preload_inputs": []}, "preload_inputs must list"),
                                ({"preload_inputs": [p for p in target["preload_inputs"] if p != "src/dv/integration/program.asm"]},
                                 "omit fixture inputs: src/dv/integration/program.asm"),
                                ({"preload_inputs": target["preload_inputs"] + ["src/dv/absent.py"]}, "missing or out-of-tree preload input")):
            targets["preload-fixture"] = {**target, **change}
            registry.write_text(json.dumps(targets))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                load_target(self.root, "preload-fixture")
        # The builder's own import closure must be declared even when no fixed input names it.
        targets["preload-fixture"] = {**target, "preload_inputs": [p for p in target["preload_inputs"] if p != "tools/sw/linker.py"]}
        registry.write_text(json.dumps(targets))
        with patch("n2m.python_tb.fixture_inputs", return_value=set()):
            with self.assertRaisesRegex(ValueError, "undeclared transitive fixture inputs: tools/sw/linker.py"):
                load_target(self.root, "preload-fixture")
        pristine = dict(read_json(test_builder.ROOT / "src/dv/builder/targets.json")["builder-smoke"])
        targets["builder-smoke"] = {**pristine, "preload_inputs": ["tools/build.py"]}
        registry.write_text(json.dumps(targets))
        with self.assertRaisesRegex(ValueError, "preload_inputs requires a preload"):
            load_target(self.root, "builder-smoke")

    def test_stage_prepares_verifies_before_launch_and_records_the_fixture(self):
        self.fixture_tree()
        record = self.run_stage()
        self.assertEqual((record["status"], record["cache"]), ("PASS", "BUILT"))
        preload = record["preload"]
        self.assertEqual((preload["mode"], preload["title"], preload["image_bytes"]), ("preloaded-execution", "N2M SMOKE", 32768))
        self.assertEqual(set(preload["files"]), {"preload-rom.mif", "preload-presence.mif", "preload-crc.hex"})
        attempt = self.root / Path(record["waves"]["path"]).parent.parent
        self.assertEqual(preload, read_json(attempt / "preload.json"))
        for name in ("program.gb", "preload.json", "preload-rom.mif", "preload-crc.hex", "fixture-preflight.json"):
            self.assertIn((attempt / name).relative_to(self.root).as_posix(), record["artifacts"])
        self.assertIn("src/dv/integration/program.asm", record["inputs"])
        self.assertIn("tools/sw/linker.py", record["inputs"])
        # A prepared file changed between preparation and the launch check fails
        # the attempt before the run starts; preparation's own checks passed.
        from n2m import preload
        real_verify, built = preload.verify, []
        original = self.sim.run
        def run(argv, cwd=None, timeout=60, env=None):
            built.append(argv[0] == self.sim.compiler)
            return original(argv, cwd)
        def verify(attempt):
            if built:
                raise ValueError("preload file changed after preparation: preload-crc.hex")
            return real_verify(attempt)
        self.sim.run = run
        with patch("n2m.preload.verify", side_effect=verify):
            self.args.rebuild = True
            failed = self.run_stage()
        self.assertEqual(failed["status"], "FAIL")
        self.assertIn("preload file changed", failed["error"])
        self.assertEqual(built, [True], "the run never launched")
        self.assertNotIn("preload", failed)

    def test_changed_fixture_input_invalidates_cache_reuse(self):
        self.fixture_tree()
        first = self.run_stage()
        self.assertEqual((first["status"], first["cache"]), ("PASS", "BUILT"))
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        source = self.root / "src/dv/integration/program.asm"
        source.write_text(source.read_text(encoding="utf-8") + "; fixture comment\n", encoding="utf-8")
        second = self.run_stage()
        self.assertEqual((second["status"], second["cache"]), ("PASS", "BUILT"))
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(self.run_stage()["cache"], "CACHED")

    def test_mooneye_tool_identity_enters_the_fingerprint(self):
        import hashlib
        from sw.package import package
        from n2m import preload
        for owner in ("src/dv/preload", "src/dv/mooneye", "tools/sw"):
            shutil.copytree(test_builder.ROOT / owner, self.root / owner, ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "src/rtl/ppu").mkdir(parents=True)
        shutil.copy(test_builder.ROOT / "src/rtl/ppu/GPL-3.0.txt", self.root / "src/rtl/ppu/GPL-3.0.txt")
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        targets["mooneye-fixture"] = {**targets["preload-fixture"], "preload": "mooneye-reg-f",
                                      "preload_inputs": ["src/dv/mooneye/pins.json", "src/dv/mooneye/THIRD_PARTY.md",
                                                         "src/rtl/ppu/GPL-3.0.txt", "tools/sw/expressions.py",
                                                         "tools/sw/linker.py", "tools/sw/objects.py", "tools/sw/package.py"]}
        registry.write_text(json.dumps(targets))
        self.args.target = "mooneye-fixture"
        signature = targets["mooneye-fixture"]["signature"]
        original = self.sim.run
        def run(argv, cwd=None, timeout=60, env=None):
            result = original(argv, cwd)
            if argv[0] != self.sim.compiler:
                result.stdout = signature
            return result
        self.sim.run = run
        image = package({"image": bytes([255]) * 32768, "entry": 0x200}, "ORIGINAL", 1)
        def prepare(target, attempt, root=None, fixture_tools=None):
            self.assertEqual(target["preload"], "mooneye-reg-f")
            self.assertIn(fixture_tools["tools"]["gcc"], ("/usr/bin/gcc", "/opt/gcc"))
            (attempt / "program.gb").write_bytes(image)
            preload.prepare(image, hashlib.sha256(image).hexdigest(), attempt)
        identities = [{"backend": "wsl", "tools": {"gcc": "/usr/bin/gcc"}, "files": {}},
                      {"backend": "wsl", "tools": {"gcc": "/opt/gcc"}, "files": {"changed": "1"}}]
        with patch("n2m.python_tb.prepare", side_effect=prepare), \
                patch("n2m.mooneye.tool_identity", return_value=identities[0]) as identity:
            first = self.run_stage()
            self.assertEqual((first["status"], first["cache"]), ("PASS", "BUILT"))
            self.assertEqual(first["options"]["fixture_tools"], identities[0])
            self.assertEqual(self.run_stage()["cache"], "CACHED")
            identity.return_value = identities[1]
            second = self.run_stage()
        self.assertEqual((second["status"], second["cache"]), ("PASS", "BUILT"))
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(second["options"]["fixture_tools"], identities[1])


class RetiredTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def test_missing_or_unknown_simulator_is_rejected(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        for value in (None, "icarus", "Verilator", 1):
            targets["builder-smoke"]["simulator"] = value
            if value is None:
                del targets["builder-smoke"]["simulator"]
            registry.write_text(json.dumps(targets))
            with self.assertRaisesRegex(ValueError, "must declare simulator as one of verilator, questa"):
                load_target(self.root, "builder-smoke")

    def test_questa_target_is_skipped_by_name_without_discovery(self):
        # The test copy marks tile-pixel retired whatever the registry says now.
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        targets["tile-pixel"]["simulator"] = "questa"
        registry.write_text(json.dumps(targets))
        self.args.target = "tile-pixel"
        with self.assertRaisesRegex(ValueError, "missing or out-of-tree source"):
            self.run_stage()
        for owner in ("src/rtl/display", "src/dv/display", "src/rtl/common"):
            shutil.copytree(test_builder.ROOT / owner, self.root / owner)
        record = self.run_stage()
        self.assertEqual((record["status"], record["reason"], record["simulator"]), ("SKIPPED", RETIRED_REASON, "questa"))
        self.assertIn("os", record)
        self.assertEqual(self.sim.calls, [])
        self.assertEqual(read_json(self.build / "sim/test/tile-pixel/result.json")["status"], "SKIPPED")
        # The CLI reports it the same way, exits 2, and never discovers a simulator.
        with patch("n2m.cli.Simulator", side_effect=AssertionError("discovered")), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["sim", "test", "tile-pixel", "--tag", "retired"], self.root)
        self.assertEqual(code, 2)
        self.assertIn(f"tile-pixel: SKIPPED {RETIRED_REASON}", output.getvalue())
        self.assertEqual(read_json(self.root / "workdir/builds/retired/manifest.json")["status"], "SKIPPED")
        self.assertFalse((self.root / "workdir/latest.txt").exists())


class HostOwnershipTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp

    def run_cli(self, system, *argv):
        with patch("n2m.cli.platform.system", return_value=system), \
                patch("n2m.cli.Simulator", side_effect=AssertionError("discovered")), \
                patch("n2m.cli.build_fpga", side_effect=AssertionError("built")), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main([*argv, "--json"], self.root)
        return code, json.loads(output.getvalue())

    def test_windows_refuses_simulation_commands(self):
        for argv in (["sim", "test", "builder-smoke", "--tag", "w1"], ["sim", "preflight", "python-joypad", "--tag", "w2"],
                     ["tests", "run", "--level", "0", "--tag", "w3"], ["regress", "pre-merge", "--tag", "w4"]):
            with self.subTest(argv=argv):
                code, report = self.run_cli("Windows", *argv)
                self.assertEqual(code, 1)
                self.assertEqual((report["status"], report["error"], report["os"]), ("FAIL", SIMULATION_HOST, "Windows"))
                self.assertFalse((self.root / "workdir/builds" / argv[-1]).exists())

    def test_linux_refuses_fpga_commands(self):
        for argv in (["fpga", "build", "smoke", "--quartus-bin", "tools", "--tag", "l1"],
                     ["fpga", "program", "--sof", "x.sof", "--quartus-bin", "tools", "--tag", "l2"]):
            with self.subTest(argv=argv):
                code, report = self.run_cli("Linux", *argv)
                self.assertEqual(code, 1)
                self.assertEqual((report["status"], report["error"], report["os"]), ("FAIL", FPGA_HOST, "Linux"))

    def test_each_host_still_runs_its_own_commands(self):
        with patch("n2m.cli.platform.system", return_value="Windows"), \
                patch("n2m.cli.build_fpga", return_value={"status": "PASS"}), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["fpga", "build", "smoke", "--quartus-bin", "tools", "--tag", "own", "--json"], self.root), 0)
        self.assertEqual(json.loads(output.getvalue())["os"], "Windows")
        with patch("n2m.cli.platform.system", return_value="Linux"), \
                patch("n2m.cli.Simulator", return_value=test_builder.FakeSimulator()), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["sim", "test", "builder-smoke", "--tag", "own-sim", "--json"], self.root), 0)
        self.assertEqual(json.loads(output.getvalue())["os"], "Linux")


if __name__ == "__main__":
    unittest.main()
