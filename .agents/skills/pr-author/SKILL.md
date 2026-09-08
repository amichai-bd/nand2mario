---
name: pr-author
description: Open, update, and finish a focused nand2mario pull request. Use for PR authoring and evidence; do not use to define issue scope or review another agent's code.
---

# PR author

Follow `agent-flow` and `wiki/agents/pull-requests.md`.

1. Confirm the issue, branch, worktree, and validation. Link the selected
   [verification tier](../../../wiki/src/dv/integration/SPEC.md#verification-tiers)
   and map scoped criteria to evidence. Name unfinished milestone issues using
   the [scope policy](../../../wiki/agents/pull-requests.md#scoped-implementation-and-milestones).
   Keep the finite merge checklist current; optional improvements are follow-ups.
2. Fill [the PR body](templates/pull-request.md) at
   `workdir/.tmp/pr/<pr-title-slug>.md`. Keep it while work or review needs it; remove it through
   [post-merge cleanup](../../../worktrees/README.md#clean-up-after-merge).
3. Open early with `gh pr create --draft --base main --title '<title>' --body-file <path>`.
4. Update evidence with `gh pr edit <number> --body-file <path>`.
5. Babysit CI and independent review. When hosted checks are externally blocked,
   use the [standing fallback](../../../wiki/agents/pull-requests.md#external-ci-fallback)
   without repeating approval requests. Post the returned report from a file,
   undraft with `gh pr ready <number>`, then use the worktree guide's
   [merge method](../../../worktrees/README.md#merge).

Use [the scenarios](examples/scenarios.md) for body handling and issue scope.
Never interpolate Markdown into shell commands. Missing required evidence blocks
merge, not other authorized work. Apply explicitly authorized scope changes to
the issue and PR before judging acceptance. Pause only actions outside existing
authorization. Preserve the tested/reviewed commit, exact commands, tool versions,
results, measured runtime and material limitations in the PR before cleanup.
