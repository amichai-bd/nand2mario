# Issues and labels

## Issue forms

Use one of three forms:

- **Bug** for incorrect or unexpected behavior.
- **Enhancement** for one new or improved behavior.
- **Specification** for one design contract or decision.

Each issue should describe one observable result. Keep acceptance criteria to
three to five checks. Put implementation discussion in comments or the PR.

Blank issues are disabled.

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
