---
name: agent-flow
description: Run a nand2mario issue through its worktree, peer review, required validation, merge, and cleanup. Use when starting, continuing, reviewing, or finishing repository work.
---

# Agent flow

Follow [AGENTS](../../../AGENTS.md#work):

1. Root checks the work caps and selects the smallest independently useful change
   in an assigned issue. Clear review and merge queues before starting more work.
   After relevant main merges and before selecting work, refresh open PR heads,
   bases, conflicts, review/check status and actual blockers.
   Delegate its author using
   [worktree setup](../../../worktrees/README.md#create) and
   [capacity guidance](references/recovery.md).
   Root owns the user boundary throughout: delegated agents report inside the
   tree and raise questions to root, and root reports outcomes and open
   decisions to the user.
   Root selects and dispatches, arranges the independent reviewer, verifies
   merge, `main` checks, deployment and cleanup, and escalates decisions to the
   user. The author and reviewer perform every delivery step between.
2. Author reads the issue and linked spec, aligning changes and validation with
   its success criteria. Keep one acceptance checklist mapping each criterion to
   evidence or a concrete gap. Defer optional improvements to follow-up issues;
   do not expand the active change or weaken acceptance to make it smaller.
   For an authorized split, update issue boundaries and name the open milestone
   issue before applying the scoped criteria; follow the [PR policy](../../../wiki/agents/pull-requests.md#scoped-implementation-and-milestones).
   Select the [verification tier](../../../wiki/src/dv/integration/SPEC.md#verification-tiers)
   from changed behavior. Freeze unfinished implementation, missing evidence,
   measured per-test/aggregate budgets,
   review findings and external dependencies in one remaining-to-merge checklist.
   Mark checks waiting for the shared tool slot separately from unfinished work.
   Iterate using affected tests, then complete the scoped acceptance set. Before
   long runs, check the full harness's short completion path. Reuse existing
   validators; avoid repeated artifact audits and unchanged diagnostics. Measure
   execution, queue and review time where practical; do not optimize an unmeasured
   bottleneck or start optional work while a useful change waits for review.
   Run authorized routine tools under existing locks without per-batch root
   permission; retain explicit hardware and safety approval boundaries.
3. Use [pr-author](../pr-author/SKILL.md) to open and maintain the draft PR.
   Resolve CI failures and obtain [independent review](references/review.md).
   The reviewer posts its own report as a PR comment. When `main` moves, the
   author rebases, compares the reviewed diff against the rebased diff to
   prove the reviewed content survived, and keeps the PR body accurate.
   Assess the whole checklist in one pass and list remaining gaps together.
   Reuse evidence only while its inputs and covered behavior remain valid;
   satisfy required checks and current-SHA review before merging. For external
   hosted failures, apply the [standing fallback](references/external-ci.md).
4. With a ready verdict on the current head and required validation satisfied,
   the author undrafts, waits for the re-triggered required checks, and performs
   the exact-head squash merge using the
   [merge method](../../../worktrees/README.md#merge).
   Merge promptly without waiting for unrelated work. Report the outcome to root.
5. Root performs [verification and cleanup](../../../worktrees/README.md#clean-up-after-merge).

For interruptions, follow [recovery](references/recovery.md). Review handoffs
use [the report template](templates/review.md); see
[scenarios](examples/scenarios.md) when needed.

Follow the [agent work rules](../../../AGENTS.md#work) on proceeding or asking.
Missing credentials block only work that needs them.
