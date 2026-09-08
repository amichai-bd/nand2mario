# Agent rules

Build a verified, original-DMG-compatible Game Boy for the DE10-Lite, with VGA
display and UART controls. Follow the [current phase](wiki/agents/bootstrap-plan.md#current-phase)
before selecting work. Read [preflight gaps](wiki/preflight-gaps.md) before
implementation; open product prerequisites are not permission to start them.

## Sources of truth

- README: human overview and entry points.
- AGENTS: mandatory agent rules and context.
- Skills: recurring methods, templates, and examples.
- Wiki: behavior, specifications, and decisions.
- Issues: one goal and its success criteria.
- PRs: completed changes and review evidence.
- `src/`: product implementation and verification.
- Build artifacts: logs, traces, and results.

Keep each fact in one linked source. Follow the
[ownership map](wiki/ownership.md) for tool PRD/SPEC and RTL MAS placement.
The site renders documentation; do not maintain document or implementation
mirrors. Review wiki requirements/design against `src/`, `tools/`, tests, and
retained evidence using the
[review guide](.agents/skills/agent-flow/references/review.md).
Track allowed drift in an open issue; never accept it silently.

## Style

Use plain words, short sentences, and direct names. Lead with the result or
decision. Keep modules small and behavior explicit. Comments explain intent,
timing, or risk. Avoid speculative features and unrelated cleanup. Match nearby
code and documents unless the issue changes the convention.

## Work

Follow [agent-flow](.agents/skills/agent-flow/SKILL.md). One root orchestrator
selects assigned issues and delegates authors to separate worktrees. Keep the
root checkout clean on `main`; never share a worktree.

Each root orchestration tree may have at most three open PRs, including its authors'
drafts, and three active subagents, including nested agents. These are ceilings,
not targets; lower runtime limits still apply. Default to two authors and a reviewer
independent of each change's author; root coordinates delivery. Prioritize existing
ready PRs, finishing, reviewing, and merging over starting more work.
If already over either cap, preserve existing work and reduce concurrency before
adding more. Open a PR only when that tree has fewer than three open. Separately
user-authorized work outside that tree does not consume its slots. Do not hide work
in branches, split orchestration trees, or close unfinished PRs to evade the cap.

Use branch `<number>-<slug>` and author worktree
`<repo-root>/worktrees/<number>-<slug>/`. Record ownership in the orchestration
handoff and PR. Edit, build, validate, and commit only there. Keep generated
output under the author or reviewer worktree's `workdir/`.

Prefer one issue per PR. Every PR starts as draft and closes its branch's
issue with `Closes #<number>`. Combine issues only when one focused result meets
all their success criteria.
The user-authorized checkpoints PR162, PR163, PR167, PR169 and PR179 instead reference
#156, #88, #164, #168 and #168, respectively, without closing them. Their unfinished acceptance stays in those issues; this
bounded exception is recorded in PR policy and does not authorize other checkpoints.
The author owns delivery through independent review of the current PR SHA,
satisfying required checks, resolved review conversations, and squash merge.
Human review is not required. Root verifies merge, issue closure, main checks,
deployment, and [cleanup](worktrees/README.md#clean-up-after-merge).
After verified delivery, retain a concise validation summary in the PR and remove
completed worktrees, artifacts, and merged branches. Do not archive build output
or copy it into the primary checkout. Preserve unfinished work and dependencies.

Read the issue and linked specification; stay within its success criteria.
Proceed when requirements and conventions support a choice within existing
authorization. Ask before resolving ambiguity that would change observable
behavior, scope, acceptance criteria, or an explicit safety boundary beyond that
authorization. Do not broaden the goal or weaken criteria without approval.
Do not reconfirm authorized changes. While awaiting a decision, continue
independent authorized work; pause only dependent work. See
[decision examples](.agents/skills/agent-flow/examples/scenarios.md#decisions).
Follow [issue guidance](wiki/agents/issues.md#agent-use) for assignment and updates;
keep review evidence in PRs and logs in artifacts.

Use [grill-me](.agents/skills/grill-me/SKILL.md) only when explicitly invoked.
Otherwise align directly. Use focused skills and keep detailed procedures there.
Choose routine steps and tools. Retain enough context for safe takeover; see
[recovery](.agents/skills/agent-flow/references/recovery.md).

## Verification and safety

When hosted CI is blocked by an external service or account condition, run the
local equivalents of required checks and meet scoped acceptance, using valid
unchanged evidence where applicable. Continue reviewed delivery without asking
for per-PR approval again. Real code, test, policy and review failures remain
blockers. Report actual hosted status; never fabricate green checks or Pages
publication. Follow the [external CI fallback](.agents/skills/agent-flow/references/external-ci.md)
for exact-head merge, temporary protection restoration and post-merge cleanup.

Use the [verification tiers](wiki/src/dv/integration/SPEC.md#verification-tiers)
for proportionate acceptance. Ordinary PRs must meet their own scoped criteria,
required checks under the external fallback and independent current-head review; full milestone gates apply to
milestone completion. Keep unfinished milestone requirements in named open issues.
Make authorized issue-boundary changes explicit before using the revised criteria;
the listed checkpoint exceptions are not a blanket waiver. Correctness defects
and regressions introduced by a PR remain its blockers.

Default to existing continuous Python and Intel-model preload for composed
execution tests. Reuse valid evidence for unchanged relevant inputs. Before an
expensive acceptance run, exercise its complete harness at a short duration,
including final pause, completion and watchdog handling. Do not hide warnings,
bypass checks or claim incomplete acceptance complete.

Run the smallest useful test and required lower-level checks. Every test must
finish within the [600-second wall budget](wiki/tools/n2m/SPEC.md#test-wall-budget);
never extend it to finish a milestone. Record exact
commands and results. A simulation compiles, elaborates, runs, and checks an
expected result. Treat unexplained warnings as failures. Preserve useful logs,
seeds, traces, waves, and reports under the build tag while work or review needs
them; follow the cleanup policy after delivery.

Merges to `main` automatically publish Pages with standing authorization.
The repository is private; the site is public. Visibility or deployment policy
changes require approval.

Verify device, wiring, and voltage before hardware use. Programming and physical
tests need explicit authorization and serialized access. Never commit commercial
ROMs, boot ROMs, saves, or credentials. Keep private machine and ROM facts out of
published sources. Pin external code, tests, and tools; record licenses and
provenance. Use `frog-bui` for process ideas until reuse terms are clear.
