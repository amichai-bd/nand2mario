"""The `check` host suite runs its module groups concurrently and fails by group name."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import host_suite

ROOT = Path(__file__).resolve().parents[3]


class GroupTests(unittest.TestCase):
    def test_every_module_in_the_tree_belongs_to_exactly_one_group(self):
        names = host_suite.modules(ROOT)
        self.assertIn(Path(__file__).name, names)
        for name in names:
            with self.subTest(module=name):
                self.assertEqual(sum(host_suite.fnmatch.fnmatchcase(name, g) for g in host_suite.GROUPS), 1)
        self.assertEqual(host_suite.unmatched(["test_1.py", "test_Zoo.py", "test_a.py"]), ["test_1.py", "test_Zoo.py"])

    def test_groups_run_together_and_a_failing_slow_or_unmatched_group_fails_by_name(self):
        with tempfile.TemporaryDirectory(prefix="host-suite ", dir=ROOT / "workdir") as temp:
            root = Path(temp)
            (root / host_suite.TESTS).mkdir(parents=True)
            for name in ("test_a.py", "test_b.py", "test_9.py"):
                (root / host_suite.TESTS / name).write_text("")
            scripts = {"test_a*": "import time; print('start'); time.sleep(3)",
                       "test_b*": "print('FAIL: test_x (test_b.T.test_x)'); print('FAILED (failures=1)'); raise SystemExit(1)",
                       "test_c*": "print('ok')"}
            command = lambda root, pattern: [sys.executable, "-c", scripts[pattern]]
            with patch.object(host_suite, "GROUPS", tuple(scripts)), patch.object(host_suite, "BUDGET", 1), \
                    patch.object(host_suite, "command", command):
                fields, problems = host_suite.run(root, root / "check.log")
            log = (root / "check.log").read_text()
        self.assertEqual(problems, ["test module test_9.py matches no check group",
                                    "group test_a* exceeded its 1-second wall budget",
                                    "group test_b*: FAIL: test_x (test_b.T.test_x)"])
        statuses = {g["pattern"]: g["status"] for g in fields["groups"]}
        self.assertEqual(statuses, {"test_a*": "FAIL", "test_b*": "FAIL", "test_c*": "PASS"})
        # Concurrent: the wall is the slowest group, well under the sum of the two others plus the budget.
        self.assertLess(fields["wall_seconds"], 3)
        self.assertEqual(fields["groups"][0]["exit_code"], None)
        self.assertIn("== group test_a*: FAIL in ", log)
        self.assertIn("== group test_c*: PASS in ", log)
        self.assertIn("FAILED (failures=1)", log)
        self.assertEqual(len(fields["commands"]), 3)


if __name__ == "__main__":
    unittest.main()
