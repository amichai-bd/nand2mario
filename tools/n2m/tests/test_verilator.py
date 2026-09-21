"""Verilator discovery, command shape, target capabilities and host ownership."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_builder
from n2m import doctor, verilator, verilator_install
from n2m.cli import TOOLS_HOST, VERILATOR_HOST, main
from n2m.records import atomic_json, file_hash, read_json
from n2m.simulation import load_target
from n2m.simulator import Simulator, ToolError, verilator_executable

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
        for backend, directory_arg in (("verilator", ""),
                                       ("verilator", str(directory / "absent"))):
            with self.assertRaises(ToolError):
                Simulator(backend, verilator_bin=directory_arg)
        for backend in ("icarus", "auto"):
            with self.assertRaisesRegex(ToolError, "unsupported simulator"):
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
                Simulator("verilator")

    def test_unknown_cli_options_fail_parsing(self):
        for option in (["--sim", "auto"], ["--iverilog", "old"]):
            with self.subTest(option=option), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    main(["sim", "test", "builder-smoke", *option], self.root)
                self.assertEqual(caught.exception.code, 2)
        for command in (["regress", "pre-merge"], ["tests", "run", "--level", "0"]):
            with self.subTest(command=command), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(command + ["--questa-bin", "old", "--json"], self.root), 1)
                self.assertIn("--questa-bin applies only to --sim questa", output.getvalue())

    def test_cli_selection_forwards_the_tool_directory(self):
        self.sim = test_builder.FakeSimulator()
        command = ["sim", "test", "builder-smoke", "--sim", "verilator", "--verilator-bin", "tools with spaces",
                   "--tag", "verilator-cli", "--json"]
        with patch("n2m.cli.Simulator", return_value=self.sim) as discover, \
                patch("n2m.cli.git_state", return_value={}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(command, self.root), 0)
        self.assertEqual(discover.call_args.args, ("verilator",))
        self.assertEqual(discover.call_args.kwargs,
                         {"verilator_bin": "tools with spaces", "questa_bin": None, "root": self.root})
        report = json.loads(output.getvalue())
        self.assertEqual((report["simulator"], report["os"]), ("verilator", report["provenance"]["os"]))


class PinnedInstallationTests(unittest.TestCase):
    """The repository's own Verilator: where it lands, how it is found, how it is built."""

    def setUp(self):
        test_builder.BuilderTests.setUp(self)
        # The shared cache is outside every checkout in use; the fixture points the
        # variable at its own directory so no test reads or writes the real one.
        cache = tempfile.TemporaryDirectory(prefix="host cache ",
                                            dir=Path(self.root).parent)
        self.addCleanup(cache.cleanup)
        self.cache = Path(cache.name)
        patcher = patch.dict(os.environ, {verilator_install.CACHE_VARIABLE: str(self.cache)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_tree(self, base, item, *, record=True):
        """An installation double: the tree a real build installs and its provenance.

        It carries a `share/verilator/include` header and an uncovered debug
        binary, because those are what the record's scope turns on."""
        base = Path(base)
        (base / "bin").mkdir(parents=True, exist_ok=True)
        (base / "share/verilator/include").mkdir(parents=True, exist_ok=True)
        (base / "share/verilator/bin").mkdir(parents=True, exist_ok=True)
        tool = base / "bin/verilator"
        tool.write_text("#!/bin/sh\n", encoding="utf-8")
        tool.chmod(0o755)
        (base / "share/verilator/include/verilated.cpp").write_text("// runtime\n", encoding="utf-8")
        (base / "bin/verilator_bin_dbg").write_text("debug build\n", encoding="utf-8")
        # A real install puts a redirector of the same name here. It is covered; only
        # the two paths in UNCOVERED are not.
        (base / "share/verilator/bin/verilator_bin_dbg").write_text("redirector\n", encoding="utf-8")
        if record:
            atomic_json(base / verilator_install.INSTALLATION,
                        {"pin": item, "commit": item["commit"], "version": VERSION,
                         "prefix": str(base), "tools": {"verilator": file_hash(tool)},
                         "tree": verilator_install.tree_digests(base),
                         "uncovered": list(verilator_install.UNCOVERED)})
        return tool

    def pinned_tree(self, *, record=True):
        item = verilator_install.pin(self.root)
        base = verilator_install.prefix(self.root, item["version"])
        return item, base, self.write_tree(base, item, record=record)

    @staticmethod
    def present(candidate):
        return candidate if Path(candidate).is_file() else None

    def test_pinned_installation_is_found_without_a_path_edit(self):
        self.assertIsNone(verilator_install.installed(self.root))
        self.assertEqual(verilator_executable(None, self.root, which=self.present), (None, "pinned"))
        item, base, tool = self.pinned_tree(record=False)
        # A tree without its provenance record is not an installation.
        self.assertIsNone(verilator_install.installed(self.root))
        self.write_tree(base, item)
        self.assertEqual(verilator_install.installed(self.root), base / "bin")
        # It lands in the shared host cache, outside the checkout, so removing the
        # worktree after delivery cannot take the build with it.
        self.assertEqual(base, self.cache / verilator_install.TOOL_FOLDER / ("v" + item["version"]))
        self.assertNotIn(self.root.resolve(), base.resolve().parents)
        self.assertEqual(verilator_executable(None, self.root, which=self.present), (str(tool), "pinned"))
        # An operator's PATH tool keeps precedence; the pin never overrides it.
        operator = self.root / "operator/verilator"
        operator.parent.mkdir()
        operator.write_text("", encoding="utf-8")
        self.assertEqual(verilator_executable(None, self.root, which=lambda c: str(operator))[1], "path")
        self.assertEqual(verilator_executable(str(base / "bin"), self.root, which=self.present),
                         (str(tool), "explicit"))
        with self.assertRaisesRegex(ToolError, "must name an existing tool directory"):
            verilator_executable(str(base / "absent"), self.root)

    def test_cache_root_prefers_the_variable_then_the_per_user_default(self):
        root = self.root
        self.assertEqual(verilator_install.cache_root(root, {verilator_install.CACHE_VARIABLE: str(self.cache)}),
                         self.cache)
        # A relative override lands inside the checkout rather than on an unknown path.
        self.assertEqual(verilator_install.cache_root(root, {verilator_install.CACHE_VARIABLE: "host tools"}),
                         Path(root).resolve() / "host tools")
        default = verilator_install.cache_root(root, {"HOME": "/home/agent", "XDG_CACHE_HOME": ""})
        self.assertEqual(default, Path("/home/agent/.cache").joinpath(*verilator_install.CACHE_FOLDER))
        self.assertEqual(verilator_install.cache_root(root, {"XDG_CACHE_HOME": "/xdg"}),
                         Path("/xdg").joinpath(*verilator_install.CACHE_FOLDER))
        # Nothing about the default is inside a checkout.
        self.assertNotIn(Path(root).resolve(), default.parents)

    def test_a_per_checkout_installation_is_still_found_and_then_adopted(self):
        """An earlier worktree build keeps its value: discovered, then published.

        The installed wrapper resolves its own root from its directory, so the
        prefix relocates; adoption moves the verified tree into the shared cache
        and restates the prefix it now occupies rather than rebuilding it."""
        item = verilator_install.pin(self.root)
        legacy = verilator_install.legacy_prefix(self.root, item["version"])
        tool = self.write_tree(legacy, item)
        self.assertEqual(verilator_install.installed(self.root), legacy / "bin")
        self.assertEqual(verilator_executable(None, self.root, which=self.present), (str(tool), "pinned"))
        source = verilator_install.legacy_source_root(self.root, item["version"])
        (source / ".git").mkdir(parents=True)
        item, base, calls, record = self.install(item["commit"])
        self.assertEqual(record["adopted"], {"prefix": True, "source": True})
        self.assertTrue(record["reused"])
        # Adopted, not rebuilt: the only step run is the reuse banner check.
        self.assertEqual([Path(argv[0]).name for argv in calls], ["verilator"])
        self.assertFalse(legacy.exists())
        self.assertEqual(verilator_install.installed(self.root), base / "bin")
        provenance = read_json(base / verilator_install.INSTALLATION)
        self.assertEqual((provenance["prefix"], provenance["adopted_from"]), (str(base), str(legacy)))
        # The retained clone follows it out, so `--offline` stays a host property.
        self.assertTrue((verilator_install.source_root(self.root, item["version"]) / ".git").is_dir())
        self.assertFalse(source.exists())

    def test_an_orphaned_clone_is_adopted_although_the_cache_already_has_the_build(self):
        """The ordinary case, and the one a prefix-gated adoption silently skipped.

        The cache usually already holds the installation while the clone is still
        in whichever worktree fetched it. Tying the clone's rescue to the prefix's
        made the documented pre-removal step a no-op and left 1.8 GB to die with
        that worktree, taking `--offline` on this host with it."""
        item = verilator_install.pin(self.root)
        base = verilator_install.prefix(self.root, item["version"])
        self.write_tree(base, item)
        legacy_source = verilator_install.legacy_source_root(self.root, item["version"])
        (legacy_source / ".git").mkdir(parents=True)
        (legacy_source / "configure").write_text("#!/bin/sh\n", encoding="utf-8")
        self.assertTrue(verilator_install.adoptable_source(self.root, item))
        self.assertFalse(verilator_install.adoptable_prefix(self.root, item, base))
        _, _, calls, record = self.install(item["commit"])
        self.assertEqual(record["adopted"], {"prefix": False, "source": True})
        self.assertTrue(record["reused"])
        # Still no build: the reuse banner check is the only step.
        self.assertEqual([Path(argv[0]).name for argv in calls], ["verilator"])
        source = verilator_install.source_root(self.root, item["version"])
        self.assertTrue((source / ".git").is_dir())
        self.assertTrue((source / "configure").is_file())
        self.assertFalse(legacy_source.exists())
        # Nothing left to adopt, and a second run moves nothing.
        self.assertFalse(verilator_install.adoptable_source(self.root, item))
        _, _, _, record = self.install(item["commit"])
        self.assertEqual(record["adopted"], {"prefix": False, "source": False})

    def test_a_second_installation_is_refused_while_one_holds_the_cache(self):
        """The cache is shared, so two builds into one prefix must not overlap.

        A held lock is refused by name with the pid holding it, never waited on.
        An installed prefix is still reused while the lock is held, so one
        worktree's discovery never blocks on another's build."""
        item = verilator_install.pin(self.root)
        base = verilator_install.prefix(self.root, item["version"])
        lock = base.parent / verilator_install.INSTALL_LOCK
        with verilator_install.cache_lock(base):
            self.assertEqual(lock.read_text(encoding="utf-8"), f"pid={os.getpid()}\n")
            for call in (lambda: verilator_install.cache_lock(base).__enter__(),
                         lambda: self.install(item["commit"])):
                with self.assertRaisesRegex(ValueError, f"by live pid {os.getpid()}; confirm its "
                                            f"writer stopped before removing {re.escape(str(lock))}"):
                    call()
            # Reuse needs no lock: an installed prefix is still served.
            self.write_tree(base, item)
            _, _, calls, record = self.install(item["commit"])
            self.assertTrue(record["reused"])
            self.assertEqual([Path(argv[0]).name for argv in calls], ["verilator"])
        self.assertFalse(lock.exists())

    def test_an_unreadable_lock_owner_counts_as_live_and_a_dead_one_is_reclaimed(self):
        """The repository's tag-lock rule, not advice to delete a running build.

        A lock whose recorded writer is dead is reclaimed once and out loud. A
        lock whose owner cannot be read counts as live, because the empty window
        between the exclusive create and the pid write is reachable, and telling a
        reader to delete that file would destroy a running 26-minute build."""
        item = verilator_install.pin(self.root)
        base = verilator_install.prefix(self.root, item["version"])
        lock = base.parent / verilator_install.INSTALL_LOCK
        lock.parent.mkdir(parents=True, exist_ok=True)
        for unreadable in (b"", b"not a pid\n"):
            lock.write_bytes(unreadable)
            self.assertIsNone(verilator_install.lock_owner(lock))
            with self.assertRaisesRegex(ValueError, "is being installed into; confirm its writer "
                                        f"stopped before removing {re.escape(str(lock))}"):
                with verilator_install.cache_lock(base):
                    pass
            # Never removed on an owner that could not be read.
            self.assertTrue(lock.exists())
        # A dead writer's lock is reclaimed once, out loud, and the caller proceeds.
        lock.write_bytes(b"pid=%d\n" % self.dead_pid())
        with contextlib.redirect_stderr(io.StringIO()) as noticed:
            with verilator_install.cache_lock(base):
                self.assertEqual(lock.read_text(encoding="utf-8"), f"pid={os.getpid()}\n")
        self.assertIn("reclaimed stale lock", noticed.getvalue())
        self.assertFalse(lock.exists())

    @staticmethod
    def dead_pid():
        """A pid no process holds: a child this test has waited for."""
        child = subprocess.Popen([sys.executable, "-c", ""])
        child.wait()
        return child.pid

    def test_a_tree_that_is_not_this_pin_is_reported_rather_than_used(self):
        """The shared path is never trust: the record and the bytes are both checked.

        A cache another pin filled, a hand-made directory and a damaged tree all
        arrive as a prefix that claims to hold the pin, so each is refused by name
        instead of becoming a silent fallback for `regress pre-merge`."""
        item = verilator_install.pin(self.root)
        base = verilator_install.prefix(self.root, item["version"])
        self.write_tree(base, dict(item, commit="0" * 40))
        for call in (lambda: verilator_install.installed(self.root),
                     lambda: verilator_executable(None, self.root, which=self.present)):
            with self.assertRaisesRegex((ValueError, ToolError), "built from a different pin"):
                call()
        self.write_tree(base, dict(item, tag="v9.999"))
        with self.assertRaisesRegex(ValueError, "tag 'v9.999' is not"):
            verilator_install.installed(self.root)
        # The recorded hash is what the installed bytes are held to.
        self.write_tree(base, item)
        (base / "bin/verilator").write_text("#!/bin/sh\nexec /usr/bin/verilator\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match its provenance record"):
            verilator_install.installed(self.root)
        # The scope is the whole installation, not just the executables: a header
        # compiled into every simulation binary changes what runs.
        self.write_tree(base, item)
        runtime = base / "share/verilator/include/verilated.cpp"
        runtime.write_text("// runtime\n// appended\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError,
                                    r"share/verilator/include/verilated\.cpp does not match"):
            verilator_install.installed(self.root)
        # A covered file the record never mentioned is refused, not ignored.
        self.write_tree(base, item)
        (base / "share/verilator/include/extra.h").write_text("// smuggled\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unrecorded file share/verilator/include/extra.h"):
            verilator_install.installed(self.root)
        (base / "share/verilator/include/extra.h").unlink()
        # A missing covered file is named by its own path.
        runtime.unlink()
        with self.assertRaisesRegex(ValueError, r"missing share/verilator/include/verilated\.cpp"):
            verilator_install.installed(self.root)
        # The debug binaries are the declared exception: no run reaches them, so
        # changing one does not refuse the installation.
        self.write_tree(base, item)
        (base / "bin/verilator_bin_dbg").write_text("another debug build\n", encoding="utf-8")
        self.assertEqual(verilator_install.installed(self.root), base / "bin")
        # The exemption is the path, not the name. A basename match would exempt the
        # redirector of the same name, and would let a planted file skip the check by
        # choosing that name -- defeating the check with the name it is keyed on.
        self.assertEqual(verilator_install.UNCOVERED,
                         ("bin/verilator_bin_dbg", "bin/verilator_coverage_bin_dbg"))
        covered = {path.relative_to(base).as_posix()
                   for path in verilator_install.covered_files(base)}
        self.assertIn("share/verilator/bin/verilator_bin_dbg", covered)
        self.assertNotIn("bin/verilator_bin_dbg", covered)
        self.write_tree(base, item)
        (base / "share/verilator/bin/verilator_bin_dbg").write_text("swapped\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError,
                                    r"share/verilator/bin/verilator_bin_dbg does not match"):
            verilator_install.installed(self.root)
        self.write_tree(base, item)
        (base / "share/verilator/include/verilator_coverage_bin_dbg").write_text("x\n", encoding="utf-8")
        with self.assertRaisesRegex(
                ValueError, "unrecorded file share/verilator/include/verilator_coverage_bin_dbg"):
            verilator_install.installed(self.root)
        (base / "share/verilator/include/verilator_coverage_bin_dbg").unlink()
        # The record excludes itself by path too. Keyed on the basename, any file
        # called installation.json deeper in the tree skipped the check by its name,
        # one expression away from the exemption above -- the same defect class, and
        # two adjacent exclusions keyed differently is how it arose.
        planted = base / "share/verilator/include" / verilator_install.INSTALLATION
        planted.write_text('{"smuggled": true}', encoding="utf-8")
        with self.assertRaisesRegex(
                ValueError, f"unrecorded file share/verilator/include/{verilator_install.INSTALLATION}"):
            verilator_install.installed(self.root)
        planted.unlink()
        # The real record, at the prefix root, is still excluded and still read.
        self.assertNotIn(verilator_install.INSTALLATION,
                         {path.name for path in verilator_install.covered_files(base)})
        self.assertEqual(verilator_install.installed(self.root), base / "bin")
        # A record that covers no tree proves nothing about what would run.
        self.write_tree(base, item)
        record = read_json(base / verilator_install.INSTALLATION)
        atomic_json(base / verilator_install.INSTALLATION,
                    {k: v for k, v in record.items() if k != "tree"})
        with self.assertRaisesRegex(ValueError, f"covers no installed tree.*remove {re.escape(str(base))} "
                                    "and reinstall"):
            verilator_install.installed(self.root)
        # `tools verilator` reuses an installed prefix, so it cannot replace one this
        # check refuses; the remedy has to name the removal or it does not work.
        record = read_json(base / verilator_install.INSTALLATION)
        atomic_json(base / verilator_install.INSTALLATION,
                    {k: v for k, v in record.items() if k != "tree"})
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["tools", "verilator", "--tag", "stale-schema", "--json"], self.root), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(f"remove {base} and reinstall", report["error"])
        # `tools` is a second view of bytes the tree already covers, so a record that
        # disagrees with itself is refused without hashing anything twice.
        self.write_tree(base, item)
        record = read_json(base / verilator_install.INSTALLATION)
        record["tools"]["verilator"] = "0" * 64
        atomic_json(base / verilator_install.INSTALLATION, record)
        with self.assertRaisesRegex(ValueError, "disagrees with itself about bin/verilator"):
            verilator_install.installed(self.root)
        self.write_tree(base, item)
        # A record with no installed tool hash proves nothing and is refused.
        atomic_json(base / verilator_install.INSTALLATION, {"pin": item, "tools": {}})
        with self.assertRaisesRegex(ValueError, "names no installed tool hash"):
            verilator_install.installed(self.root)
        (base / verilator_install.INSTALLATION).write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unreadable Verilator provenance record"):
            verilator_install.installed(self.root)

    def test_a_running_verilator_that_is_not_the_pin_is_reported(self):
        """The banner is the last word, so the pin is held against what will run.

        The pinned tree claims to be the pin, so a mismatch there refuses the run.
        An operator's own tool keeps its precedence and is carried as a notice into
        the simulation record instead of passing unremarked."""
        self.assertEqual(verilator_install.pinned_release(self.root), "5.052")
        stale = "Verilator 5.020 2025-01-01 rev v5.020"

        def banner(argv, **_):
            return SimpleNamespace(returncode=0, stdout=stale if argv[0].endswith("verilator")
                                   else "g++ (GCC) 13.3.0\n")
        item, base, tool = self.pinned_tree()
        with patch("n2m.simulator.shutil.which", side_effect=self.operator_which), \
                patch.object(Simulator, "run", side_effect=banner):
            with self.assertRaisesRegex(ToolError, "Verilator 5.020 from pinned discovery is not the pinned 5.052"):
                Simulator("verilator", root=self.root)
            simulator = Simulator("verilator", verilator_bin=str(base / "bin"), root=self.root)
        identity = simulator.info["tools"]["verilator"]
        self.assertEqual((identity["pin"], identity["pin_match"]), ("5.052", False))
        self.assertEqual(len(simulator.notices), 1)
        self.assertIn("is not the pinned 5.052", simulator.notices[0])

    def operator_which(self, candidate):
        """PATH holds no verilator; g++ is present, as on the recorded host."""
        if candidate == "verilator":
            return None
        return candidate if Path(candidate).is_file() else "/usr/bin/g++" if candidate == "g++" else None

    def fake_build(self, commit, *, banner=VERSION):
        """A build double: it records the steps and installs the expected tool."""
        calls = []
        item = verilator_install.pin(self.root)
        base = verilator_install.prefix(self.root, item["version"])

        def run(argv, cwd, log_path, timeout, env):
            argv = [str(part) for part in argv]
            calls.append(argv)
            Path(log_path).write_text("", encoding="utf-8")
            self.assertNotIn("VERILATOR_ROOT", env)
            if "rev-parse" in argv:
                return commit + "\n"
            if "--version" in argv:
                return banner + "\n"
            if argv[-1] == "install":
                (base / "bin").mkdir(parents=True, exist_ok=True)
                (base / "bin/verilator").write_text("#!/bin/sh\n", encoding="utf-8")
            return ""
        return item, base, calls, run

    def install(self, commit, **kwargs):
        item, base, calls, run = self.fake_build(commit, **kwargs.pop("banner_only", {}))
        record = verilator_install.install(self.root, self.build / "tools", item, run=run,
                                           which=lambda name: "/usr/bin/" + name,
                                           environ={"PATH": "/usr/bin", "VERILATOR_ROOT": "/stale"},
                                           **kwargs)
        return item, base, calls, record

    def test_pinned_source_build_records_its_provenance(self):
        item, base, calls, record = self.install(item_commit := verilator_install.pin(self.root)["commit"])
        self.assertEqual([argv[1] if argv[0].endswith("git") else Path(argv[0]).name for argv in calls],
                         ["clone", "-C", "autoconf", "configure", "make", "make", "verilator"])
        self.assertIn("--branch", calls[0])
        self.assertIn(item["tag"], calls[0])
        self.assertEqual(calls[3][:3], [str(base.parent / ("v" + item["version"] + ".source/configure")),
                                        "--prefix", str(base)])
        self.assertEqual(record["commit"], item_commit)
        self.assertFalse(record["reused"])
        provenance = json.loads((base / verilator_install.INSTALLATION).read_text())
        self.assertEqual((provenance["commit"], provenance["version"]), (item_commit, VERSION))
        self.assertEqual(provenance["pin"]["tag"], item["tag"])
        self.assertEqual(provenance["local_changes"], "none")
        self.assertIn("verilator", provenance["tools"])
        # A second install reuses the recorded tree and builds nothing.
        item, base, calls, record = self.install(item_commit)
        self.assertTrue(record["reused"])
        self.assertEqual([Path(argv[0]).name for argv in calls], ["verilator"])

    def test_foreign_commit_banner_and_missing_prerequisite_refuse_the_install(self):
        with self.assertRaisesRegex(ValueError, "commit mismatch"):
            self.install("0" * 40)
        self.assertFalse(verilator_install.prefix(self.root, "5.052").exists())
        with self.assertRaisesRegex(ValueError, "expected 5.052"):
            self.install(verilator_install.pin(self.root)["commit"],
                         banner_only={"banner": "Verilator 5.020 2025-01-01"})
        item = verilator_install.pin(self.root)
        with self.assertRaisesRegex(ValueError, "missing Verilator build prerequisite: bison"):
            verilator_install.install(self.root, self.build / "tools", item,
                                      which=lambda name: None if name == "bison" else "/usr/bin/" + name)
        with self.assertRaisesRegex(ValueError, "offline"):
            verilator_install.install(self.root, self.build / "tools", item, offline=True,
                                      which=lambda name: "/usr/bin/" + name)

    def test_zero_jobs_and_zero_timeout_are_refused_rather_than_defaulted(self):
        """The guard covers what it claims to, on both sides of zero.

        `jobs or os.cpu_count()` and `timeout or STEP_TIMEOUT` turn zero into a
        working default, so a guard placed after either fold only ever catches
        negatives. Both are refused by name before anything is cloned."""
        item = verilator_install.pin(self.root)
        for value in (0, -1):
            with self.subTest(jobs=value), self.assertRaisesRegex(ValueError, "--jobs must be at least 1"):
                self.install(item["commit"], jobs=value)
            with self.subTest(timeout=value), \
                    self.assertRaisesRegex(ValueError, "--timeout must be at least 1 second"):
                self.install(item["commit"], timeout=value)
        # Refused before the source is touched, so no partial tree is left behind.
        self.assertFalse(verilator_install.prefix(self.root, item["version"]).exists())
        self.assertFalse(verilator_install.source_root(self.root, item["version"]).exists())
        # And the whole command reports the refusal rather than building on a default.
        with patch("n2m.verilator_install.install",
                   side_effect=verilator_install.install), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["tools", "verilator", "--timeout", "0", "--tag", "pin-zero", "--json"],
                        self.root)
        self.assertEqual(code, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("--timeout must be at least 1 second", report["error"])

    def test_a_missing_verilator_states_its_remedy_once(self):
        """One remedy, spelled `python3`, with no clause repeated by the caller.

        Both entry points prefix the shared note, so neither may restate either
        half of it: the note already names installing the pin and selecting a
        directory."""
        note = verilator_install.discovery_note(self.root)
        self.assertIn("python3 tools/build.py tools verilator", note)
        for message in (self.missing_verilator_message(doctor.verilator),
                        self.missing_verilator_message(self.discover_through_simulator)):
            self.assertIn("missing verilator", message)
            self.assertEqual(message.count("tool directory explicitly"), 1)
            self.assertEqual(message.count("python3 tools/build.py tools verilator"), 1)
            # `python3` only: the SPEC's Linux examples all spell it that way.
            self.assertNotIn("python tools/build.py", message)

    def discover_through_simulator(self, root, folder, directory):
        del folder
        Simulator("verilator", verilator_bin=directory, root=root)

    def missing_verilator_message(self, call):
        """The failure text one entry point produces with no Verilator anywhere."""
        with patch("n2m.simulator.installed_verilator", return_value=None), \
                patch("shutil.which", return_value=None), \
                self.assertRaises((RuntimeError, ToolError)) as raised:
            call(self.root, self.build, None)
        return str(raised.exception)

    def test_command_reports_the_discovered_pin(self):
        item = verilator_install.pin(self.root)
        base = verilator_install.prefix(self.root, item["version"])

        def install(root, folder, pin, **kwargs):
            self.write_tree(base, pin)
            return {"pin": pin, "reused": False, "version": VERSION, "commands": []}

        with patch("n2m.verilator_install.install", side_effect=install), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["tools", "verilator", "--tag", "pin-fixture", "--json"], self.root), 0)
        report = json.loads(output.getvalue())
        self.assertEqual((report["status"], report["version"]), ("PASS", VERSION))
        self.assertEqual(report["discovered"], str(base / "bin"))
        self.assertEqual(report["pin"]["version"], item["version"])
        with patch("n2m.verilator_install.install", side_effect=ValueError("make exited 2")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["tools", "verilator", "--tag", "pin-fixture", "--json"], self.root), 1)
        self.assertIn("make exited 2", json.loads(output.getvalue())["error"])


