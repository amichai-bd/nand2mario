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
three to five checks. Put implementation discussion in comments or the PR.

Blank issues are disabled.

## Agent use

The issue is the agent's working guide and starting prompt.

- Assign the issue before work starts. The assignee is accountable for it.
- Claim the issue in a comment. Name the agent, branch, and relative worktree.
- When an internal agent has no GitHub identity, assign the accountable user and
  name the agent or session in the claim comment.
- Read the full issue and specification before changing files.
- Use comments for useful discoveries, decisions, blockers, and evidence.
- Edit the issue when new facts make it clearer or add required links.
- Summarize a material body edit in a comment.
- Never broaden the goal or weaken success criteria without approval.
- At completion, check the criteria and post the validation evidence.

Do not use comments as a command transcript. Build logs belong under the build
tag; the issue should contain only the result and useful links.

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
