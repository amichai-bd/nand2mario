"""Execute the workflow's actual policy with an isolated GitHub response."""

import contextlib
import io
import json
import os
from pathlib import Path
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
    def run_policy(self, number, branch, body, issue=None, base="main"):
        if issue is None:
            issue = {"state": "open", "assignees": [{"login": "owner"}]}
        env = {"PR_NUMBER": number, "PR_BRANCH": branch, "PR_BODY": body,
               "PR_BASE": base, "GH_REPOSITORY": "example/repo", "GH_TOKEN": "test"}
        with patch.dict(os.environ, env, clear=True), patch(
            "urllib.request.urlopen", return_value=io.StringIO(json.dumps(issue))
        ), contextlib.redirect_stdout(io.StringIO()):
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


if __name__ == "__main__":
    unittest.main()
