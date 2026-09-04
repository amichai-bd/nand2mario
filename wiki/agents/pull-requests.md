# Branches and pull requests

## Default flow

Prefer one issue, one observable result, one branch, and one pull request.

Name every work branch:

```text
issue/<primary-number>-<lowercase-slug>
```

Example:

```text
issue/42-fix-tima-reload
```

Create its worktree at:

```text
worktrees/issue-42-fix-tima-reload
```

The root checkout stays clean and on `main`. All changes, builds, commits, and
PR updates happen from the issue worktree. See the
[worktree lifecycle](../../worktrees/README.md).

## Issue closure

Every PR must close at least one issue. Put each closing reference on its own
line in the PR body:

```text
Closes #42
```

The primary issue number in the branch name must be included. A PR may close
more issues when one focused change satisfies all of them:

```text
Closes #42
Closes #47
```

Do not combine unrelated issues to reduce the number of PRs. Split the work
when the goals, specifications, validation, or rollback paths differ.

## PR content

The PR template asks for:

- a short result;
- closing issue references;
- specification impact;
- the focused changes;
- exact validation and evidence; and
- the main risk.

The PR explains the completed change. The issue remains the work guide and owns
the goal and success criteria.

## Agent review and ownership

The authoring agent owns the PR through verified merge and cleanup. It polls
checks and review state, diagnoses failures, fixes owned failures in the author
worktree, and pushes until the PR is ready.

An independent agent reviews the exact head SHA from a separate read-only
worktree. Its review records the agent, SHA, verdict, and findings. A material
push invalidates the verdict and requires another review. A same-account agent
uses a COMMENT review because GitHub does not allow authors to approve their own
PRs. Zero approving reviews are required; a `ready` peer-agent verdict is the
project gate.

After merge, verify issue closure and any deployment before removing worktrees
and branches. Detailed steps live in the `agent-flow` skill.

## Policy check

The `PR policy` workflow checks:

- the branch matches `issue/<number>-<slug>`;
- the base branch is `main`;
- the PR body contains at least one `Closes #<number>`; and
- the PR closes the primary issue named by the branch; and
- every closing reference is an open issue with an assignee.

## Main protection

`main` requires:

- a pull request;
- a passing, up-to-date `PR policy` check;
- linear history;
- resolved review conversations; and
- no force-push or branch deletion.

No human approving review is required. Peer-agent review evidence is required by
the repository process until a distinct reviewer identity can enforce it.

GitHub closes every referenced issue when the PR merges into `main`. See
[Linking a pull request to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).
