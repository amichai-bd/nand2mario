# Infrastructure acceptance

Exercise the existing infrastructure flow with a fresh author. Record evidence,
procedural coaching, and unfinished steps in the PR and ignored `workdir/`
artifacts. This checklist is not a new CI gate.

- [ ] Confirm the assigned issue fits the [current phase](bootstrap-plan.md#current-phase)
  and read the [preflight gaps](../preflight-gaps.md). Product architecture,
  RTL, DV, software, FPGA, project build/doctor, simulation, and hardware work
  remain deferred; completing this checklist does not change the phase.
- [ ] Root records ownership and delegates the author in an isolated checkout
  using the [worktree guide](../../worktrees/README.md#create).
- [ ] Follow [agent flow](../../.agents/skills/agent-flow/SKILL.md) and the issue's
  linked specifications. Fix only demonstrated guide gaps within the issue.
- [ ] Run the existing [wiki and browser checks](../tools/wiki/SPEC.md#browser-checks)
  and the issue-helper test command in the [Wiki workflow](../../.github/workflows/wiki.yml).
  Record exact commands, results, and artifact paths; identify any local browser
  override. CI must pass its pinned browser run.
- [ ] Use [pr-author](../../.agents/skills/pr-author/SKILL.md) to open a draft PR
  with ownership, a closing reference, and retained evidence. Confirm the
  required [PR checks](pull-requests.md#policy-and-protection) pass.
- [ ] Obtain an [independent review](../../.agents/skills/agent-flow/references/review.md)
  of the complete diff in a separate detached checkout. Retain the report and
  alignment assessment; confirm its ready verdict names the current head SHA.
- [ ] Author resolves findings, babysits checks, posts the review, undrafts, and
  uses the [squash merge method](../../worktrees/README.md#merge).
- [ ] Root verifies the merge, issue closure, and successful main
  [Pages deployment](../../.github/workflows/pages.yml), then completes
  [worktree and branch cleanup](../../worktrees/README.md#clean-up-after-merge).
  Record a concise cleanup and deployment summary in the PR. Follow
  [preview cleanup](../../.agents/skills/agent-flow/references/preview-cleanup.md)
  when a local preview was used.
