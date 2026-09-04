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

## Policy check

The `PR policy` workflow checks:

- the branch matches `issue/<number>-<slug>`;
- the PR body contains at least one `Closes #<number>`; and
- the PR closes the primary issue named by the branch.

## Main protection

`main` requires:

- a pull request;
- a passing, up-to-date `PR policy` check;
- linear history;
- resolved review conversations; and
- no force-push or branch deletion.

No approving review count is required yet.

GitHub closes every referenced issue when the PR merges into `main`. See
[Linking a pull request to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).
