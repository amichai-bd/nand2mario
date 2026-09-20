"""The `check` host suite runs its module groups concurrently, budgets each group's own CPU, and fails by group name."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import host_suite

ROOT = Path(__file__).resolve().parents[3]
SLEEP = 1.2
# argv: <name> <seconds>; writes <name>.start, sleeps, then writes <name>.finish (wall-clock seconds).
TIMED_SCRIPT = ("import sys, time; from pathlib import Path; n = Path(sys.argv[1]); "
                "n.with_suffix('.start').write_text(repr(time.time())); time.sleep(float(sys.argv[2])); "
                "n.with_suffix('.finish').write_text(repr(time.time()))")
# argv: <seconds>; burns exactly that much of its own CPU, however fast or busy the host is.
BURN_SCRIPT = ("import sys, time; deadline = time.process_time() + float(sys.argv[1]); x = 0\n"
               "while time.process_time() < deadline: x += 1")
# argv: <seconds>; spends wall without CPU, the way a group waiting for a core does.
WAIT_SCRIPT = "import sys, time; time.sleep(float(sys.argv[1]))"
BURN = 1.0
# Interpreter startup and the write of the group's output are the group's CPU too.
STARTUP = 0.6


def scripted(scripts):
    """A `command` replacement that runs each group pattern's own `python -c` script."""
    return lambda root, pattern: [sys.executable, "-c", *scripts[pattern]]


def workspace():
    return tempfile.TemporaryDirectory(prefix="host-suite ", dir=ROOT / "workdir")


def suite(root, scripts, modules=(), cpu_budget=60, wall_ceiling=60):
    """Run the given groups in a bare tree and return (fields, problems, log)."""
    (root / host_suite.TESTS).mkdir(parents=True, exist_ok=True)
    for name in modules:
        (root / host_suite.TESTS / name).write_text("")
    with patch.object(host_suite, "GROUPS", tuple(scripts)), \
            patch.object(host_suite, "CPU_BUDGET", cpu_budget), \
            patch.object(host_suite, "WALL_CEILING", wall_ceiling), \
            patch.object(host_suite, "command", scripted(scripts)):
        fields, problems = host_suite.run(root, root / "check.log")
    return fields, problems, (root / "check.log").read_text()


