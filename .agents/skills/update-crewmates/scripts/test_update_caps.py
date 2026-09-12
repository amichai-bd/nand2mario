from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("update_caps.py")
SPEC = importlib.util.spec_from_file_location("update_caps", SCRIPT)
assert SPEC and SPEC.loader
update_caps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_caps)

AGENTS = (
    "## Work\r\n\r\n"
    "Each root orchestration tree may have at most two open PRs, including its authors'\r\n"
    "drafts, and at most two active crewmates at any moment, including reviewers,\r\n"
    "scouts and nested agents. Reviewers are not extra capacity on top of authors:\r\n"
    "a reviewer occupies one of the two slots. So an author goes idle before its\r\n"
    "reviewer starts. These are ceilings, not targets.\r\n"
    "Open a PR only when that tree has fewer than two open. Separately\r\n"
    "user-authorized work outside that tree does not consume its slots.\r\n"
)
RECOVERY = (
    "Check the work caps before\n"
    "spawning. The reviewer takes one of the two crewmate slots, so pause or finish\n"
    "the author before requesting review.\n"
)


class UpdateCapsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.write("AGENTS.md", AGENTS)
        self.write(".agents/skills/agent-flow/references/recovery.md", RECOVERY)
        self.write("worktrees/README.md", "Preserve open PRs and unfinished work.\n")
        (self.root / "wiki/agents").mkdir(parents=True)
        (self.root / ".claude").mkdir()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        return path

    def read(self, relative: str) -> str:
        with (self.root / relative).open("r", encoding="utf-8", newline="") as stream:
            return stream.read()

    def run_script(self, *args: str) -> int:
        return update_caps.main([*args, "--root", str(self.root), "--date", "2026-01-02", "--by", "test"])

    def test_rewrites_only_the_numbers_and_keeps_line_endings(self) -> None:
        self.assertEqual(0, self.run_script("4", "2"))
        expected = AGENTS.replace("two active crewmates", "four active crewmates").replace(
            "one of the two slots", "one of the four slots")
        self.assertEqual(expected, self.read("AGENTS.md"))
        self.assertEqual(RECOVERY.replace("two crewmate", "four crewmate"),
                         self.read(".agents/skills/agent-flow/references/recovery.md"))
        self.assertIn("- 2026-01-02: crewmates 2 -> 4, open PRs 2 -> 2 (asked by test)\n",
                      self.read(update_caps.HISTORY))

    def test_changes_both_caps_and_appends_history(self) -> None:
        self.assertEqual(0, self.run_script("3", "1"))
        self.assertEqual(0, self.run_script("5", "6"))
        text = self.read("AGENTS.md")
        self.assertIn("at most six open PRs", text)
        self.assertIn("fewer than six open.", text)
        self.assertIn("at most five active crewmates", text)
        history = self.read(update_caps.HISTORY).splitlines()
        self.assertEqual("- 2026-01-02: crewmates 2 -> 3, open PRs 2 -> 1 (asked by test)", history[-2])
        self.assertEqual("- 2026-01-02: crewmates 3 -> 5, open PRs 1 -> 6 (asked by test)", history[-1])

    def test_stale_statement_outside_the_list_fails_naming_file_and_line(self) -> None:
        self.write("wiki/agents/notes.md", "Intro.\nRoot may run 2 crewmates at once.\n")
        self.assertEqual(1, self.run_script("4", "2"))
        self.assertIn("at most four active crewmates", self.read("AGENTS.md"))
        self.assertEqual(1, self.run_script("4", "2", "--check"))
        found, stale = update_caps.verify(self.root, {"crewmates": 4, "prs": 2})
        self.assertEqual(5, len(found))
        self.assertEqual(1, len(stale))
        self.assertTrue(stale[0].startswith("wiki/agents/notes.md:2: crewmates=2"))

    def test_check_reports_disagreement_without_writing(self) -> None:
        self.assertEqual(1, self.run_script("4", "2", "--check"))
        self.assertEqual(AGENTS, self.read("AGENTS.md"))
        self.assertFalse((self.root / update_caps.HISTORY).exists())
        self.assertEqual(0, self.run_script("2", "2", "--check"))

    def test_check_without_numbers_uses_the_last_history_entry(self) -> None:
        self.assertEqual(1, update_caps.main(["--check", "--root", str(self.root)]))
        self.assertEqual(0, self.run_script("4", "2"))
        self.assertEqual(0, update_caps.main(["--check", "--root", str(self.root)]))
        self.write("wiki/agents/notes.md", "at most two active crewmates\n")
        self.assertEqual(1, update_caps.main(["--check", "--root", str(self.root)]))
        self.assertEqual(1, update_caps.main(["4", "--root", str(self.root)]))

    def test_refuses_ambiguous_location_before_writing(self) -> None:
        self.write("AGENTS.md", AGENTS + "Again: at most two open PRs.\n")
        self.assertEqual(1, self.run_script("4", "2"))
        self.assertEqual(AGENTS + "Again: at most two open PRs.\n", self.read("AGENTS.md"))
        self.assertEqual(RECOVERY, self.read(".agents/skills/agent-flow/references/recovery.md"))

    def test_rejects_numbers_without_a_word(self) -> None:
        self.assertEqual(1, self.run_script("13", "2"))
        self.assertEqual(1, self.run_script("0", "2"))
        self.assertEqual(AGENTS, self.read("AGENTS.md"))


if __name__ == "__main__":
    unittest.main()
