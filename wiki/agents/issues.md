# Issues and labels

## Issue forms

Use one of three forms:

- **Bug** for incorrect or unexpected behavior.
- **Enhancement** for one new or improved behavior.
- **Specification** for one design contract or decision.

Every form uses:

1. `TL;DR`
2. `Specification reference`
3. Type-specific context and evidence
4. `Goal`
5. `Success criteria`

`TL;DR` summarizes the issue in one or two sentences. Link the governing wiki
page or gap in the specification field; name its planned path only if the page
does not exist.

End every issue with one observable goal and three to five success checks.

Put implementation discussion in the PR.

Blank issues are disabled.

## Agent use

The issue is the agent's working guide and starting prompt.

When the user explicitly invokes
[`grill-me`](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/grill-me/SKILL.md),
map its confirmed decision packet to the issue goal, scope, success criteria,
and linked wiki work.
Otherwise align directly. Do not copy the full interview into the issue.

- Assign the issue before work starts. The assignee is accountable for it.
- Follow the [work rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md#work)
  for delegation, ownership, and issue scope.
- When an internal agent has no GitHub identity, assign the accountable user and
  name the agent or session in that handoff and PR.
- Edit or comment only when a new finding requires clarification, a decision,
  or documented drift. State the finding and its effect on the issue contract.
- Edit the body for settled facts; comment for an unresolved question or drift.
  Do not duplicate a body edit in a comment.

Do not post routine claims, progress, CI, review, merge, cleanup, or completion
updates, or tick criteria in the issue body. Check criteria and record results
in the PR; keep logs in build artifacts. Assignment, linked PRs, and automatic
closure show the lifecycle.

Use the [issue skill](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/issue-author/SKILL.md)
for retained Markdown drafts under `workdir/.tmp/issues/` and safe CLI bodies.

See [Branches and pull requests](pull-requests.md) for closing references and CI.

## Helper tests

From the repository root, run:

```text
python -m unittest discover -s .agents/skills/issue-author/scripts -p test_create_issue.py -v
```

The required PR `Wiki check` and main Pages build run this suite before the
wiki build. A failed test stops publication. The tests mock GitHub calls;
they do not create issues.

## Labels

`.github/labels.yml` is the canonical label catalog.

- Apply exactly one `type:*` label.
- Apply one primary `area:*` label. Add a second only for a real boundary.
- Apply one `priority:*` label after the issue is scheduled.
- Use `needs:decision` or `needs:hardware` only when required.
- Use `status:blocked` only when the blocking dependency is named.

Do not add `in-progress` or `in-review` labels. Assignees, linked branches
and PRs, and GitHub state show the lifecycle.

## Titles

Write a short imperative result. Do not repeat the type or area label.

Good:

```text
Detect stale Questa compile libraries
Define the host control register map
Fix TIMA reload timing
```

Bad:

```text
[BUG][RTL] Timer issue
Improve things
Game Boy specification
```
