"""Native Questa discovery, command, diagnostics and cache tests using doubles."""
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_builder
from n2m.cli import main
from n2m.records import read_json
from n2m.simulator import (QUESTA_LICENSE, QUESTA_LICENSE_PROBE, Simulator, ToolError,
                          questa_license)


class FakeQuesta(test_builder.FakeSimulator):
    backend, compiler, runtime = "questa", "vlog", "vsim"

    def __init__(self):
        super().__init__()
        self.info = {"backend": "questa", "tools": {
            name: {"path": f"/tools/{name}", "version": "Questa 2025.2"}
            for name in ("vlib", "vmap", "vlog", "vsim")}}
        self.tools = {name: name for name in ("vlib", "vmap", "vlog", "vsim")}
        self.output = "PASS builder-smoke\nErrors: 0, Warnings: 0"
        self.exit_code = 0

    def run(self, argv, cwd=None, **_):
        self.calls.append(argv)
        if argv[0] == "vlib":
            (cwd / argv[1]).mkdir(exist_ok=True)
        if argv[0] == "vmap" and "-c" in argv:
            (cwd / "modelsim.ini").write_text("local mappings")
        if argv[0] == self.compiler:
            (cwd / "work").mkdir(exist_ok=True)
            (cwd / "work/design.bin").write_text("compiled")
        if argv[0] != self.runtime:
            return SimpleNamespace(returncode=0, stdout="Errors: 0, Warnings: 0")
        if self.timeout:
            raise ToolError("runtime timed out", "partial Questa transcript")
        (cwd / "waves/simulation.wlf").write_text("wave")
        (cwd / "waves/smoke.vcd").write_text("wave")
        return SimpleNamespace(returncode=self.exit_code, stdout=self.output)


class QuestaTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def test_explicit_discovery_hashes_every_tool_and_never_falls_back(self):
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
            # Three -version banners (vlib has none) and the vsim license probe.
            self.assertEqual(len(run.call_args_list), 4)
            self.assertEqual(run.call_args_list[-1].args[0][1:], list(QUESTA_LICENSE_PROBE))
            self.assertTrue(simulator.info["discovery"][-1]["licensed"])
            self.assertEqual(set(simulator.info["tools"]), {"vlib", "vmap", "vlog", "vsim"})
            first_hash = simulator.info["tools"]["vsim"]["sha256"]
            (directory / ("vsim" + suffix)).write_bytes(b"changed")
            self.assertNotEqual(first_hash, Simulator("questa", questa_bin=str(directory)).info["tools"]["vsim"]["sha256"])
            (directory / ("vlog" + suffix)).unlink()
            with self.assertRaisesRegex(ToolError, "missing vlog"):
                Simulator("questa", questa_bin=str(directory))
            self.assertTrue(all(Path(call.args[0]).parent == directory for call in find.call_args_list))
        for directory_arg in ("", str(directory / "absent")):
            with self.assertRaises(ToolError):
                Simulator("questa", questa_bin=directory_arg)
        with self.assertRaisesRegex(ToolError, "--verilator-bin applies only"):
            Simulator("questa", verilator_bin=str(directory))

    def test_bad_banner_diagnostic_and_timeout_fail_discovery(self):
        with patch("n2m.simulator.shutil.which", return_value=str(self.root / "tools/build.py")):
            for output, code in (("Questa", 1), ("Other tool", 0), ("Questa\nWarning: bad", 0)):
                with patch.object(Simulator, "run", return_value=SimpleNamespace(returncode=code, stdout=output)):
                    with self.assertRaises(ToolError):
                        Simulator("questa")
            with patch.object(Simulator, "run", side_effect=ToolError("timed out", "partial")):
                with self.assertRaises(ToolError):
                    Simulator("questa")

    def test_isolated_commands_backend_cache_and_legacy_mirror(self):
        verilator = self.run_stage()
        self.sim = FakeQuesta()
        first = self.run_stage()
        self.assertEqual((first["status"], first["cache"]), ("PASS", "BUILT"))
        self.assertNotEqual(verilator["authoritative_result"], first["authoritative_result"])
        self.assertIn("/questa/", first["authoritative_result"])
        macro = next(path for path in first["artifacts"] if path.endswith("run.do"))
        self.assertIn("runStatus -full", (self.root / macro).read_text())
        command = first["commands"][-1]["argv"]
        self.assertEqual(command[-2:], ["-do", "do run.do"])
        self.assertEqual(command[command.index("-onfinish") + 1], "stop")
        mirror = read_json(self.build / "sim/test/builder-smoke/result.json")
        self.assertEqual((mirror["simulator"], mirror["authoritative_result"]),
                         ("questa", first["authoritative_result"]))
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        # The generic reader remains compatible, but it has no cache authority.
        (self.build / "sim/test/builder-smoke/result.json").write_text("corrupt")
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        self.assertEqual(read_json(self.build / "sim/test/builder-smoke/result.json")["simulator"], "questa")
        self.sim.info["tools"]["vsim"]["version"] = "Questa changed"
        self.assertEqual(self.run_stage()["cache"], "BUILT")

    def test_strict_diagnostics_timeout_and_expected_failure(self):
        self.sim = FakeQuesta()
        self.assertEqual(self.run_stage()["status"], "PASS")
        self.args.rebuild = True
        for output in ("PASS builder-smoke\nWarning: bad", "PASS builder-smoke\nWarnings: 1",
                       "PASS builder-smoke\n** Error: bad", "normal exit without signature"):
            self.sim.output = output
            self.assertEqual(self.run_stage()["status"], "FAIL")
        self.sim.timeout = True
        failed = self.run_stage()
        self.assertEqual(failed["status"], "FAIL")
        self.assertTrue(any("partial Questa transcript" in (self.root / path).read_text()
                            for path in failed["artifacts"] if path.endswith("sim.log")))
        self.sim.timeout = False
        self.args.target = "builder-smoke-fail"
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        signature = "count cycle=3 expected=7 actual=3 seed=1"
        targets[self.args.target].update(expected_exit="nonzero", signature=signature)
        registry.write_text(json.dumps(targets))
        self.sim.exit_code, self.sim.output = 1, f"** Fatal: {signature}\nErrors: 1, Warnings: 0"
        result = self.run_stage()
        self.assertEqual(result["status"], "PASS", result.get("error"))

    def test_windows_cli_forwards_selected_tool_directory_and_failure_path(self):
        self.sim = FakeQuesta()
        command = ["sim", "test", "builder-smoke", "--sim", "questa",
                   "--questa-bin", "tools with spaces", "--tag", "questa-cli", "--json"]
        with patch("n2m.cli.platform.system", return_value="Windows"), \
                patch("n2m.cli.Simulator", return_value=self.sim) as discover, \
                patch("n2m.cli.git_state", return_value={}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(command, self.root), 0)
            self.assertEqual(discover.call_args.args, ("questa",))
            # `root` travels with every discovery so Verilator can fall back to
            # the repository's pinned installation; Questa never uses it.
            self.assertEqual(discover.call_args.kwargs,
                             {"verilator_bin": None, "questa_bin": "tools with spaces",
                              "root": self.root})
            with patch("n2m.cli.Simulator", side_effect=ToolError("missing vsim", "partial discovery")):
                self.assertEqual(main(command + ["--rebuild"], self.root), 1)
        current = self.root / "workdir/builds/questa-cli/sim/test/builder-smoke/questa/result.json"
        mirror = self.root / "workdir/builds/questa-cli/sim/test/builder-smoke/result.json"
        self.assertEqual(read_json(current)["status"], "FAIL")
        self.assertEqual(read_json(mirror)["authoritative_result"], current.relative_to(self.root).as_posix())


# Measured vsim transcripts, captured on this host from
# `vsim -c -nolog -lic_noqueue -do "quit -f"`. Every failed startup checkout ends
# with the same generic pair whatever the cause, so each fixture carries it.
TERMINAL = ("Unable to checkout a license.  Vsim is closing.\n"
            "** Error: Invalid license environment. Application closing.\n")
# Neither license variable set. Also what LM_LICENSE_FILE or MGLS_LICENSE_FILE
# alone produces: vsim reads neither, so it still reports SALT unset.
UNSET_VSIM = (
    "Unable to find the license file.  It appears that your license file environment "
    "variable (SALT_LICENSE_SERVER) is not set correctly.\n" + TERMINAL)
# A variable IS set and the checkout failed. Byte-identical for an unreachable
# server, a nonexistent path, a garbage file and a valid-syntax file with a bogus
# signature, all four measured; the wording carries no cause beyond "it is set".
# vsim WRAPS it across two lines, so `lmutil lmdiag` lands on the second. A
# single-line fixture would let a per-line classifier pass while the tool slipped.
SET_BUT_UNUSABLE_VSIM = (
    "Unable to checkout a license. Make sure your license file environment variable "
    "(SALT_LICENSE_SERVER)\n"
    "is set correctly and then run 'lmutil lmdiag' to diagnose the problem.\n" + TERMINAL)
