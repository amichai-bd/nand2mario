---
name: agent-flow
description: Run a nand2mario issue through its worktree, peer review, green CI, merge, and cleanup. Use when starting, continuing, reviewing, or finishing repository work.
---

# Agent flow

Own the result until merge and cleanup are verified. Follow `AGENTS.md` and the
focused skill for the work.

1. Align with the user. Use `grill-me` only when explicitly invoked.
2. Create or refine a focused issue. Start only when it has an assignee.
3. Claim a branch and issue worktree as defined in `worktrees/README.md`.
4. Work in the issue worktree. Keep specification, code, and tests aligned.
5. Commit, push, and open a PR that closes the issue.
6. Poll checks. Fix owned failures and review findings.
7. Get an independent agent review of the exact head SHA.
8. Squash merge when checks and review pass. Verify closure, then clean up.

Use [the review template](templates/review.md) for the peer-agent handoff. Read
[the scenarios](examples/scenarios.md) when the ownership or retry boundary is
unclear.

Stop for a new product decision, broader scope, protected action, missing
credential, or hardware action without approval.
