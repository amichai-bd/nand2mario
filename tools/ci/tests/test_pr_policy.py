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
    HEAD = "27a0a6e21be3be7b6af3b9b288cc60de6c89b24e"

    def run_policy(self, number, branch, body, issue=None, base="main", title="Title", files=None,
                   head=HEAD):
        if issue is None:
            issue = {"state": "open", "assignees": [{"login": "owner"}]}
        if files is None:
            files = ["tools/ci/README.md"]
        env = {"PR_NUMBER": number, "PR_BRANCH": branch, "PR_BODY": body, "PR_TITLE": title,
               "PR_BASE": base, "PR_HEAD_SHA": head, "GH_REPOSITORY": "example/repo", "GH_TOKEN": "test"}

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
                      [{"filename": "wiki/statistics.html", "status": "removed"}],
                      [{"filename": "wiki/old-statistics.html", "status": "renamed",
                        "previous_filename": "wiki/statistics.html"}],
                      [{"filename": "wiki/statistics.html", "status": "renamed",
                        "previous_filename": "wiki/stats.html"}]):
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
        self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165", files=[
            {"filename": "wiki/stats.md", "status": "renamed", "previous_filename": "wiki/project-statistics.md"}]))

    def test_ordinary_pr_snapshot_is_found_past_the_first_files_page(self):
        many = [f"wiki/pages/file{index}.md" for index in range(100)]
        self.assertEqual(1, self.run_policy("166", "165-policy", "Closes #165", files=many + self.SNAPSHOT))
        self.assertEqual(2, sum("/files?" in url for url in self.urls))
        self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165", files=many + ["wiki/index.md"]))

    def test_ordinary_rules_ignore_the_automated_title(self):
        self.assertEqual(1, self.run_policy("166", "165-policy", "Refs #392", title=self.AUTOMATED_TITLE))
        self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165", title=self.AUTOMATED_TITLE))

    RTL = ["src/rtl/cpu/sm83.sv"]
    GATE = textwrap.dedent("""\
        ```text
        Questa compile gate
        head: 27a0a6e
        vlog: Questa Altera Starter FPGA Edition-64 vlog 2025.2 Compiler 2025.05 May 31 2025
        vopt: Questa Altera Starter FPGA Edition-64 vopt 2025.2 Compiler 2025.05 May 31 2025
        sources: 88
        tops: 14
        elapsed_seconds: 39.5
        attempt_result: workdir/builds/lint-660-r2/lint/questa/02d3f292c922/result.json
        status: PASS
        ```
        """)

    def gate_body(self, **replace):
        block = self.GATE
        for key, value in replace.items():
            block = re.sub(rf"(?m)^{key}:.*$", f"{key}: {value}".rstrip(), block)
        return f"Result.\n\n{block}\nCloses #165\n"

    def test_rtl_change_needs_the_questa_gate_block(self):
        for files in (self.RTL, ["src/fpga/de10_lite/targets.json"], ["wiki/index.md", "src/fpga/top.sv"],
                      [{"filename": "src/rtl/new.sv", "status": "renamed",
                        "previous_filename": "src/rtl/old.sv"}],
                      [{"filename": "src/dv/x.sv", "status": "renamed", "previous_filename": "src/rtl/x.sv"}]):
            with self.subTest(files=files):
                self.assertEqual(1, self.run_policy("166", "165-policy", "Closes #165", files=files))
                output = self.output.getvalue()
                self.assertIn("::error::Changed files under src/rtl or src/fpga", output)
                self.assertIn("wiki/tools/n2m/SPEC.md#questa-compile-gate", output)

    def test_rtl_change_passes_with_a_pass_block_at_the_head(self):
        self.assertEqual(0, self.run_policy("166", "165-policy", self.gate_body(), files=self.RTL))
        self.assertIn("Questa compile gate PASS recorded for head 27a0a6e: 88 sources, 14 tops, 39.5 s.",
                      self.output.getvalue())
        # Full SHA, CRLF bodies from the web editor, and a plain fence are accepted.
        self.assertEqual(0, self.run_policy("166", "165-policy", self.gate_body(head=self.HEAD), files=self.RTL))
        self.assertEqual(0, self.run_policy("166", "165-policy", self.gate_body().replace("\n", "\r\n"),
                                            files=self.RTL))
        self.assertEqual(0, self.run_policy("166", "165-policy", self.gate_body().replace("```text", "```"),
                                            files=self.RTL))
        # An older FAIL block may stay in the body when a PASS block names the head.
        stale = self.gate_body(head="0c02984", status="FAIL").split("Closes")[0]
        self.assertEqual(0, self.run_policy("166", "165-policy", stale + self.gate_body(), files=self.RTL))

    def test_rtl_change_fails_with_a_stale_head(self):
        for head in ("410a279", "27a0a6", "27a0a6e21be3be7b6af3b9b288cc60de6c89b24f", ""):
            with self.subTest(head=head):
                self.assertEqual(1, self.run_policy("166", "165-policy", self.gate_body(head=head), files=self.RTL))
                output = self.output.getvalue()
                self.assertIn("but the PR head is 27a0a6e", output)
                self.assertIn("rerun 'python tools/build.py lint questa", output)
        # The same block is stale once the PR head moves.
        self.assertEqual(1, self.run_policy("166", "165-policy", self.gate_body(), files=self.RTL,
                                            head="410a279e8ec800089d786f405bb3d2dc4f9de5fc"))

    def test_rtl_change_fails_with_a_fail_result(self):
        for status in ("FAIL", "pass", "PASS (see below)"):
            with self.subTest(status=status):
                self.assertEqual(1, self.run_policy("166", "165-policy", self.gate_body(status=status),
                                                    files=self.RTL))
                self.assertIn(f"::error::Questa compile gate at 27a0a6e reports status {status}",
                              self.output.getvalue())

    def test_rtl_change_fails_with_missing_or_malformed_fields(self):
        for key in ("vlog", "vopt", "sources", "tops", "elapsed_seconds", "attempt_result", "status"):
            with self.subTest(missing=key):
                self.assertEqual(1, self.run_policy("166", "165-policy", self.gate_body(**{key: ""}),
                                                    files=self.RTL))
                self.assertIn(f"::error::Questa compile gate evidence block lacks {key}", self.output.getvalue())
        for key, value in (("sources", "many"), ("tops", "0"), ("elapsed_seconds", "40 s")):
            with self.subTest(malformed=key):
                self.assertEqual(1, self.run_policy("166", "165-policy", self.gate_body(**{key: value}),
                                                    files=self.RTL))
                self.assertIn("integer sources and tops counts", self.output.getvalue())
        # Keyed lines outside a fenced block are prose, not evidence.
        self.assertEqual(1, self.run_policy("166", "165-policy", self.gate_body().replace("```", ""),
                                            files=self.RTL))

    def test_other_changes_ignore_the_questa_gate(self):
        # Issue #663's own file set: builder stand-ins live under src/dv, not src/rtl.
        for files in (["tools/n2m/lint.py", "src/dv/builder/questa_lint_vendor.sv", "wiki/tools/n2m/SPEC.md"],
                      ["src/rtl_notes.md", "docs/src/rtl/x.sv"], []):
            with self.subTest(files=files):
                self.assertEqual(0, self.run_policy("166", "165-policy", "Closes #165", files=files))
                self.assertNotIn("Questa", self.output.getvalue())
        # The block is harmless when present without RTL changes, whatever it says.
        self.assertEqual(0, self.run_policy("166", "165-policy", self.gate_body(status="FAIL", head="deadbee")))
        # Checkpoints and the ordinary rules still apply to RTL PRs.
        self.assertEqual(1, self.run_policy("162", "156-checkpoint", "Checkpoint for #156\nRefs #156",
                                            files=self.RTL))
        self.assertEqual(1, self.run_policy("166", "165-policy", self.gate_body().replace("#165", "#164"),
                                            files=self.RTL))


if __name__ == "__main__":
    unittest.main()
