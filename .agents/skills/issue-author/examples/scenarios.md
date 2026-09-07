# Scenarios

Good: "Detect stale Questa compile libraries" links the build specification,
states the failing command, and ends with checks for the fixed recreation and a
regression.

Use `bug.md` for a failure with recreation evidence, `enhancement.md` for new
observable behavior, and `specification.md` for one missing design contract.
Keep the template's matching `type:*` label; replace area and priority examples
with the issue's labels.

Bad: "Improve simulation" mixes tool setup, RTL changes, and CI work without an
observable goal.

Not a trigger: Open or update a pull request for completed work.

## Findings, not progress

Good: "The linked spec gives two reset values. Which is intended?" Comment with
the conflicting references; update the body after the decision.

Good: Document that the spec is ahead of the code, with the open drift issue and
the condition that restores alignment.

Bad: "Started work", "CI passed", "PR merged", or checking completed criteria
in the issue body. Keep ownership in the handoff and PR, and evidence in the PR.

## Safe draft handling

Save a filled template at `workdir/.tmp/issues/fix-timer.md`, then run:

```powershell
python .agents/skills/issue-author/scripts/create_issue.py --check workdir/.tmp/issues/fix-timer.md
python .agents/skills/issue-author/scripts/create_issue.py workdir/.tmp/issues/fix-timer.md
```

Keep the draft while work or review needs it; remove it with the worktree. The helper sends only the body through stdin, stripping metadata.
For edits, save a body-only Markdown file and use
`gh issue edit 42 --body-file workdir/.tmp/issues/fix-timer-body.md`.
Do not pass the metadata template directly as an edit body.

Bad: Interpolate Markdown backticks into PowerShell, encode line breaks as
literal escapes, or retry an uncertain creation without checking for an existing
issue first.
