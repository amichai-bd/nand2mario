# Issue worktrees

The root checkout stays clean on `main`. It orchestrates isolated author and
reviewer checkouts. `workdir/` stores generated output inside each checkout.

## Create

Root selects an assigned issue and delegates one author. From the root:

```powershell
git fetch origin
git worktree add -b 42-fix-timer worktrees/42-fix-timer origin/main
```

The branch and author directory have the same name: `<number>-<slug>`.
`<repo-root>` means the root orchestration checkout, not a required environment
variable. Record the agent, branch, and relative worktree in the orchestration
handoff before editing, then in the PR when opened. Never share a worktree.

For PR 51, resolve its current head and give a different agent a detached
checkout named `worktrees/review-51-<sha7>/`:

```powershell
git fetch origin pull/51/head
git rev-parse FETCH_HEAD
# Substitute the returned full SHA and its first seven characters:
git worktree add --detach worktrees/review-51-<sha7> <full-sha>
```

Follow [agent-flow](../.agents/skills/agent-flow/SKILL.md) for review and babysitting.

## Clean up after merge

The author reports its squash merge. Root verifies the PR merged, its closing
issues closed, and required main checks/deployment passed. Stop active users of
the worktrees before removing them. If a worktree ran a local preview, follow
[preview cleanup](../.agents/skills/agent-flow/references/preview-cleanup.md).

Check both worktrees are clean. Resolve their full paths and confirm they are
inside this repository's `worktrees/`. Do not force-remove dirty worktrees.
Retain temporary drafts by moving their ignored `workdir/.tmp/` content to root
`workdir/.tmp/` before removal; preserve same-name collisions under distinct
names. Keep useful evidence until its linked retention need is satisfied.

Then remove the exact author and reviewer worktrees with `git worktree remove`.
Delete the verified merged local branch with `git branch -D 42-fix-timer`
(squash merges do not retain branch ancestry). Delete its remote branch if still
present, fetch with prune, and fast-forward root `main`. Do not delete unrelated
branches or refs. End agent sessions through supported lifecycle tools.

For interruption or ownership transfer, read
[recovery](../.agents/skills/agent-flow/references/recovery.md).
