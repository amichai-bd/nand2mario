---
name: agent-flow
description: Run a nand2mario issue from human alignment through an isolated worktree, implementation, peer-agent review, green CI, squash merge, and cleanup. Use when starting, continuing, reviewing, or finishing repository work.
---

# Agent flow

Own the result until the merge and cleanup are verified. Follow `AGENTS.md` and
use the focused repository skill for the work itself.

## Inputs

- A focused issue with a goal and success criteria.
- An accountable GitHub assignee.
- Linked specifications and declared external dependencies.
- Explicit approval for hardware or another protected action when needed.

## Flow

1. Align before committing to scope.
   - Inspect the repository and linked facts first.
   - Align directly with the human by default. Use `grill-me` only when the
     human explicitly invokes it.
   - Create or refine the issue after the human confirms the scope.
2. Claim isolated work.
   - Assign the issue.
   - Keep the root checkout clean and on `main`.
   - Create `issue/<number>-<slug>` at
     `worktrees/issue-<number>-<slug>` from current `origin/main`.
   - Comment with the agent, branch, and relative worktree.
3. Run the change loop in the issue worktree.
   - Read the issue and linked specification.
   - Change specification, implementation, and tests together.
   - Run the smallest proving test, then required lower levels.
   - Repeat until the acceptance criteria have evidence.
4. Commit, push, and open a draft PR early.
   - Keep commits focused and the worktree testable.
   - Use the PR template and include every `Closes #<number>` line.
   - Record exact validation. Do not claim planned checks passed.
5. Babysit the PR.
   - Poll checks and review state until the PR can merge or needs new authority.
   - Diagnose each failure. Fix owned failures in the author worktree and push.
   - Do not rerun a deterministic failure without a change or reason.
   - Keep the issue and PR updated with decisions and useful evidence.
6. Get an independent agent review.
   - Spawn a reviewer with the issue, PR, and no implementation conclusions.
   - Give it a separate read-only worktree named
     `worktrees/review-<pr>-<agent>` at the exact PR head SHA.
   - Require findings by severity, the reviewed SHA, and a clear verdict.
   - A same-account reviewer submits a COMMENT review. GitHub does not permit the
     PR author's account to approve its own PR.
   - Fix blocking findings in the author worktree. Re-review the latest SHA after
     any material push.
7. Finish.
   - Merge only when required checks pass, conversations are resolved, and the
     latest peer-agent verdict is ready.
   - Squash merge without waiting for human approval.
   - Verify the PR merged, closing issues closed, and any deployment completed.
   - Remove reviewer and author worktrees only when clean. Prune worktree data,
     deleted remote refs, and local issue branches. Update root `main` last.

## Review verdict

Use one of:

- `ready` — no blocking findings at the stated SHA.
- `changes requested` — list concrete blockers and how to reproduce them.
- `blocked` — name the missing fact, permission, or external dependency.

Suggestions outside the issue become new issues. They do not expand the PR.

## Outputs

- An assigned issue with final evidence.
- A merged PR with green checks and a review of its final material SHA.
- Updated specifications and tests where behavior changed.
- A clean root checkout with no stale task or review worktrees.

## Stop conditions

Stop and ask when work needs a new product decision, broader scope, protected
external action, unavailable credential, or hardware action without approval.
After repeated external failure, preserve evidence and mark the issue blocked.

## Examples

Good: An agent claims issue #42, works only in its issue worktree, updates the
timer specification and tests with RTL, fixes a CI failure, gets a fresh review
of the new SHA, merges, verifies closure, and removes both worktrees.

Bad: An agent edits root `main`, opens a PR without an assigned issue, asks a
same-account subagent for a fake approval, ignores a failing check, or stops after
push without verifying merge and cleanup.
