---
name: agent-flow
description: Run a nand2mario issue through its worktree, peer review, green CI, merge, and cleanup. Use when starting, continuing, reviewing, or finishing repository work.
---

# Agent flow

One root orchestrator selects issues. Authors babysit their PRs until merged.

1. Align directly; use `grill-me` only on explicit invocation.
2. Create or pick an assigned issue. Root delegates one author and records
   ownership using [the worktree guide](../../../worktrees/README.md).
3. Author reads the issue and spec, then loops on specification, code, and tests.
   Keep routine updates in the handoff or PR; follow the
   [issue update rules](../../../wiki/agents/issues.md#agent-use).
4. Commit, push, and open a draft PR using `pr-author`.
5. Babysit: poll CI, fix failures, and request an independent review following
   [the review guide](references/review.md).
6. After a ready verdict for the current SHA and green checks, author posts the
   report, undrafts, squash merges, and reports the merge to root.
7. Root verifies merge, issue closure, deployment, and cleanup using the worktree
   guide. For worktrees that ran a local preview, read
   [preview cleanup](references/preview-cleanup.md). End author and reviewer
   sessions through available lifecycle tools.

Read [recovery and capacity](references/recovery.md) for delegation or interrupted
work. Use [the review template](templates/review.md) and
[scenarios](examples/scenarios.md) for review handoffs.

Stop for a new product decision, broader scope, missing credentials, or an
unauthorized hardware action. Routine Pages deployment already has authorization.
