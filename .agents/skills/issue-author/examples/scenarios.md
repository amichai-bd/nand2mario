# Scenarios

Good: "Detect stale Questa compile libraries" links the build specification,
states the failing command, and ends with checks for the fixed recreation and a
regression.

Use `bug.md` for a failure with recreation evidence, `enhancement.md` for new
observable behavior, and `specification.md` for one missing design contract.
Keep the matching `type:*` label from that template and replace its area and
priority examples with the issue's real labels.

Bad: "Improve simulation" mixes tool setup, RTL changes, and CI work without an
observable goal.

Not a trigger: Open or update a pull request for completed work.

## Safe draft handling

Save a filled template at `workdir/.tmp/issues/fix-timer.md`, then run:

```powershell
python .agents/skills/issue-author/scripts/create_issue.py --check workdir/.tmp/issues/fix-timer.md
python .agents/skills/issue-author/scripts/create_issue.py workdir/.tmp/issues/fix-timer.md
```

Keep the draft. The helper strips its metadata and sends only the body through
stdin. For edits, save a body-only Markdown file and use
`gh issue edit 42 --body-file workdir/.tmp/issues/fix-timer-body.md`.
Do not pass the metadata template directly as an edit body.

Bad: Interpolate Markdown backticks into PowerShell, encode line breaks as
literal escapes, or retry an uncertain creation without checking for an existing
issue first.
