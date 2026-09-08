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
gh pr merge <number> --squash --match-head-commit <reviewed-sha>
```

Do not pass `--delete-branch` from an author worktree. Root owns worktree and
branch deletion after the post-merge verification below.

If the command errors after sending the merge request, inspect remote state:

```powershell
gh pr view <number> --json state,mergedAt,mergeCommit
gh issue view <issue> --json state,closedAt
```

If merged, report the merge commit and local error to root; do not retry.
If remote state is unclear, investigate before any retry or cleanup.

For externally blocked hosted checks, use the
[standing fallback procedure](../.agents/skills/agent-flow/references/external-ci.md).
It preserves exact-head review and restores any temporary administrator setting.

## Clean up after merge

The author reports its squash merge. Root verifies the PR merged, required main
checks and deployment passed (or records the actual external blockage and local
validation under the [fallback](../wiki/agents/pull-requests.md#external-ci-fallback)),
and issues that the PR completes closed. Do not claim Pages publication from a
local build. Approved
checkpoint issues remain open with their unfinished criteria; do not close them
for cleanup.

Before deleting evidence, keep a concise summary in the PR: tested and reviewed
SHAs, exact validation commands, tool versions, results, and limitations. During
work, keep logs, waves, reports, build environments, and temporary drafts in the
author or reviewer's own `workdir/`. Do not copy them into the primary checkout
before deletion. Do not create routine artifact archives or retention manifests.
Reproducing an intermittent failure or physical condition may require more work.

Check for active users and dependencies on each worktree and its artifacts.
Preserve open PRs, unfinished work, checkpoint dependencies, and unrelated user
files. A merged checkpoint does not establish that its evidence is disposable.
Record a concrete remaining dependency in the handoff. Shared reviewer worktrees
must wait until their other work is complete.

Stop owned processes and verify their children ended before removal. For local
previews, follow [preview cleanup](../.agents/skills/agent-flow/references/preview-cleanup.md).
Inspect tracked, untracked, and ignored content. Confirm each resolved absolute
path is the intended author or reviewer directory inside this repository's
`worktrees/`. Preserve user changes; do not force-remove a dirty worktree.

Remove eligible worktrees with `git worktree remove`. Delete their known build
artifacts and temporary drafts with the worktree; follow the linked recovery
procedure if ignored output prevents removal. Do not move that output elsewhere.
Delete the verified merged local branch with `git branch -D 42-fix-timer`
(squash merges do not retain branch ancestry). Delete its remote branch if still
present, fetch with prune, and fast-forward root `main`, preserving user changes.
If fast-forwarding is blocked, report it without resetting or discarding files.
Do not delete unrelated branches or refs. End agent sessions through supported
lifecycle tools.

Apply the same completion and dependency checks to existing post-merge archives.
Delete only verified eligible exact paths; never blanket-delete `workdir/`.
Verify removal and report cleanup results in the PR or handoff, without creating
another artifact archive.

For interruption or ownership transfer, read
[recovery](../.agents/skills/agent-flow/references/recovery.md).
