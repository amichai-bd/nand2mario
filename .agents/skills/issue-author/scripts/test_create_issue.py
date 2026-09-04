from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("create_issue.py")
SPEC = importlib.util.spec_from_file_location("create_issue", SCRIPT)
assert SPEC and SPEC.loader
create_issue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(create_issue)


class CreateIssueTest(unittest.TestCase):
    def write(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "issue draft.md"
        with path.open("w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        return path

    def test_preserves_body_and_keeps_values_in_single_arguments(self) -> None:
        body = (
            "## TL;DR\r\n\r\nKeep  two spaces, `ticks`, an apostrophe's value, and café.\r\n\r\n"
            "## Specification reference\r\n\r\n- `wiki/CPU plan.md`\r\n\r\n"
            "## Context\r\n\r\nLine one.\r\nLine two: 日本語.\r\n\r\n"
            "## Goal\r\n\r\nPreserve exact Markdown.\r\n\r\n"
            "## Success criteria\r\n\r\n- [ ] Body is unchanged.\r\n"
        )
        title = "Keep spaces, `ticks`, apostrophe's text, and 日本語"
        metadata_source = {
            "title": title,
            "labels": ["type:enhancement", "area:agents"],
            "assignee": "@me",
            "repo": "owner/repo",
        }
        meta = f"<!-- issue-meta: {json.dumps(metadata_source, ensure_ascii=False)} -->\r\n"
        path = self.write(meta + body)
        metadata, parsed_body = create_issue.read_draft(path)
        self.assertEqual(body, parsed_body)

        completed = subprocess.CompletedProcess([], 0, b"https://example/1\n", b"")
        with patch.object(create_issue.subprocess, "run", return_value=completed) as run:
            url = create_issue.create_issue(metadata, parsed_body)

        self.assertEqual("https://example/1", url)
        args, kwargs = run.call_args
        command = args[0]
        self.assertIsInstance(command, list)
        self.assertEqual(title, command[command.index("--title") + 1])
        self.assertEqual(body.encode("utf-8"), kwargs["input"])
        self.assertNotIn("shell", kwargs)

    def test_rejects_wrong_shared_heading_order(self) -> None:
        draft = (
            '<!-- issue-meta: {"title":"Bad order","labels":["type:bug"],'
            '"assignee":"@me","repo":"owner/repo"} -->\n'
            "## Specification reference\n\nwiki/a.md\n\n## TL;DR\n\nWrong.\n\n"
            "## Goal\n\nFix it.\n\n## Success criteria\n\n- [ ] Fixed.\n"
        )
        with self.assertRaisesRegex(create_issue.DraftError, "must start"):
            create_issue.read_draft(self.write(draft))

    def test_rejects_unknown_metadata_field(self) -> None:
        metadata = {
            "title": "A",
            "labels": ["type:bug"],
            "assignee": "@me",
            "repo": "owner/repo",
            "titel": "typo",
        }
        with self.assertRaisesRegex(create_issue.DraftError, "unknown titel"):
            create_issue.validate_metadata(metadata)


if __name__ == "__main__":
    unittest.main()
