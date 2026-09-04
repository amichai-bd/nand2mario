---
name: pr-author
description: Open, update, and finish a focused nand2mario pull request. Use for PR authoring and evidence; do not use to define issue scope or review another agent's code.
---

# PR author

Follow `wiki/agents/pull-requests.md` and `agent-flow`.

1. Confirm the branch, issue, worktree, and latest validation.
2. Fill [the PR body](templates/pull-request.md). Include each `Closes #N` line.
3. State specification impact, exact results, risk, and current review SHA.
4. Open early, then update the body when evidence changes.
5. Poll checks and review. Fix owned failures until merge or a stop condition.

Use [the scenarios](examples/scenarios.md) when deciding whether issues belong in
one PR. Stop when scope changed, evidence is missing, or a protected action needs
approval.
