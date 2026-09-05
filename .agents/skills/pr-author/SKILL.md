---
name: pr-author
description: Open, update, and finish a focused nand2mario pull request. Use for PR authoring and evidence; do not use to define issue scope or review another agent's code.
---

# PR author

Follow `agent-flow` and `wiki/agents/pull-requests.md`.

1. Confirm the issue, branch, worktree, and validation.
2. Fill [the PR body](templates/pull-request.md) at
   `workdir/.tmp/pr/<pr-title-slug>.md`. Keep it locally after use.
3. Open early with `gh pr create --draft --base main --title '<title>' --body-file <path>`.
4. Update evidence with `gh pr edit <number> --body-file <path>`.
5. Babysit CI and independent review. Post the returned report from a file,
   undraft with `gh pr ready <number>`, then use the worktree guide's
   [merge method](../../../worktrees/README.md#merge).

Use [the scenarios](examples/scenarios.md) for body handling and issue scope.
Never interpolate Markdown into shell commands. Stop when scope changes,
evidence is missing, or an unauthorized protected action is required.
