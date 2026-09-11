"""Regression subset and cleanup contract tests; children are host doubles, not RTL evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.cli import main
from n2m.records import atomic_json, read_json
from n2m import regress as module
from n2m.test_budget import supervise

ROOT = Path(__file__).resolve().parents[3]


class RegressTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/regress-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="space ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # tile-pixel sources travel too: the runner validates every member before the first child.
        for owner in ("tools/n2m", "src/dv/builder", "src/rtl/display", "src/dv/display"):
            shutil.copytree(ROOT / owner, self.root / owner, ignore=shutil.ignore_patterns("__pycache__", "tests"))
        shutil.copy(ROOT / "tools/build.py", self.root / "tools/build.py")
        (self.root / "workdir/builds").mkdir(parents=True)
        self.subsets = self.root / "src/dv/builder/regressions.json"
        self.declare({"good": ["builder-smoke", "tile-pixel"], "mixed": ["builder-smoke", "builder-smoke-fail", "tile-pixel"]})
        self.children = []
        self.outcomes = {"builder-smoke-fail": ("FAIL", 1)}

    def declare(self, subsets, budget=300, tier="ordinary"):
        plan = {"version": 1, "subsets": {name: {"tier": tier, "purpose": "test", "budget_seconds": budget, "targets": members}
                                          for name, members in subsets.items()}}
        atomic_json(self.subsets, plan)

    def fake_supervise(self, command, root, tag, *, target=None, ceiling=None):
        """Stand in for the public sim-test child: record the call, publish the
        result a real child would leave, and answer with its JSON line."""
        self.children.append({"command": command, "tag": tag, "target": target, "ceiling": ceiling})
        self.assertEqual(command[:4], [sys.executable, str(root / "tools/n2m/test_budget.py"), "sim", "test"])
        self.assertEqual(command[4], target)
        self.assertEqual(command[command.index("--tag") + 1], tag)
        status, code = self.outcomes.get(target, ("PASS", 0))
        record = {"status": status, "cache": "BUILT", "tag": tag}
        if status == "FAIL":
            record["error"] = "unexpected exit 1; see sim.log"
        atomic_json(root / "workdir/builds" / tag / "sim/test" / target / "result.json", record)
        return code, "note on stdout\n" + json.dumps(record) + "\n"

    def run_cli(self, *argv):
        with patch("n2m.regress.supervise", side_effect=self.fake_supervise), \
                patch("n2m.cli.git_state", return_value={"commit": "test"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(list(argv), self.root)
        return code, json.loads(output.getvalue()) if "--json" in argv else output.getvalue()

    def test_pass_reports_every_target_and_publishes_summary(self):
        code, report = self.run_cli("regress", "good", "--tag", "agg", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual([child["target"] for child in self.children], ["builder-smoke", "tile-pixel"])
        self.assertEqual({name: outcome["status"] for name, outcome in report["targets"].items()},
                         {"builder-smoke": "PASS", "tile-pixel": "PASS"})
        self.assertEqual(report["targets"]["tile-pixel"]["result"], "workdir/builds/agg/sim/test/tile-pixel/result.json")
        self.assertEqual(report["failed"], [])
        self.assertLessEqual(report["elapsed_seconds"], 300)
        summary = read_json(self.root / "workdir/builds/agg/sim/regress/summary.json")
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["subset"], "good")
        self.assertEqual(read_json(self.root / "workdir/builds/agg/manifest.json")["status"], "PASS")
        self.assertEqual(read_json(self.root / "workdir/builds/agg/status.json")["status"], "PASS")
        self.assertEqual((self.root / "workdir/latest.txt").read_text(), "agg\n")
        self.assertFalse((self.root / "workdir/builds/agg/.lock").exists())
        self.assertFalse((self.root / "workdir/builds/agg/sim/regress/.lock").exists())
        self.assertTrue(all(child["ceiling"] <= 300 for child in self.children))

    def test_failing_target_fails_aggregate_and_is_named(self):
        code, report = self.run_cli("regress", "mixed", "--tag", "agg", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["failed"], ["builder-smoke-fail"])
        self.assertIn("builder-smoke-fail FAIL", report["error"])
        self.assertEqual(report["targets"]["builder-smoke-fail"]["status"], "FAIL")
        self.assertEqual(report["targets"]["builder-smoke-fail"]["error"], "unexpected exit 1; see sim.log")
        # Later members still run; the aggregate reports each outcome.
        self.assertEqual(report["targets"]["tile-pixel"]["status"], "PASS")
        self.assertFalse((self.root / "workdir/latest.txt").exists())
        code, text = self.run_cli("regress", "mixed", "--tag", "agg2")
        self.assertIn("builder-smoke-fail: FAIL", text)

    def test_unknown_subset_and_invalid_declarations_fail_before_any_child(self):
        code, report = self.run_cli("regress", "nightly", "--tag", "agg", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(report["error"], "unknown regression subset: nightly")
        self.assertEqual(self.children, [])
        self.assertEqual(read_json(self.root / "workdir/builds/agg/manifest.json")["status"], "FAIL")
        for plan, message in (({"version": 2, "subsets": {}}, "version 1"),
                              ({"version": 1, "subsets": {"x": {"tier": "ordinary", "purpose": "p", "budget_seconds": 300}}}, "exactly"),
                              ({"version": 1, "subsets": {"x": {"tier": "nightly", "purpose": "p", "budget_seconds": 300, "targets": ["builder-smoke"]}}}, "tier"),
                              ({"version": 1, "subsets": {"x": {"tier": "ordinary", "purpose": " ", "budget_seconds": 300, "targets": ["builder-smoke"]}}}, "purpose"),
                              ({"version": 1, "subsets": {"x": {"tier": "ordinary", "purpose": "p", "budget_seconds": 300, "targets": ["builder-smoke", "builder-smoke"]}}}, "distinct"),
                              ({"version": 1, "subsets": {"x": {"tier": "ordinary", "purpose": "p", "budget_seconds": 300, "targets": ["missing"]}}}, "registered"),
                              ({"version": 1, "subsets": {"x": {"tier": "ordinary", "purpose": "p", "budget_seconds": 301, "targets": ["builder-smoke"]}}}, "1..300"),
                              ({"version": 1, "subsets": {"x": {"tier": "milestone", "purpose": "p", "budget_seconds": 301, "targets": ["builder-smoke"]}}}, "1..300"),
                              ({"version": 1, "subsets": {"x": {"tier": "ordinary", "purpose": "p", "budget_seconds": 300.0, "targets": ["builder-smoke"]}}}, "integer"),
                              ({"version": 1, "subsets": {"x": {"tier": "ordinary", "purpose": "p", "budget_seconds": 900, "targets": ["builder-smoke", "tile-pixel", "tile-pixel-corrupt"]}}}, "ordinary")):
            atomic_json(self.subsets, plan)
            with self.assertRaisesRegex(ValueError, message):
                module.load_subsets(self.root)
        self.assertEqual(self.children, [])

    def test_unrunnable_member_fails_before_any_child(self):
        targets = self.root / "src/dv/builder/targets.json"
        registry = read_json(targets)
        registry["tile-pixel"]["sources"].append("src/missing.sv")
        atomic_json(targets, registry)
        code, report = self.run_cli("regress", "good", "--tag", "agg", "--json")
        self.assertEqual(code, 1)
        self.assertIn("missing or out-of-tree source", report["error"])
        self.assertEqual(self.children, [])

    def test_broader_budget_requires_the_flag(self):
        self.declare({"long": ["builder-smoke", "tile-pixel"]}, budget=400, tier="milestone")
        code, report = self.run_cli("regress", "long", "--tag", "agg", "--json")
        self.assertEqual(code, 1)
        self.assertIn("--broader", report["error"])
        self.assertEqual(self.children, [])
        code, report = self.run_cli("regress", "long", "--tag", "agg", "--json", "--broader")
        self.assertEqual(code, 0)
        self.assertTrue(report["broader"])
        self.assertEqual(report["budget_seconds"], 400)

    def test_aggregate_budget_caps_children_and_skips_the_rest(self):
        self.declare({"tight": ["builder-smoke", "tile-pixel", "tile-pixel-corrupt"]}, budget=100)
        clock = iter([0, 0, 0, 0, 50, 50, 50, 95, 100])
        with patch("n2m.regress.time.monotonic", side_effect=lambda: next(clock)):
            code, report = self.run_cli("regress", "tight", "--tag", "agg", "--json")
        self.assertEqual(code, 1)
        self.assertEqual([child["ceiling"] for child in self.children], [100, 50])
        self.assertEqual(report["targets"]["tile-pixel-corrupt"]["status"], "SKIPPED")
        self.assertEqual(report["failed"], ["tile-pixel-corrupt"])
        self.assertIn("tile-pixel-corrupt SKIPPED", report["error"])

    def test_child_options_and_real_supervisor_cap(self):
        code, report = self.run_cli("regress", "good", "--tag", "agg", "--json", "--seed", "7", "--rebuild",
                                    "--questa-bin", "C:/q/bin", "--intel-sim-lib", "C:/sim lib")
        self.assertEqual(code, 0)
        command = self.children[0]["command"]
        self.assertEqual(command[command.index("--seed") + 1], "7")
        self.assertIn("--rebuild", command)
        self.assertEqual(command[command.index("--intel-sim-lib") + 1], "C:/sim lib")
        (self.root / "workdir/builds/cap").mkdir()
        supervise([sys.executable, "-c", "print('ok')"], self.root, "cap", target="builder-smoke", ceiling=40)
        record = json.loads(next((self.root / "workdir/builds/cap/wall-budget").glob("*.json")).read_text())
        self.assertEqual((record["wall_limit_seconds"], record["wall_ceiling_seconds"]), (40, 40))
        with self.assertRaisesRegex(ValueError, "ceiling"):
            supervise([sys.executable, "-c", "print('ok')"], self.root, "cap", ceiling=12)

    def test_regress_guard_refuses_a_second_runner_on_the_tag(self):
        guard = self.root / "workdir/builds/agg/sim/regress/.lock"
        guard.parent.mkdir(parents=True)
        guard.write_text("pid=1")
        code, report = self.run_cli("regress", "good", "--tag", "agg", "--json")
        self.assertEqual(code, 1)
        self.assertIn("locked", report["error"])
        self.assertEqual(self.children, [])
        self.assertTrue(guard.exists())

    def test_clean_removes_exactly_one_tag(self):
        self.run_cli("regress", "good", "--tag", "agg", "--json")
        build = self.root / "workdir/builds/agg"
        other = self.root / "workdir/builds/other/keep.txt"
        other.parent.mkdir()
        other.write_text("keep")
        with patch("n2m.cli.git_state", return_value={"commit": "test"}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["clean", "--tag", "agg", "--json"], self.root), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["removed"], "workdir/builds/agg")
        self.assertGreater(report["files"], 0)
        self.assertTrue(report["latest_cleared"])
        self.assertFalse(build.exists())
        self.assertFalse((self.root / "workdir/latest.txt").exists())
        self.assertEqual(other.read_text(), "keep")
        with patch("n2m.cli.git_state", return_value={"commit": "test"}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["clean", "--tag", "agg", "--json"], self.root), 1)
        self.assertEqual(json.loads(output.getvalue())["error"], "no build tag agg")

    def test_clean_refuses_paths_outside_the_tag_and_locked_tags(self):
        outside = self.root / "outside/keep.txt"
        outside.parent.mkdir()
        outside.write_text("keep")
        builds = self.root / "workdir/builds"
        (builds / "locked").mkdir()
        (builds / "locked/.lock").write_text("pid=1")
        link = builds / "linked"
        linked = True
        try:
            if os.name == "nt":
                # A junction needs no privilege on Windows; a symlink usually does.
                subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside.parent)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.symlink(outside.parent, link, target_is_directory=True)
        except (OSError, subprocess.CalledProcessError):
            linked = False
        for tag, message in (("../outside", "valid build tag"), (str(outside.parent), "valid build tag"),
                             ("..", "valid build tag"), ("workdir", "no build tag"), ("locked", "locked"),
                             *((("linked", "link"),) if linked else ())):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(ValueError, message):
                    module.clean(self.root, tag)
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                main(["clean"], self.root)
        self.assertTrue(linked, "linked-tag case did not run on this host")
        self.assertEqual(outside.read_text(), "keep")
        self.assertTrue((builds / "locked/.lock").exists())
        self.assertTrue(self.root.is_dir())
        self.assertTrue((self.root / "workdir").is_dir())

    def test_declared_subsets_in_repository_are_valid(self):
        subsets, _ = module.load_subsets(ROOT)
        self.assertIn("pre-merge", subsets)
        self.assertEqual(subsets["builder-fault"]["targets"], ["builder-smoke", "builder-smoke-fail"])


if __name__ == "__main__":
    unittest.main()