# QUESTA_LICENSE_PROXY set to an unreachable proxy.
PROXY_VSIM = (
    "Couldn't connect to proxy '1717@nonexistent.invalid'.\n"
    "** Fatal: Failed to initialize licensing environment with status 111.\n" + TERMINAL)
# This repository's real contention: one node-locked seat, already held. The
# recorded refusal is exit 12 with this wording (PR #455 review evidence, cited in
# wiki/blogs/2026-09-13-remote-fpga.md). Only the phrase and the exit are
# recorded, so nothing else is invented here; TERMINAL is appended in a separate
# case rather than assumed to be present.
BUSY_SEAT = "an instance of QuestaSim is already running\n"
BUSY_SEAT_EXIT = 12


class QuestaLicenseTests(unittest.TestCase):
    """vsim needs a runtime checkout; the banner and the compile tools do not."""

    def probe(self, output, returncode=4):
        calls = []

        def run(argv):
            calls.append(argv)
            return SimpleNamespace(returncode=returncode, stdout=output)

        try:
            return questa_license("/tools/vsim", run), None, calls
        except ToolError as error:
            return None, error, calls

    def assert_refused(self, output):
        record, error, calls = self.probe(output)
        self.assertIsNone(record)
        message = str(error)
        self.assertTrue(message.startswith(QUESTA_LICENSE + ": "), message)
        quoted = message[len(QUESTA_LICENSE) + 2:]
        # The quote is what vsim reported, never the generic closing line, and it
        # is whole: a wrapped cause is rejoined, so it never starts mid-sentence.
        self.assertNotIn("Invalid license environment", quoted)
        self.assertNotIn("Vsim is closing", quoted)
        self.assertNotIn("\n", quoted)
        self.assertTrue(quoted.endswith("."), quoted)
        self.assertEqual((error.record["exit_code"], error.record["licensed"]), (4, False))
        for absent in ("Windows", "PowerShell", "Linux", "operating system"):
            self.assertNotIn(absent, message)
        self.assertEqual(calls, [["/tools/vsim", *QUESTA_LICENSE_PROBE]])
        return quoted

    def assert_reaches_the_run(self, output, returncode=4):
        record, error, _ = self.probe(output, returncode)
        self.assertIsNone(error, f"refused: {error}")
        self.assertTrue(record["licensed"])
        return record

    def test_an_unset_license_variable_is_refused_by_license_not_by_host(self):
        quoted = self.assert_refused(UNSET_VSIM)
        self.assertTrue(quoted.startswith("Unable to find the license file"), quoted)

    def test_a_set_but_unusable_license_is_refused_with_its_whole_wrapped_cause(self):
        """Four measured causes share this output, so the refusal claims no more
        than vsim does: the variable is set and the checkout failed."""
        quoted = self.assert_refused(SET_BUT_UNUSABLE_VSIM)
        self.assertTrue(quoted.startswith("Unable to checkout a license."), quoted)
        # Rejoined across the wrap, so the second line is present and attached.
        self.assertIn("is set correctly and then run 'lmutil lmdiag'", quoted)

    def test_an_unreachable_license_proxy_is_refused(self):
        """Without this, a host with only QUESTA_LICENSE_PROXY set reached the run
        and failed there, which is what the probe exists to prevent."""
        quoted = self.assert_refused(PROXY_VSIM)
        self.assertTrue(quoted.startswith("Couldn't connect to proxy"), quoted)

    def test_this_repositorys_contended_seat_reaches_the_run(self):
        """The contention this repository actually has: one node-locked seat held
        by another run, refused with exit 12 and wording the probe does not match.
        It must reach the run, which reports the seat itself."""
        for output in (BUSY_SEAT, BUSY_SEAT + TERMINAL):
            with self.subTest(terminal=output.endswith(TERMINAL)):
                record = self.assert_reaches_the_run(output, BUSY_SEAT_EXIT)
                self.assertEqual(record["exit_code"], BUSY_SEAT_EXIT)

    def test_a_floating_seats_exhausted_host_would_be_misclassified(self):
        """A stated limit, pinned so it cannot change unnoticed.

        On a floating licence with every seat taken, `-lic_noqueue` turns the
        queue wait into the same validation failure a broken licence produces, and
        the vendor puts no distinction in the output, so such a host is refused.
        Not reachable on this repository's node-locked seat, whose refusal is the
        case above. If a future vsim distinguishes the two, this test fails and the
        classifier and the SPEC limit should both be revisited.
        """
        _, error, _ = self.probe(SET_BUT_UNUSABLE_VSIM)
        self.assertIsNotNone(error)

    def test_the_generic_closing_pair_alone_never_refuses(self):
        """It follows any failed checkout, so on its own it names no cause."""
        self.assert_reaches_the_run(TERMINAL)

    def test_refusal_requires_a_nonzero_exit_as_well_as_a_wording(self):
        """A vsim that exits 0 has a license, whatever its output mentions."""
        self.assert_reaches_the_run(UNSET_VSIM + "Reading pref.tcl\n# quit -f\n", returncode=0)
        # The same output with a nonzero exit does refuse, so neither half decides
        # alone and the exit code genuinely participates.
        _, error, _ = self.probe(UNSET_VSIM, returncode=4)
        self.assertIsNotNone(error)

    def test_the_probe_argv_stays_the_documented_one(self):
        """Pinned because each option carries a contract: `-c` forces the checkout,
        `quit -f` loads no design, `-nolog` writes no transcript into the caller's
        directory and `-lic_noqueue` never waits behind a busy server."""
        self.assertEqual(QUESTA_LICENSE_PROBE, ("-c", "-nolog", "-lic_noqueue", "-do", "quit -f"))

    def test_the_refusal_advises_only_variables_vsim_reads(self):
        """Measured: LM_LICENSE_FILE and MGLS_LICENSE_FILE are ignored, so naming
        them would send an operator to a setting that cannot work."""
        self.assertIn("SALT_LICENSE_SERVER", QUESTA_LICENSE)
        self.assertIn("QUESTA_LICENSE_PROXY", QUESTA_LICENSE)
        self.assertNotIn("LM_LICENSE_FILE", QUESTA_LICENSE)
        self.assertNotIn("MGLS_LICENSE_FILE", QUESTA_LICENSE)

    def test_a_licensed_vsim_passes_and_records_the_probe(self):
        record = self.assert_reaches_the_run("# quit\n", returncode=0)
        self.assertEqual((record["argv"], record["exit_code"]),
                         (["/tools/vsim", *QUESTA_LICENSE_PROBE], 0))

    def test_a_nonzero_exit_without_a_license_wording_is_recorded_not_refused(self):
        """The probe names a license it can prove absent or unusable. It does not
        second-guess a vsim whose own run reports the detail, so Windows keeps its
        existing behavior."""
        record = self.assert_reaches_the_run("** Error: something else entirely\n", returncode=1)
        self.assertEqual(record["exit_code"], 1)

    def test_preparation_discovers_the_tools_without_consulting_the_license(self):
        """`sim prepare` launches no vsim, so it must not need a checkout: the run
        that adopts the attempt is what does."""
        present = str(Path(__file__).resolve())

        def run_tool(argv):
            if "-version" in argv:
                return SimpleNamespace(returncode=0, stdout="Questa 2025.2")
            return SimpleNamespace(returncode=4, stdout=UNSET_VSIM)

        with patch("n2m.simulator.shutil.which", return_value=present), \
                patch.object(Simulator, "run", side_effect=run_tool) as run:
            simulator = Simulator("questa", require_license=False)
            self.assertFalse(simulator.info["license_required"])
            # Three -version banners and no probe.
            self.assertEqual(len(run.call_args_list), 3)
            for call in run.call_args_list:
                self.assertNotIn("-lic_noqueue", call.args[0])
            with self.assertRaises(ToolError):
                Simulator("questa")

    def test_a_host_without_questa_is_refused_by_the_missing_tool(self):
        """No Questa at all names the executable, not the license and not the host."""
        with patch("n2m.simulator.shutil.which", return_value=None):
            with self.assertRaisesRegex(ToolError, r"missing vlib; select the Questa tool directory explicitly"):
                Simulator("questa")
        # A host holding only the compile tools still names the absent vsim, so a
        # `lint questa` host is not mistaken for a simulation host.
        present = str(Path(__file__).resolve())
        with patch("n2m.simulator.shutil.which", side_effect=lambda candidate: (
                None if Path(candidate).stem == "vsim" else present)), \
                patch.object(Simulator, "run", return_value=SimpleNamespace(
                    returncode=0, stdout="Questa 2025.2")):
            with self.assertRaisesRegex(ToolError, r"missing vsim"):
                Simulator("questa")


if __name__ == "__main__":
    unittest.main()
