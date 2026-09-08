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
required validation, independent current-head review and conversations are satisfied.

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

Main normally requires passing up-to-date hosted checks, linear history, and resolved review
conversations. The authorized external-blockage fallback below supplies equivalent local validation. Force pushes and branch deletion are blocked on main. Human
approval is not required. Independent review and code/spec alignment are agent
responsibilities; they are not enforced by scripts or approval counts.

A merge closes its closing references and triggers Pages deployment. A trigger is not
proof that publication succeeded. See
[GitHub issue linking](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).


## External CI fallback

The user gives standing authorization to use local equivalents when a hosted
service or account condition prevents required checks from executing. Record the
specific external cause and actual run status/link. A job that ran and found a
code, test, policy or review failure still blocks delivery; an unexplained
failure is not evidence of an external outage.

Identify the currently required checks from protection and run their workflow
commands locally at the reviewed head, including live issue/PR metadata checks.
Meet the PR's scoped acceptance too. Reuse prior results only with explicit
relevant-input and behavior equivalence; record the producing SHA, commands,
results and limitations. Advisory jobs are selected by affected scope, not
automatically rerun merely because hosted CI is unavailable. If an equivalent
cannot be established, pause that delivery and name the missing evidence.

Independent current-SHA readiness and resolved conversations remain mandatory.
Record the local equivalents and actual hosted state in the PR, then follow the
[exact-head merge procedure](../../worktrees/README.md#merge). Do not wait for
hosted green or ask again for approval when this fallback applies. Do not write
synthetic check statuses, alter workflows to report success, or permanently
weaken protection.

After merge, root verifies remote merge state and the intended issue disposition.
For externally blocked main checks or deployment, record their actual status and
local equivalent validation (or qualified reuse). A local wiki/browser build
supports documentation validation, not Pages publication. Report deployment as
unverified or blocked until observed successful. Routine
[cleanup](../../worktrees/README.md#clean-up-after-merge) may proceed once the PR
summary is complete and no active user or dependency needs the worktree; an
external hosted outage alone does not require keeping it.
