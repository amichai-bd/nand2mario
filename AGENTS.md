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

Keep each fact in one place and link to it. The site renders existing sources;
do not maintain mirrored documents. Review source/spec/test alignment using the
[review guide](.agents/skills/agent-flow/references/review.md).
Document allowed drift with an open issue; do not silently accept it.

## Style

Use plain words, short sentences, and direct names. Lead with the result or
decision. Keep modules small and behavior explicit. Comments explain intent,
timing, or risk. Avoid speculative features and unrelated cleanup. Match nearby
code and documents unless the issue changes the convention.

## Work

Follow [agent-flow](.agents/skills/agent-flow/SKILL.md). One root orchestrator
selects assigned issues and delegates authors to separate worktrees. Keep the
root checkout clean on `main`; never share a worktree.

Use branch `<number>-<slug>` and author worktree
`<repo-root>/worktrees/<number>-<slug>/`. Record ownership in the orchestration
handoff and PR. All edits, builds, validation, and commits belong in that worktree.
Keep generated output under `workdir/`.

Prefer one issue and one PR. Every PR starts as draft and closes its branch's
issue with `Closes #<number>`. Combine issues only when one focused result meets
all their success criteria.
The author owns delivery through independent review of the current PR SHA,
passing required checks, resolved review conversations, and squash merge.
No human review is required. Root verifies merge, issue closure, main checks,
deployment, and cleanup.

Read the issue and linked specification. Keep scope within its success criteria.
Proceed when requirements and conventions support a choice within existing
authorization. Ask before resolving ambiguity that would change observable
behavior, scope, acceptance criteria, or an explicit safety boundary beyond that
authorization. Do not broaden the goal or weaken criteria without approval.
Do not ask again for an authorized change. While awaiting a decision, continue
independent authorized work; pause only work that depends on the answer. See
[decision examples](.agents/skills/agent-flow/examples/scenarios.md#decisions).
Follow [issue guidance](wiki/agents/issues.md#agent-use) for assignment and updates;
keep review evidence in PRs and logs in artifacts.

Use [grill-me](.agents/skills/grill-me/SKILL.md) only when explicitly invoked.
Otherwise align directly. Use focused skills and keep detailed procedures there.
Choose routine steps and tools to meet these obligations. Retain enough context
for another agent to resume safely; see
[recovery](.agents/skills/agent-flow/references/recovery.md).

## Verification and safety

Run the smallest useful test and required lower-level checks. Record exact
commands and results. A simulation compiles, elaborates, runs, and checks an
expected result. Treat unexplained warnings as failures. Preserve useful logs,
seeds, traces, waves, and reports under the build tag.

Merges to `main` automatically publish Pages with standing authorization.
The repository is private and the site is public. Changes to visibility or
deployment policy require approval.

Verify device, wiring, and voltage before hardware use. Programming and physical
tests need explicit authorization and serialized access. Never commit commercial
ROMs, boot ROMs, saves, or credentials. Keep private machine and ROM facts out of
published sources. Pin external code, tests, and tools; record licenses and
provenance. Use `frog-bui` for process ideas until reuse terms are clear.
