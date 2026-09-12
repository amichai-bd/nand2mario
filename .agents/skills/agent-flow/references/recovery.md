# Delegation and recovery

An author may request a review subagent when nested delegation is supported.
Otherwise root spawns the reviewer, which posts its report on the PR. Authors
never pick unrelated backlog work.

Check the [work caps](../../../../AGENTS.md#work) and runtime capacity before
spawning. The reviewer takes a crewmate slot, so when the slots are full, pause
or finish the author before requesting review rather than running both at once.
Native review does not remove the need for an independent reviewer.

## Retained context

Keep the orchestration handoff in root's ignored `workdir/` and give its location
to delegated agents. It must identify unfinished work, its owner and worktree,
verified results, pending work, and the next action or blocker. Link existing
issue, PR, and artifact evidence. Keep active artifacts in their owning worktrees;
the root handoff is a summary, not an artifact archive.
Use any concise format; routine progress logs are unnecessary. Update ownership
and next actions when they change so recovery does not depend on chat history.

## Takeover

Read the handoff, issue, and PR, then verify the current head SHA, checks, and
worktree status against that context. Root confirms the previous owner has
stopped before recording the transfer in the handoff and PR. Resume existing
work; do not create a second author branch or discard dirty changes. Reuse only
evidence for the current change and repeat review when its SHA is stale.

Record a concrete blocker and next action in the handoff or PR, following
[issue update rules](../../../../wiki/agents/issues.md#agent-use) when a contract
decision is needed. Do not loop on unchanged deterministic failures.

If a merge errors after sending its request, follow the
worktree guide's [remote verification](../../../../worktrees/README.md#merge).

Follow [cleanup](../../../../worktrees/README.md#clean-up-after-merge) to end
sessions and remove worktrees. If no close operation exists, let agents finish
or interrupt active work; report that limitation rather than claiming deletion.
