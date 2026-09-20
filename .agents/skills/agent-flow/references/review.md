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

## When the head moves after a verdict

A verdict covers the SHA it names and nothing later. Three ordinary things move
the head between a `ready` verdict and the merge: the author applies a reviewer
finding, the author applies something root asked for, or `main` moves and the
base branch requires an up-to-date branch, which makes that rebase mandatory
rather than a choice. A merge handoff cannot authorize a change and a merge in
one breath; the change needs its disposition first. Classify each move, state its
disposition in the PR, and merge only at a head a verdict covers.

**A content change goes back to the reviewer, who decides.** Any commit that
alters content the reviewer read returns the PR to that reviewer, whatever its
size: an applied finding, a wording correction, a re-measurement, a new file.
The reviewer re-reviews the changed material and posts a verdict naming the new
SHA. That pass may be scoped to what moved instead of a full pass, but the
reviewer judges that, not the author. An author never rules its own edit too
small to review.

**A rebase that carries no content change keeps the verdict, and the author
proves it.** The author decides this case, because the claim is mechanical: every
path the PR changes holds at the new head the same content it held at the
reviewed SHA. State that disposition in the PR with per-file evidence, not a
patch summary:

- each changed path's blob hash at the reviewed SHA and at the new head, from
  `git rev-parse <sha>:<path>`, quoted as a matching pair;
- the merge-base diff file list against current `origin/main`, showing that the
  commits the rebase pulled in touch none of those paths.

An empty `git diff <reviewed-sha> <new-head> -- <path>` supports the claim but
does not replace it. The blob pair states the result per file and survives
quoting into the PR body, which is where the next agent reads it. Once stated
with that evidence, the disposition makes the new head the reviewed head, and
that SHA is the one the merge pins.

**A blob that moved is a content change on its path**, whichever commit moved
it. When `main` edited a path this branch also edits, the rebase combined two
edits there: name that path, show the branch's own contribution to it, and send
that path to the reviewer. The paths whose blobs match keep their verdict.

The [merge step](../../../../worktrees/README.md#merge) checks the delivered head
against the verdict rather than assuming they agree.
