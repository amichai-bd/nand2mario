---
name: issue-author
description: Draft, validate, create, or refine a focused nand2mario GitHub issue. Use for issue authoring; do not use for PRs or implementation.
---

# Issue author

Write one observable result using `wiki/agents/issues.md`.

1. Read the governing wiki page or name its planned path.
2. Choose the matching [bug](templates/bug.md),
   [enhancement](templates/enhancement.md), or
   [specification](templates/specification.md) template.
3. State current facts, scope, goal, and three to five observable checks.
4. Put discussion in comments. Do not prescribe needless implementation.
5. Save metadata and body at `workdir/.tmp/issues/<issue-title-slug>.md`, then run
   `python .agents/skills/issue-author/scripts/create_issue.py <draft>`.

The script validates section order and passes UTF-8 body text to `gh` through
stdin, without shell interpolation. Use `--check` before creation. Keep drafts
locally after success or failure; never commit them. See
[safe draft handling](examples/scenarios.md).

Read [the scenarios](examples/scenarios.md) when issue scope is unclear. Stop
when the goal needs an unmade product decision or an unknown specification.
