# Issues and labels

## Issue forms

Use one of three forms:

- **Bug** for incorrect or unexpected behavior.
- **Enhancement** for one new or improved behavior.
- **Specification** for one design contract or decision.

Every form uses the same frame:

1. `TL;DR`
2. `Specification reference`
3. Type-specific context and evidence
4. `Goal`
5. `Success criteria`

`TL;DR` summarizes the issue in one or two sentences. The specification field
links the governing wiki page or gap. If the page does not exist, it states the
planned path.

The goal is one observable end state. Success criteria are three to five checks
that prove the goal. These two fields always finish the issue.

Each issue should describe one observable result. Keep success criteria to
three to five checks. Put implementation discussion in the PR.

Blank issues are disabled.

## Agent use

The issue is the agent's working guide and starting prompt.

When the user explicitly invokes
[`grill-me`](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/grill-me/SKILL.md),
its confirmed decision
packet maps into the issue goal, scope, success criteria, and linked wiki work.
Otherwise align directly. Do not copy the full interview into the issue.

- Assign the issue before work starts. The assignee is accountable for it.
- One root orchestrator picks issues and delegates authors. Authors do not pick
  unrelated backlog work.
- Record the agent, branch, and relative worktree in the orchestration handoff
  and PR, not an issue claim comment.
- When an internal agent has no GitHub identity, assign the accountable user and
  name the agent or session in that handoff and PR.
- Read the full issue and specification before changing files.
- Edit or comment only when a new finding requires clarification, a decision,
  or documented drift. State the finding and its effect on the issue contract.
- Edit the body for settled facts; comment for an unresolved question or drift.
  Do not duplicate a body edit in a comment.
- Never broaden the goal or weaken success criteria without approval.

Do not post routine claims, progress, CI, review, merge, or cleanup updates.
Do not edit the body just to report completion or tick criteria. Check criteria
and record results in the PR; keep logs in build artifacts. Assignment, linked
PRs, and automatic closure show the lifecycle without issue updates.

Use the [issue skill](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/issue-author/SKILL.md)
for retained Markdown drafts under `workdir/.tmp/issues/` and safe CLI bodies.

Every implementation PR closes its issue. The normal case is one issue and one
PR. One focused PR may close several related issues. See
[Branches and pull requests](pull-requests.md).

## Labels

`.github/labels.yml` is the canonical label catalog.

- Apply exactly one `type:*` label.
- Apply one primary `area:*` label. Add a second only for a real boundary.
- Apply one `priority:*` label after the issue is scheduled.
- Use `needs:decision` or `needs:hardware` only when required.
- Use `status:blocked` only when the blocking dependency is named.

Do not add `in-progress` or `in-review` labels. Assignees, linked branches,
linked PRs, and GitHub state already show that lifecycle.

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
