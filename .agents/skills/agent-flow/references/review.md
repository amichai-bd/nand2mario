# Independent review

The author requests review and root arranges another agent to review the exact
PR head SHA in a separate detached worktree. Authors never review their own
changes.

Use the installed native `review-agent` skill when available. Read its local
`SKILL.md`; it inspects the diff and returns findings without editing, posting,
pushing, or delegating. Do not copy that external skill into this repository.

The CLI also offers native review. Inspect `codex review --help` first.
For the complete PR diff in the detached reviewer checkout:

```text
git fetch origin main
codex review --base origin/main
```

`--commit <sha>` reviews only one commit, not a multi-commit PR. `--uncommitted`
is for local edits. Use only supported option combinations. A CLI run is optional
when the independent agent uses the native
skill directly. Report unavailable tooling honestly and perform the same
read-only diff review; never invent native-run evidence.

## Code, spec, and test alignment

Inspect the complete merge-base diff and linked issue criteria. Follow the
[ownership map](../../../../wiki/ownership.md) to the affected tool PRD/SPEC or
RTL MAS. Check both directions: behavioral changes in `src/` or `tools/` need
matching wiki requirements/design and tests; changed wiki behavior needs
matching implementation and tests. Check retained evidence against those rules,
not just successful command exits. Verify moved links and navigation, and keep
Markdown, HTML, and SVG documentation within the publication boundary; source
references remain external rather than copied into documentation.

Record one result in [the report](../templates/review.md):

- Aligned: cite the relevant source, spec, and test.
- No impact: explain why a refactor or documentation correction changes no
  behavior. Do not demand cosmetic counterpart edits.
- Known misalignment: link an open issue, name which side is ahead, explain why,
  and state what closes the gap. Mark future specifications as planned.

Check tool specs and tests for tooling changes. Unexplained mismatches block
readiness. A linked issue does not waive this PR's success criteria.
These are agent instructions, not a semantic CI check.

Read each issue/PR reference in changed wiki content. Internal issue links must
explain a current implementation or verification gap and point to an open issue;
closed issues and internal PR history belong outside specifications. Replace
delivery narratives with current source/test/contract links. External issue/PR
technical citations are allowed. The repository statistics page is the explicit
exception for delivery history and issue/PR measurements. Search may inventory
references, but judge and revise their surrounding prose manually.

## Verdict and PR state

Return findings, validation, residual risks, and `ready`, `changes requested`,
or `blocked`, tied to the reviewed SHA. Re-review changed material; after any
push, confirm the current SHA before readiness.

The reviewer posts its own report as a PR comment. Same-account agents use
comments, not GitHub approval. The author fixes findings and obtains a fresh
ready verdict before undrafting and merging. Reviewers do not edit, push, or
merge the branch.