class GroupTests(unittest.TestCase):
    def test_every_module_in_the_tree_belongs_to_exactly_one_group(self):
        names = host_suite.modules(ROOT)
        self.assertIn(Path(__file__).name, names)
        for name in names:
            with self.subTest(module=name):
                self.assertEqual(sum(host_suite.fnmatch.fnmatchcase(name, g) for g in host_suite.GROUPS), 1)
        self.assertEqual(host_suite.unmatched(["test_1.py", "test_Zoo.py", "test_a.py"]), ["test_1.py", "test_Zoo.py"])

    def test_groups_run_together(self):
        # Every group sleeps SLEEP seconds and records its own start and finish wall-clock times.
        # A sequential runner starts one group only after another finished, so its wall is about
        # three sleeps and no start precedes every finish; the concurrent runner overlaps all three.
        groups = ("test_a*", "test_b*", "test_c*")
        with workspace() as temp:
            root = Path(temp)
            scripts = {g: (TIMED_SCRIPT, str(root / g[5]), str(SLEEP)) for g in groups}
            fields, problems, _ = suite(root, scripts, cpu_budget=5, wall_ceiling=30)
            starts = [float((root / f"{g[5]}.start").read_text()) for g in groups]
            finishes = [float((root / f"{g[5]}.finish").read_text()) for g in groups]
        self.assertEqual(problems, [])
        self.assertEqual([g["status"] for g in fields["groups"]], ["PASS"] * 3)
        # All three groups were running at once: the last to start began before the first finished.
        self.assertLess(max(starts), min(finishes), f"starts {starts} finishes {finishes}")
        # The wall is about one sleep, not the three sleeps a sequential runner would take.
        self.assertGreaterEqual(fields["wall_seconds"], SLEEP)
        self.assertLess(fields["wall_seconds"], 2 * SLEEP)

    def test_each_group_is_charged_only_the_cpu_it_spent(self):
        # The budget is only meaningful if concurrent groups do not pool their CPU. Two groups burn
        # BURN seconds of CPU each while a third only waits; the parent's RUSAGE_CHILDREN would
        # charge the waiter its siblings' 2 * BURN, and os.wait4 per pid charges it nothing.
        scripts = {"burn_a*": (BURN_SCRIPT, str(BURN)), "burn_b*": (BURN_SCRIPT, str(BURN)),
                   "wait_c*": (WAIT_SCRIPT, str(2 * BURN))}
        with workspace() as temp:
            fields, problems, log = suite(Path(temp), scripts)
        self.assertEqual(problems, [])
        spent = {g["pattern"]: g["cpu_seconds"] for g in fields["groups"]}
        walls = {g["pattern"]: g["elapsed_seconds"] for g in fields["groups"]}
        if spent["wait_c*"] is None:  # a host without per-child CPU time falls back to the wall
            self.assertEqual(set(spent.values()), {None})
            return self.assertIn("no per-child CPU time", log)
        for pattern in ("burn_a*", "burn_b*"):
            self.assertLessEqual(BURN, spent[pattern], spent)
            self.assertLess(spent[pattern], BURN + STARTUP, spent)
        # The waiter spent a whole burn's worth of wall and none of the CPU that bought it.
        self.assertGreaterEqual(walls["wait_c*"], 2 * BURN)
        self.assertLess(spent["wait_c*"], STARTUP, spent)
        self.assertEqual(fields["cpu_seconds"], sum(spent.values()))

    def test_a_group_that_waits_for_a_core_passes_while_one_that_grows_fails(self):
        # Same wall, opposite verdicts: the busy-machine group is charged the CPU it spent.
        scripts = {"wait_a*": (WAIT_SCRIPT, str(2 * BURN)), "burn_b*": (BURN_SCRIPT, str(2 * BURN))}
        with workspace() as temp:
            fields, problems, log = suite(Path(temp), scripts, cpu_budget=1, wall_ceiling=60)
        statuses = {g["pattern"]: g["status"] for g in fields["groups"]}
        if fields["groups"][0]["cpu_seconds"] is None:
            return self.assertEqual(statuses, {"wait_a*": "FAIL", "burn_b*": "FAIL"})
        self.assertEqual(statuses, {"wait_a*": "PASS", "burn_b*": "FAIL"})
        self.assertEqual(len(problems), 1)
        self.assertRegex(problems[0], r"^group burn_b\* used \d+ s of CPU, over its 1-second CPU budget \(wall \d+ s\)$")
        self.assertIn("== group wait_a*: PASS in ", log)
        self.assertIn(" s CPU, ", log)

    def test_a_group_that_stops_making_progress_fails_on_the_wall_ceiling(self):
        scripts = {"wait_a*": (WAIT_SCRIPT, "30"), "ok_b*": (WAIT_SCRIPT, "0")}
        with workspace() as temp:
            fields, problems, log = suite(Path(temp), scripts, cpu_budget=60, wall_ceiling=1)
        self.assertEqual({g["pattern"]: g["status"] for g in fields["groups"]},
                         {"wait_a*": "FAIL", "ok_b*": "PASS"})
        self.assertEqual(len(problems), 1)
        self.assertRegex(problems[0], r"^group wait_a\* made no progress: it ran \d+ s, past the "
                                      r"1-second wall ceiling, for (\d+ s of|an unmeasured amount of) CPU$")
        self.assertIsNone(fields["groups"][0]["exit_code"])
        self.assertIn("== group wait_a*: FAIL in ", log)

    def test_a_failing_or_unmatched_group_fails_by_name(self):
        scripts = {"test_a*": ("print('ok')",),
                   "test_b*": ("print('FAIL: test_x (test_b.T.test_x)'); "
                               "print('FAILED (failures=1)'); raise SystemExit(1)",)}
        with workspace() as temp:
            fields, problems, log = suite(Path(temp), scripts, modules=("test_a.py", "test_b.py", "test_9.py"))
        self.assertEqual(problems, ["test module test_9.py matches no check group",
                                    "group test_b*: FAIL: test_x (test_b.T.test_x)"])
        self.assertEqual({g["pattern"]: g["status"] for g in fields["groups"]},
                         {"test_a*": "PASS", "test_b*": "FAIL"})
        self.assertIn("== group test_a*: PASS in ", log)
        self.assertIn("FAILED (failures=1)", log)
        self.assertEqual(len(fields["commands"]), 2)


if __name__ == "__main__":
    unittest.main()
