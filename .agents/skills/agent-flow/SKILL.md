---
name: agent-flow
description: Run a nand2mario issue through its worktree, peer review, green CI, merge, and cleanup. Use when starting, continuing, reviewing, or finishing repository work.
---

# Agent flow

Apply the obligations in [AGENTS](../../../AGENTS.md#work) through this flow:

1. Root selects the assigned issue and delegates its author using
   [worktree setup](../../../worktrees/README.md#create) and
   [capacity guidance](references/recovery.md).
2. Author reads the issue and linked spec, then aligns the change and validation
   with its success criteria. Iterate as needed; use the relevant focused skills.
3. Use [pr-author](../pr-author/SKILL.md) to open and maintain the draft PR.
   Resolve CI failures and obtain [independent review](references/review.md).
4. With a current ready verdict and required checks passing, post the report,
   undraft, and follow the [merge method](../../../worktrees/README.md#merge).
   Report the outcome to root.
5. Root performs [verification and cleanup](../../../worktrees/README.md#clean-up-after-merge).

For interrupted work, follow [recovery](references/recovery.md). Review handoffs
use [the report template](templates/review.md); see
[scenarios](examples/scenarios.md) when needed.

Use the [agent work rules](../../../AGENTS.md#work) for proceed-or-ask decisions.
Missing credentials block only work that needs them.
