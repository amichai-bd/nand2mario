# Independent review

The author requests a different agent to review the exact PR head SHA in a
separate detached worktree. Never let an author review its own change.

Use the installed native `review-agent` skill when available. Read its local
`SKILL.md`; it inspects the diff and returns findings without editing, posting,
pushing, or delegating. Do not copy that external skill into this repository.

The CLI also offers native review. Inspect `codex review --help` first.
For the complete PR diff in the detached reviewer checkout:

```text
git fetch origin main
codex review --base origin/main
```

`--commit <sha>` reviews only one commit; it is not a substitute for a multi-commit
PR review. `--uncommitted` is for local edits. Use only supported option
combinations. A CLI run is optional when the independent agent uses the native
skill directly. Report unavailable tooling honestly and perform the same
read-only diff review; never invent native-run evidence.

## Code, spec, and test alignment

Inspect the complete merge-base diff and linked issue criteria. Check both
directions: behavioral changes in `src/` need matching wiki requirements and
tests; changed wiki behavior needs matching implementation and tests.

Record one result in [the report](../templates/review.md):

- Aligned: cite the relevant source, spec, and test.
- No impact: explain why a refactor or documentation correction changes no
  behavior. Do not demand cosmetic counterpart edits.
- Known misalignment: link an open issue, name which side is ahead, explain why,
  and state what closes the gap. Mark future specifications as planned.

For tooling changes, check their tool specs and tests too. An unexplained mismatch
blocks readiness. A linked issue does not waive this PR's success criteria.
These are agent instructions, not a semantic CI check.

## Verdict and PR state

Return findings, validation, residual risks, and `ready`, `changes requested`,
or `blocked`, tied to the reviewed SHA. Re-review changed material; after any
push, confirm the current SHA before readiness.

The author posts the independent report without changing its meaning. Same-account
agents use comments, not GitHub approval. The author fixes findings and obtains
a fresh ready verdict before undrafting and merging. Reviewers stay read-only.
