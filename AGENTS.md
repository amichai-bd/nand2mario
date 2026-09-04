# Agent rules

## Goal

Build a verified, original-DMG-compatible Game Boy for the DE10-Lite. It must
display through VGA and accept controls through UART.

## Current phase

Read `wiki/preflight-gaps.md` before implementation. Before functional RTL
starts, do only approved bootstrap work that closes its applicable P0 gaps.

The repository is private. Do not change visibility, publish Pages, or program
the FPGA without explicit approval.

## Sources of truth

- The issue defines the goal and acceptance criteria.
- The wiki defines behavior and decisions.
- A skill defines a recurring method.
- `src/` contains the product and its verification.
- Tests and build artifacts provide evidence.

Keep each fact in one place. Link to it elsewhere.

## Style

- Use plain words and short sentences.
- Lead with the result, evidence, or decision.
- Write small modules with direct names and explicit behavior.
- Comments explain intent, timing, or risk. They do not repeat code.
- Avoid clever abstractions, speculative features, and unrelated cleanup.
- Match nearby code and documents unless the issue changes the convention.

## Work

- Use `grill-me` only when the user explicitly invokes it. Otherwise align
  directly with the user.
- Keep the root checkout clean and on `main`. Use it only to orchestrate work.
- Start work only after the issue has an assignee.
- Prefer one issue, one observable result, one branch, and one PR.
- Name work branches `issue/<primary-number>-<slug>`.
- Use one worktree per issue at `worktrees/issue-<number>-<slug>`.
- Record the agent, branch, and worktree in an issue comment before editing.
- Do all edits, builds, validation, and commits inside that worktree.
- Never share a worktree between agents.
- Every PR must close at least one issue with `Closes #<number>`.
- The branch's primary issue number must be one of those closing references.
- Close several issues in one PR only when one focused change completes them.
- Treat the issue as the working guide and starting prompt.
- Read the issue and linked specification before editing.
- Keep changes inside the acceptance criteria.
- Comment useful discoveries, decisions, blockers, and validation evidence.
- Edit the issue when facts or links become clearer. Summarize material edits in
  a comment.
- Do not broaden the goal or weaken success criteria without approval.
- Update specification, implementation, and tests together when behavior
  changes.
- Record exact commands and results. Do not claim a planned command passed.
- Finish by checking the success criteria and posting the evidence.
- The authoring agent owns the PR until merge and cleanup are verified.
- Require an independent agent review of the latest material commit.
- Fix owned CI failures and review findings; keep polling until resolution.
- Same-account agents leave review comments. They cannot approve their own PR.
- No human approval is required after checks and agent review pass.
- Remove the worktree only after the PR is verified as merged.
- Keep generated output under `workdir/`.

## Verification

- Run the smallest test that proves the change, then required lower-level
  checks.
- A simulation must compile, elaborate, run, and check an expected result.
- Treat unexplained warnings as failures.
- Preserve useful logs, seeds, traces, waves, and reports under the build tag.

## Safety and external content

- Verify the USB-Blaster, device, voltage, and wiring before hardware use.
- Keep programming and physical tests explicit and serialized.
- Never commit commercial ROMs, Nintendo boot ROMs, saves, or credentials.
- Pin external code, test suites, and tools. Record licenses and provenance.
- Use `frog-bui` for process ideas only until reuse terms are clear.

## Skills

Use a focused repository skill when one exists. Keep procedures, examples, and
tool-specific detail in the skill, not here.
