# Issue worktrees

`worktrees/` holds isolated Git checkouts. `workdir/` holds disposable build
output inside each checkout.

The root checkout is the control point. Keep it clean and on `main`. Use it to
create, inspect, and remove worktrees, not to implement changes.

## Lifecycle

1. Create a focused issue and assign its accountable owner.
2. From the root checkout, fetch `main` and create the branch and worktree:

   ```powershell
   git fetch origin
   git worktree add -b issue/42-fix-tima-reload worktrees/issue-42-fix-tima-reload origin/main
   ```

3. Comment on the issue with the agent, branch, and relative worktree path.
4. Make all edits, builds, validation, and commits in that worktree.
5. Push the branch and open a PR containing `Closes #42`.
6. Create a separate reviewer worktree at the exact PR head SHA:

   ```powershell
   git fetch origin pull/42/head:refs/review/pr-42
   git worktree add --detach worktrees/review-42-agent refs/review/pr-42
   ```

7. After agent review and required checks pass, squash merge and verify the PR.
8. From the root checkout, remove both clean worktrees and prune metadata:

   ```powershell
   git worktree remove worktrees/issue-42-fix-tima-reload
   git worktree remove worktrees/review-42-agent
   git worktree prune
   ```

9. Delete local task and review refs only after the merge is verified.

## Ownership

- One issue has one active author worktree.
- A reviewer uses a separate read-only worktree at the reviewed SHA.
- One agent owns each worktree. Never share one.
- The GitHub assignee remains accountable when an internal agent has no account.
- Transfer ownership in an issue comment before another agent continues.
- Use relative paths in issues and documentation.
- Do not force-remove a dirty worktree. Resolve or preserve its changes first.

Child directories are ignored. This file is the only tracked file here.
