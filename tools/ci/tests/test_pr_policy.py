"""Execute the workflow's actual policy with an isolated GitHub response."""

import contextlib
import io
import json
import os
from pathlib import Path
import re
import textwrap
import unittest
from unittest.mock import patch


POLICY = textwrap.dedent(
    (Path(__file__).resolve().parents[3] / ".github/workflows/pr-policy.yml")
    .read_text(encoding="utf-8")
    .split("python3 - <<'PY'\n", 1)[1]
    .rsplit("          PY", 1)[0]
)


class PrPolicyTests(unittest.TestCase):
    def run_policy(self, number, branch, body, issue=None, base="main", title="Title", files=None):
        if issue is None:
            issue = {"state": "open", "assignees": [{"login": "owner"}]}
        if files is None:
            files = ["tools/ci/README.md"]
        env = {"PR_NUMBER": number, "PR_BRANCH": branch, "PR_BODY": body, "PR_TITLE": title,
               "PR_BASE": base, "GH_REPOSITORY": "example/repo", "GH_TOKEN": "test"}

        def urlopen(request):
            self.urls.append(request.full_url)
            match = re.fullmatch(rf".*/pulls/{number}/files\?per_page=100(?:&page=(\d+))?", request.full_url)
            if match:
                entries = [{"filename": name, "status": "modified"} if isinstance(name, str) else name
                           for name in files]
                page = int(match.group(1) or 1)
                return io.StringIO(json.dumps(entries[(page - 1) * 100:page * 100]))
            return io.StringIO(json.dumps(issue))

        self.urls = []
        self.output = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch(
            "urllib.request.urlopen", urlopen
        ), contextlib.redirect_stdout(self.output):
            try:
                exec(compile(POLICY, "pr-policy.yml", "exec"), {})
            except SystemExit as error:
                return error.code
        return 0

    def test_approved_pairs(self):
        for number, issue in (("162", "156"), ("163", "88"), ("167", "164"), ("169", "168"), ("179", "168")):
            with self.subTest(number=number):
                self.assertEqual(0, self.run_policy(
                    number, f"{issue}-checkpoint", f"Checkpoint for #{issue}\nRefs #{issue}"))

    def test_checkpoint_rejections(self):
        valid = "Checkpoint for #156\nRefs #156"
        cases = [("164", "156-checkpoint", valid),
                 ("162", "88-checkpoint", valid),
                 ("162", "156-checkpoint", "Refs #156"),
                 ("162", "156-checkpoint", "Checkpoint for #156"),
                 ("162", "156-checkpoint", "Checkpoint for #88\nRefs #88")]
        cases += [("162", "156-checkpoint", valid + "\n" + closing + " #88")
                  for closing in ("Closes", "Fixes", "Resolved", "close", "fix")]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(1, self.run_policy(*args))

    def test_issue_validation_remains_required(self):
        for issue in ({"state": "closed", "assignees": [{"login": "owner"}]},
                      {"state": "open", "assignees": []},
                      {"pull_request": {}, "state": "open", "assignees": [{"login": "owner"}]}):
            with self.subTest(issue=issue):
                self.assertEqual(1, self.run_policy(
                    "162", "156-checkpoint", "Checkpoint for #156\nRefs #156", issue))

    def test_ordinary_policy(self):
        self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165"))
        self.assertEqual(1, self.run_policy("166", "165-policy", "Closes #164"))
        self.assertEqual(1, self.run_policy("166", "bad", "Closes #165"))
        self.assertEqual(1, self.run_policy("166", "165-policy", "Closes #165", base="other"))

    AUTOMATED = ("400", "stats-refresh-20260911T120000Z", "Refresh the snapshot to `abc`.\n\nRefs #392\n")
    AUTOMATED_TITLE = "stats: refresh snapshot to 0123abc"
    SNAPSHOT = ["wiki/statistics.html"]

    def test_automated_statistics_refresh_accepted(self):
        self.assertEqual(0, self.run_policy(*self.AUTOMATED, title=self.AUTOMATED_TITLE, files=self.SNAPSHOT))
        # The class reads only the changed-file set; it never needs #392 open.
        self.assertEqual(["https://api.github.com/repos/example/repo/pulls/400/files?per_page=100"], self.urls)

    def test_automated_statistics_refresh_rejections(self):
        number, branch, body = self.AUTOMATED
        title = self.AUTOMATED_TITLE
        cases = {
            "branch suffix": dict(branch="stats-refresh-20260911T120000Z-2"),
            "branch case": dict(branch="stats-refresh-20260911t120000z"),
            "title free text": dict(title="stats: refresh snapshot"),
            "title long sha": dict(title="stats: refresh snapshot to 0123abcd"),
            "title suffix": dict(title=title + " again"),
            "body without refs": dict(body="Refresh the snapshot.\n"),
            "body other issue": dict(body="Refs #391\n"),
            "body closes": dict(body=body + "Closes #392\n"),
            "body fixes": dict(body=body + "Fixes #7\n"),
            "extra file": dict(files=["tools/wiki/refresh_statistics.py", "wiki/statistics.html"]),
            "other file": dict(files=["wiki/index.md"]),
            "no file": dict(files=[]),
            "snapshot added": dict(files=[{"filename": "wiki/statistics.html", "status": "added"}]),
            "snapshot removed": dict(files=[{"filename": "wiki/statistics.html", "status": "removed"}]),
            "base": dict(base="other"),
        }
        for name, override in cases.items():
            with self.subTest(case=name):
                args = dict(number=number, branch=branch, body=body, title=title, files=self.SNAPSHOT)
                args.update(override)
                self.assertEqual(1, self.run_policy(**args))

    def test_ordinary_pr_must_not_change_the_snapshot(self):
        # Issue #442: only the automated refresh may move wiki/statistics.html.
        for files in (self.SNAPSHOT,
                      ["src/rtl/cpu/sm83.sv", "wiki/statistics.html"],
                      [{"filename": "wiki/statistics.html", "status": "removed"}]):
            with self.subTest(files=files):
                self.assertEqual(1, self.run_policy("166", "165-policy", "Closes #165", files=files))
                self.assertIn("::error::wiki/statistics.html is generated", self.output.getvalue())
                self.assertIn("stats-refresh-", self.output.getvalue())
        # Checkpoints are ordinary PRs for this rule too.
        self.assertEqual(1, self.run_policy("162", "156-checkpoint", "Checkpoint for #156\nRefs #156",
                                            files=self.SNAPSHOT))
        # Other files, and a look-alike path, stay allowed.
        self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165",
                                            files=["wiki/project-statistics.md", "tools/wiki/refresh_statistics.py"]))
        self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165", files=[]))

    def test_ordinary_pr_snapshot_is_found_past_the_first_files_page(self):
        many = [f"src/rtl/file{index}.sv" for index in range(100)]
        self.assertEqual(1, self.run_policy("166", "165-policy", "Closes #165", files=many + self.SNAPSHOT))
        self.assertEqual(2, sum("/files?" in url for url in self.urls))
        self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165", files=many + ["wiki/index.md"]))

    def test_ordinary_rules_ignore_the_automated_title(self):
        self.assertEqual(1, self.run_policy("166", "165-policy", "Refs #392", title=self.AUTOMATED_TITLE))
        self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165", title=self.AUTOMATED_TITLE))


if __name__ == "__main__":
    unittest.main()
