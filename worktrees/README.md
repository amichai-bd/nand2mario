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
6. After required checks pass, squash merge and verify the PR is merged.
7. From the root checkout, remove the clean worktree and prune its metadata:

   ```powershell
   git worktree remove worktrees/issue-42-fix-tima-reload
   git worktree prune
   ```

8. Delete the local branch only after the merge is verified.

## Ownership

- One issue has one active worktree.
- One agent owns a worktree at a time. Never share it.
- The GitHub assignee remains accountable when an internal agent has no account.
- Transfer ownership in an issue comment before another agent continues.
- Use relative paths in issues and documentation.
- Do not force-remove a dirty worktree. Resolve or preserve its changes first.

Child directories are ignored. This file is the only tracked file here.