class DiagnosticTests(unittest.TestCase):
    def test_warnings_and_errors_fail_without_an_expected_failure(self):
        self.assertIsNone(verilator.diagnostic("PASS builder-smoke seed=1 checks=22\n- x.sv:37: Verilog $finish"))
        for output in ("%Warning-WIDTH: x.sv:3: Operator ASSIGN expects 4 bits",
                       "[100] %Warning: late", "     0.00ns WARNING  cocotb.regression  test failed",
                       "%Error: x.sv:1: syntax error", "[40000] %Fatal: x.sv:31: Assertion failed",
                       "     -.--ns ERROR    gpi  no users", "CRITICAL cocotb  boom"):
            with self.subTest(output=output):
                self.assertIsNotNone(verilator.diagnostic("ok\n" + output))

    def test_explained_warning_lines_are_accepted_one_at_a_time(self):
        failed = "    47.00ns WARNING  cocotb.regression                  test_joypad.joypad_contract failed"
        explained = ("test_joypad.joypad_contract failed",)
        self.assertIsNone(verilator.diagnostic(failed + "\n- :0: Verilog $finish", explained=explained))
        self.assertEqual(verilator.diagnostic(failed + "\n- :0: Verilog $finish"), "unexplained simulator warning")
        self.assertEqual(verilator.diagnostic(failed + "\nWARNING  cocotb.regression  other failed", explained=explained),
                         "unexplained simulator warning")
        self.assertEqual(verilator.diagnostic(failed + "\n%Warning-WIDTH: x.sv:3: late", explained=explained),
                         "unexplained simulator warning")

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

    def test_configuration_sources_precede_hdl_and_the_generated_access_list(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        waivers = "src/dv/builder/waivers.vlt"
        (self.root / waivers).write_text("`verilator_config\n")
        targets["builder-smoke"]["sources"].append(waivers)
        registry.write_text(json.dumps(targets))
        target, _ = load_target(self.root, "builder-smoke")
        attempt = self.build / "attempt"
        compiler = self.build / "compile"
        for folder in (attempt / "waves", compiler):
            folder.mkdir(parents=True)
        (build, *_), (run, *_) = verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        config = str(self.root / waivers)
        # The waiver file is passed once, ahead of the HDL and before the harness.
        self.assertEqual(build.count(config), 1)
        self.assertLess(build.index(config), build.index(str(self.root / "src/dv/builder/builder_smoke.sv")))
        self.assertEqual(build[-1], verilator.HARNESS)
        self.assertNotIn(config, run)
        # Under the peer flow it also precedes the generated access list, so both apply.
        shutil.copytree(test_builder.ROOT / "src/dv/integration", self.root / "src/dv/integration",
                        ignore=shutil.ignore_patterns("__pycache__"))
        targets = read_json(registry)
        targets["verilator-peer"]["sources"].append(waivers)
        registry.write_text(json.dumps(targets))
        target, _ = load_target(self.root, "verilator-peer")
        runtime = {"library_dir": "/venv/cocotb/libs", "support": "/venv/cocotb/share/lib/verilator/verilator.cpp"}
        (build, *_), _ = verilator.commands(self.sim, self.root, target, 1, self.build, attempt, python_runtime=runtime)
        access = str(self.build / verilator.ACCESS_CONFIG)
        self.assertLess(build.index(config), build.index(access))
        self.assertLess(build.index(access), build.index(str(self.root / "src/dv/integration/tb_verilator_peer.sv")))

    def test_parameter_overrides_are_verilated_in_and_kept_off_the_run(self):
        # Questa applied -g parameter overrides at vsim time; Verilator takes
        # them at verilate time as -G and the run never sees them.
        target, _ = load_target(self.root, "builder-smoke")
        target = {**target, "args": ["-gPRELOADED=1", "-gBUILD_ID=128'h10", "+inject_failure", "+io_peek_samples=120"]}
        attempt = self.build / "attempt"
        (attempt / "waves").mkdir(parents=True)
        (build, *_), (run, *_) = verilator.commands(self.sim, self.root, target, 7, self.build, attempt)
        top = build.index("--top-module")
        self.assertEqual(build[top + 2:top + 4], ["-GPRELOADED=1", "-GBUILD_ID=128'h10"])
        self.assertEqual(build[-1], verilator.HARNESS)
        self.assertEqual(run[1:], ["+seed=7", "+verilator+seed+7", "+verilator+rand+reset+2", "+inject_failure", "+io_peek_samples=120"])
        self.assertFalse(verilator.is_parameter_arg("-g"))
        self.assertFalse(verilator.is_parameter_arg("+define+PRELOADED"))

    def test_defines_become_build_options_and_are_validated(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        pristine = dict(targets["builder-smoke"])
        targets["builder-smoke"] = {**pristine, "defines": ["PRELOADED", "DEPTH=8"]}
        registry.write_text(json.dumps(targets))
        target, _ = load_target(self.root, "builder-smoke")
        attempt = self.build / "attempt"
        compiler = self.build / "compile"
        for folder in (attempt / "waves", compiler):
            folder.mkdir(parents=True)
        (build, *_), (run, *_) = verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        self.assertIn("+define+PRELOADED", build)
        self.assertIn("+define+DEPTH=8", build)
        self.assertNotIn("+define+PRELOADED", run)
        for bad in (["-gPRELOADED=1"], "PRELOADED", ["A B"]):
            targets["builder-smoke"] = {**pristine, "defines": bad}
            registry.write_text(json.dumps(targets))
            with self.assertRaisesRegex(ValueError, "defines must list"):
                load_target(self.root, "builder-smoke")

    def test_adc_binding_writes_the_channel_fixture_beside_the_run(self):
        target, _ = load_target(self.root, "builder-smoke")
        target = {**target, "vendor_model": "intel-adc"}
        attempt = self.build / "attempt"
        compiler = self.build / "compile"
        for folder in (attempt / "waves", compiler):
            folder.mkdir(parents=True)
        verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        self.assertEqual(sorted(p.name for p in attempt.glob("adc_ch*.txt")), sorted(f"adc_ch{i}.txt" for i in range(17)))
        self.assertEqual((attempt / "adc_ch1.txt").read_text(), "0 0.625\n")
        self.assertEqual((attempt / "adc_ch2.txt").read_text(), "0 1.25\n")
        self.assertEqual((attempt / "adc_ch0.txt").read_text(), "0 0.0\n")
        # A replay against the retained attempt leaves identical files alone
        # and refuses a foreign file under a fixture name.
        verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        (attempt / "adc_ch3.txt").write_text("0 9.9\n")
        with self.assertRaisesRegex(ValueError, "ADC stimulus path already exists"):
            verilator.commands(self.sim, self.root, target, 1, compiler, attempt)

    def test_controls_binding_writes_the_same_channel_fixture(self):
        # The composed controls binding carries the ADC, so its double needs
        # the same channel files as a plain intel-adc target.
        target, _ = load_target(self.root, "builder-smoke")
        target = {**target, "vendor_model": "intel-controls"}
        attempt = self.build / "attempt"
        compiler = self.build / "compile"
        for folder in (attempt / "waves", compiler):
            folder.mkdir(parents=True)
        verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        self.assertEqual(len(list(attempt.glob("adc_ch*.txt"))), 17)
        target = {**target, "vendor_model": "intel-memory"}
        (attempt / "adc_ch0.txt").unlink()
        verilator.commands(self.sim, self.root, target, 1, compiler, attempt)
        self.assertFalse((attempt / "adc_ch0.txt").exists())

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
        # The wrappers own their clocks and settled-sample delays, so --timing
        # stays; only the top module is public, and the C++ is built -O2.
        self.assertIn("--timing", build)
        self.assertNotIn("--public-flat-rw", build)
        config = self.build / verilator.ACCESS_CONFIG
        self.assertIn(str(config), build)
        self.assertEqual(config.read_text().splitlines()[-1], 'public_flat_rw -module "n2m_joypad" -var "*"')
        self.assertEqual(build[build.index("-CFLAGS") + 1], "-O2")
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
        # Only the declared access list is public; the whole-design switch
        # would cost the optimizations the product targets need for their budget.
        self.assertNotIn("--public-flat-rw", build)
        config = self.build / verilator.ACCESS_CONFIG
        self.assertIn(str(config), build)
        text = config.read_text()
        self.assertTrue(text.startswith("`verilator_config\n"))
        for name in target["driver"]["access"]:
            self.assertIn(f'public_flat_rw -module "tb_verilator_peer" -var "{name}"', text)


class RecordTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def test_changed_configuration_source_changes_the_fingerprint(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        waivers = self.root / "src/dv/builder/waivers.vlt"
        waivers.write_text("`verilator_config\n")
        targets["builder-smoke"]["sources"].append("src/dv/builder/waivers.vlt")
        registry.write_text(json.dumps(targets))
        first = self.run_stage()
        self.assertEqual((first["status"], first["cache"]), ("PASS", "BUILT"))
        self.assertIn("src/dv/builder/waivers.vlt", first["inputs"])
        self.assertEqual(self.run_stage()["cache"], "CACHED")
        waivers.write_text('`verilator_config\nlint_off -rule WIDTHEXPAND -file "*/builder_smoke.sv"\n')
        second = self.run_stage()
        self.assertEqual((second["status"], second["cache"]), ("PASS", "BUILT"))
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(self.run_stage()["cache"], "CACHED")

    def test_record_names_simulator_os_seed_waves_and_split_timing(self):
        with patch("n2m.simulation.platform.system", return_value="Linux"):
            record = self.run_stage()
        self.assertEqual((record["status"], record["simulator"], record["os"], record["seed"]), ("PASS", "verilator", "Linux", 1))
        self.assertEqual(record["waves"]["format"], "fst")
        self.assertIn(record["waves"]["path"], record["artifacts"])
        self.assertTrue(record["waves"]["path"].endswith("waves/simulation.fst"))
        self.assertEqual(set(record["timing"]), {"prepare_seconds", "build_seconds", "run_seconds",
                                                 "locked_seconds", "locked_cpu_seconds"})
        self.assertEqual(record["prepared"]["mode"], "inline")
        self.assertGreaterEqual(record["timing"]["locked_seconds"], record["timing"]["build_seconds"] + record["timing"]["run_seconds"])
        # The locked CPU is measured beside the locked wall so the pair is
        # written into one record and a cache hit replays both.
        self.assertGreaterEqual(record["timing"]["locked_cpu_seconds"], 0)
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

    def test_vendor_model_is_recorded_and_a_driver_needs_the_peer_module(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        pristine = dict(targets["builder-smoke"])
        (self.root / "driver.do").write_text("run -all\n")
        (self.root / "driver.py").write_text("import cocotb\n")
        access = ["tx_go", "finish_request"]
        # The synthesis binding is accepted as a record; the Questa-only
        # mixed-mode inventory and unknown bindings are refused.
        targets["builder-smoke"] = {**pristine, "vendor_model": "intel-memory"}
        registry.write_text(json.dumps(targets))
        self.assertEqual(load_target(self.root, "builder-smoke")[0]["vendor_model"], "intel-memory")
        targets["builder-smoke"] = {**pristine, "simulators": ["verilator", "questa"],
                                    "vendor_model": "intel-memory",
                                    "intel_mixed_mode_instances": ["tb.dut.ram"]}
        registry.write_text(json.dumps(targets))
        self.assertEqual(load_target(self.root, "builder-smoke")[0]["intel_mixed_mode_instances"],
                         ["tb.dut.ram"])
        for change, message in (({"vendor_model": "altera-mf"}, "vendor_model must be one of"),
                                ({"simulators": ["verilator"], "vendor_model": "intel-memory", "intel_mixed_mode_instances": ["tb.dut.ram"]}, "intel_mixed_mode_instances"),
                                ({"simulators": ["verilator"], "driver": {"script": "driver.do", "peer": "tools/build.py", "inputs": [], "access": access}}, "Python peer driver supports only Verilator"),
                                ({"simulators": ["verilator"], "driver": {"script": "driver.py", "peer": "tools/build.py", "inputs": []}}, "nonempty access list"),
                                ({"simulators": ["verilator"], "driver": {"script": "missing.py", "peer": "tools/build.py", "inputs": [], "access": access}}, "missing or out-of-tree driver input")):
            targets["builder-smoke"] = {**pristine, **change}
            registry.write_text(json.dumps(targets))
            with self.assertRaisesRegex(ValueError, message):
                load_target(self.root, "builder-smoke")
        # Tcl peer drivers are not part of the common Python-peer contract.
        targets["builder-smoke"] = {**pristine, "simulators": ["questa"],
                                    "driver": {"script": "driver.do", "peer": "tools/build.py", "inputs": []}}
        registry.write_text(json.dumps(targets))
        with self.assertRaisesRegex(ValueError, "Python peer driver supports only Verilator"):
            load_target(self.root, "builder-smoke")
        targets["builder-smoke"] = {**pristine, "simulators": ["verilator"],
                                    "driver": {"script": "driver.py", "peer": "tools/build.py", "inputs": [], "access": access}}
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
                # prepared files, so INIT_FILE and $readmemh paths resolve.
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


class CapabilityTests(unittest.TestCase):
    setUp = test_builder.BuilderTests.setUp
    run_stage = test_builder.BuilderTests.run_stage

    def test_missing_or_unknown_simulator_is_rejected(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        for value in (None, [], ["icarus"], ["Verilator"], ["verilator", "verilator"], 1):
            targets["builder-smoke"]["simulators"] = value
            if value is None:
                del targets["builder-smoke"]["simulators"]
            registry.write_text(json.dumps(targets))
            with self.assertRaisesRegex(ValueError, "must declare simulators as a nonempty unique list"):
                load_target(self.root, "builder-smoke")

    def test_unsupported_pair_fails_before_discovery(self):
        registry = self.root / "src/dv/builder/targets.json"
        targets = read_json(registry)
        targets["builder-smoke"]["simulators"] = ["verilator"]
        registry.write_text(json.dumps(targets))
        with self.assertRaisesRegex(ValueError, "does not support simulator questa"):
            load_target(self.root, "builder-smoke", "questa")
        with patch("n2m.cli.Simulator", side_effect=AssertionError("discovered")), \
                patch("n2m.cli.platform.system", return_value="Windows"), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["sim", "test", "builder-smoke", "--sim", "questa", "--tag", "unsupported", "--json"], self.root)
        self.assertEqual(code, 1)
        self.assertIn("does not support simulator questa", json.loads(output.getvalue())["error"])
        self.assertFalse((self.root / "workdir/latest.txt").exists())
        self.assertFalse((self.root / "workdir/builds/unsupported").exists())


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

    def test_verilator_is_refused_on_windows(self):
        """The pin is an autoconf/make/g++ source build, so no Windows Verilator
        exists for discovery to find. That refusal is a tool fact and stays."""
        for argv in (["sim", "test", "builder-smoke", "--tag", "h1"],
                     ["tests", "run", "--level", "0", "--tag", "h2"],
                     ["regress", "pre-merge", "--tag", "h3"]):
            with self.subTest(argv=argv):
                code, report = self.run_cli("Windows", *argv, "--sim", "verilator")
                self.assertEqual(code, 1)
                self.assertEqual((report["status"], report["error"], report["os"]),
                                 ("FAIL", VERILATOR_HOST, "Windows"))

    def test_questa_carries_no_operating_system_refusal(self):
        """Questa follows its install and its license, not the host OS.

        `sim test --sim questa` reaches discovery on every host, exactly as it
        does on Windows; run_cli patches Simulator to raise on arrival. No
        simulator command answers with an operating-system refusal.
        """
        for system in ("Linux", "Darwin", "Windows"):
            with self.subTest(system=system):
                code, report = self.run_cli(system, "sim", "test", "builder-smoke",
                                            "--tag", "q1-" + system.lower(), "--sim", "questa")
                self.assertEqual(code, 1)
                self.assertEqual((report["status"], report["error"]), ("FAIL", "discovered"))
        for argv in (["tests", "run", "--level", "0"], ["regress", "pre-merge"]):
            for system in ("Linux", "Darwin", "Windows"):
                with self.subTest(argv=argv, system=system):
                    tag = argv[0] + "-" + system.lower()
                    code, report = self.run_cli(system, *argv, "--tag", tag, "--sim", "questa")
                    self.assertEqual(code, 1)
                    for absent in ("runs on Windows", "PowerShell", "operating system"):
                        self.assertNotIn(absent, report["error"])

    def test_linux_programming_is_refused_by_tool_discovery_not_by_the_host(self):
        """No refusal names the operating system: the stage's own discovery names the programmer."""
        code, report = self.run_cli("Linux", "fpga", "program", "--sof", "x.sof",
                                   "--quartus-bin", "tools", "--tag", "l2")
        self.assertEqual(code, 1)
        self.assertEqual((report["status"], report["os"]), ("FAIL", "Linux"))
        for absent in ("runs on Windows", "PowerShell", "operating system", "unverified"):
            self.assertNotIn(absent, report["error"])

    def test_hardware_inspection_reaches_its_checks_on_either_host(self):
        """The read-only inspection that precedes programming carries no OS refusal.

        `fpga program` resolves its programmer by discovery, so the environment
        check that must run before a write resolves the same way. Reaching the
        check on both hosts is what proves the gate is gone; the doctor itself is
        patched to raise on arrival, so no tool is discovered and nothing is read.
        """
        for system in ("Linux", "Windows"):
            with self.subTest(system=system):
                with patch("n2m.cli.platform.system", return_value=system), \
                        patch("n2m.cli.doctor", side_effect=AssertionError("inspected")), \
                        patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    code = main(["doctor", "--profile", "environment", "--sim", "questa",
                                 "--tag", "inspect-" + system.lower(), "--json"], self.root)
                report = json.loads(output.getvalue())
                self.assertEqual(code, 1)
                self.assertEqual((report["status"], report["error"], report["os"]),
                                 ("FAIL", "inspected", system))
                for absent in ("runs on Windows", "PowerShell", "operating system", "Windows-owned"):
                    self.assertNotIn(absent, report["error"])

    def test_linux_reaches_the_fpga_build_stage(self):
        """No refusal stands between Linux and Quartus: the stage itself runs."""
        code, report = self.run_cli("Linux", "fpga", "build", "smoke", "--quartus-bin", "tools", "--tag", "l1")
        self.assertEqual(code, 1)
        # run_cli patches build_fpga to raise; reaching it proves the OS gate is gone.
        self.assertEqual((report["status"], report["error"], report["os"]), ("FAIL", "built", "Linux"))

    def test_windows_refuses_the_pinned_tool_installation(self):
        """The pin is an autoconf/make/g++ build; Windows gets a refusal, not a
        missing-prerequisite error from halfway into the build."""
        code, report = self.run_cli("Windows", "tools", "verilator", "--tag", "w1")
        self.assertEqual(code, 1)
        self.assertEqual((report["status"], report["error"], report["os"]),
                         ("FAIL", TOOLS_HOST, "Windows"))

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
