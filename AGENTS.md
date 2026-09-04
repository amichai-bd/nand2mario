# Agent rules

Build a verified, original-DMG-compatible Game Boy for the DE10-Lite, with VGA
display and UART controls. Read [preflight gaps](wiki/preflight-gaps.md) before
implementation. Only approved bootstrap work may start before applicable P0 gaps
close.

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
`<repo-root>/worktrees/<number>-<slug>/`. Record ownership in the issue before
editing. All edits, builds, validation, and commits belong in that worktree.
Keep generated output under `workdir/`.

Prefer one issue and one PR. Every PR starts as draft and closes its branch's
issue with `Closes #<number>`. Combine issues only for one focused result.
The author babysits through independent review, green checks, and squash merge.
No human review is required. Root verifies merge, closure, and cleanup.

Read the issue and linked specification. Keep scope within its success criteria.
Comment useful findings, decisions, blockers, and evidence. Clarify issue facts
and links as needed; summarize material edits in a comment. Do not broaden the
goal or weaken criteria without approval.

Use [grill-me](.agents/skills/grill-me/SKILL.md) only when explicitly invoked.
Otherwise align directly. Use focused skills and keep detailed procedures there.

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
