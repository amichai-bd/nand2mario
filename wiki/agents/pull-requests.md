# Branches and pull requests

Follow the [agent work rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md#work)
for branch naming, worktree ownership, draft state, and issue scope.
Use a lowercase branch slug, such as `42-fix-timer`.
Each closing reference has its own line:

```text
Closes #42
```

The issue owns the goal; the PR describes the result and evidence. Use the
[PR skill](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/pr-author/SKILL.md) for temporary body files and
the [agent flow](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/agent-flow/SKILL.md) for babysitting,
independent review, author undrafting, squash merge, and root cleanup.

## Scoped implementation and milestones

An implementation PR closes its own independently useful issue. Its criteria
select the applicable [verification tiers](../src/dv/integration/SPEC.md#verification-tiers);
full milestone acceptance belongs to named open milestone issues, referenced in
the PR. With scope authorization, revise existing issue boundaries explicitly:
state what lands, its required proof, and what remains in each open issue. Do not
label a partial subsystem or milestone complete. A known defect that undermines
the scoped result still blocks that PR, and introduced regressions remain its
responsibility. Finish the finite checklist and merge when scoped acceptance,
required CI, independent current-head review and conversations are satisfied.

For the authorized current split, [#178](https://github.com/amichai-bd/nand2mario/issues/178)
owns delivery and bounded complete-path proof of the continuous v0.5 harness;
[#88](https://github.com/amichai-bd/nand2mario/issues/88) retains full execution
acceptance. This is an explicit issue-boundary change, not another checkpoint
exception. Historical Tcl diagnosis remains in
[#168](https://github.com/amichai-bd/nand2mario/issues/168) and does not gate unrelated delivery.

## Policy and protection

The `PR policy` check requires a valid numbered branch, `main` base, and closing
references to open assigned issues including the primary branch issue.
The explicitly authorized checkpoints PR162, PR163 and PR167 use
`Checkpoint for #156`, `Checkpoint for #88` and `Checkpoint for #164`, respectively.
PR169 and PR179 both use `Checkpoint for #168`.
Each requires a matching `Refs` line. They keep
those assigned acceptance issues open and contain no closing references. The
policy records only these five exceptions; other PRs still close their issues.
`Wiki check` validates the documentation build.

Main requires passing up-to-date checks, linear history, and resolved review
conversations. Force pushes and branch deletion are blocked on main. Human
approval is not required. Independent review and code/spec alignment are agent
responsibilities; they are not enforced by scripts or approval counts.

A merge closes the referenced issues and automatically deploys Pages. See
[GitHub issue linking](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).
