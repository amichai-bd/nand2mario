# Scenarios

Good: Claim an assigned issue, work only in its worktree, fix CI, get a fresh
review after the last material push, merge, verify closure, and clean both
worktrees.

Bad: Edit root `main`, accept a stale review, rerun a deterministic failure
without a change, or stop after opening the PR.

A same-account reviewer leaves a COMMENT review. It does not claim to approve
the author's PR. The recorded `ready` verdict is the project gate.

Not a trigger: A design question that has no issue work to start or finish.
