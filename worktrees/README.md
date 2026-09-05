# Issue worktrees

Setup, merge, and cleanup methods for the [work rules](../AGENTS.md#work).

## Create

Root selects an assigned issue and delegates one author. From root:

```powershell
git fetch origin
git worktree add -b 42-fix-timer worktrees/42-fix-timer origin/main
```

`<repo-root>` means the root orchestration checkout, not a required environment
variable. Record the agent, branch, and relative worktree in the orchestration
handoff before editing, then in the PR when opened. See
[recovery](../.agents/skills/agent-flow/references/recovery.md#retained-context)
for retained context.

For PR 51, resolve its current head and give a different agent a detached
checkout named `worktrees/review-51-<sha7>/`:

```powershell
git fetch origin pull/51/head
git rev-parse FETCH_HEAD
# Substitute the returned full SHA and its first seven characters:
git worktree add --detach worktrees/review-51-<sha7> <full-sha>
```

Follow [agent-flow](../.agents/skills/agent-flow/SKILL.md) for review and babysitting.

## Merge

Once [review readiness](../.agents/skills/agent-flow/references/review.md#verdict-and-pr-state)
and the [delivery obligations](../AGENTS.md#work) are met, the author runs:

```powershell
gh pr merge <number> --squash
```

Do not pass `--delete-branch` from an author worktree. Root owns worktree and
branch deletion after it verifies the merge and deployment.

If the command errors after sending the merge request, inspect remote state:

```powershell
gh pr view <number> --json state,mergedAt,mergeCommit
gh issue view <issue> --json state,closedAt
```

If merged, report the merge commit and local error to root; do not retry.
If remote state is unclear, investigate before any retry or cleanup.

## Clean up after merge

The author reports its squash merge. Root verifies the PR merged, its closing
issues closed, and required main checks/deployment passed. Stop active worktree
users before removal. If a worktree ran a local preview, follow
[preview cleanup](../.agents/skills/agent-flow/references/preview-cleanup.md).

Check both worktrees are clean and their resolved full paths are inside this
repository's `worktrees/`. Do not force-remove dirty worktrees.
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
