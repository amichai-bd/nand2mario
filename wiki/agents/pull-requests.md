# Branches and pull requests

Follow the [agent work rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md#work)
for branch naming, worktree ownership, draft state, and issue scope.
Use a lowercase branch slug, such as `42-fix-timer`.
Each closing reference has its own line:

```text
Closes #<issue-number>
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
required validation, independent current-head review and conversations are satisfied.

## Policy and protection

The `PR policy` check requires a valid numbered branch, `main` base, and closing
references to open assigned issues including the primary branch issue. Only the
fixed [checkpoint exceptions](#checkpoint-exceptions) below may use matching
checkpoint and `Refs` lines without a closing reference. Other PRs close their
issues. `Wiki check` validates the documentation build.

Main normally requires passing up-to-date hosted checks, linear history, and resolved review
conversations. The authorized external-blockage fallback below supplies equivalent local validation. Force pushes and branch deletion are blocked on main. Human
approval is not required. Independent review and code/spec alignment are agent
responsibilities; they are not enforced by scripts or approval counts.

A merge closes its closing references and triggers Pages deployment. A trigger is not
proof that publication succeeded. See
[GitHub issue linking](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).


## Checkpoint exceptions

This set is closed. It is a record of PRs the user authorized to merge without a
closing reference, each carrying matching `Checkpoint for #<number>` and
`Refs #<number>` lines for the issue it referenced when it merged. It authorizes
no further checkpoint, and no PR may be added to it.

The set is PR162, PR163, PR167, PR169 and PR179, all merged.

Each kept its acceptance in the issue it referenced when it merged; whether that
issue is still open today is a question for that issue, not for this record. The
pairing itself is not repeated here: the `PR policy` check holds it in its own
fixed map, keyed by PR number, and each PR body carries its own `Checkpoint for`
and `Refs` lines. That map is also why the set cannot grow by editing this page.

Every other PR closes its branch's issue. A PR that merely references an issue
without closing it, outside this set, does not satisfy the policy.

## External CI fallback

The [mandatory rule](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md#verification-and-safety)
authorizes equivalent local required checks when hosted execution is externally
blocked. Real failures and missing scoped evidence remain blockers. Follow the
[skill procedure](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/agent-flow/references/external-ci.md)
for evidence, exact-head merge, restoration and honest deployment status. This
standing authorization needs no repeated per-PR approval.
