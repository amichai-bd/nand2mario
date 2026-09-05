# Branches and pull requests

Follow the [agent work rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md#work)
for branch naming, worktree ownership, draft state, and issue scope.
Use a lowercase branch slug, such as `42-fix-timer`.
Each closing reference has its own line:

```text
Closes #42
```

The issue owns the goal; the PR describes the result and evidence. Use the
[PR skill](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/pr-author/SKILL.md) for retained body files and
the [agent flow](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/agent-flow/SKILL.md) for babysitting,
independent review, author undrafting, squash merge, and root cleanup.

## Policy and protection

The `PR policy` check requires a valid numbered branch, `main` base, and closing
references to open assigned issues including the primary branch issue.
`Wiki check` validates the documentation build.

Main requires passing up-to-date checks, linear history, and resolved review
conversations. Force pushes and branch deletion are blocked on main. Human
approval is not required. Independent review and code/spec alignment are agent
responsibilities; they are not enforced by scripts or approval counts.

A merge closes the referenced issues and automatically deploys Pages. See
[GitHub issue linking](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).
