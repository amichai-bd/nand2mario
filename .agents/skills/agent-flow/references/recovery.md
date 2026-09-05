# Delegation and recovery

An author may request a review subagent when nested delegation is supported.
Otherwise root spawns the reviewer and returns its report. Authors never pick
unrelated backlog work.

Check available agent capacity before spawning; reserve space for a reviewer.
Limits depend on the runtime, so do not hard-code a slot count. If capacity is
full, finish or pause independent work before requesting review. Native review
does not remove the need for an independent reviewer.

## Retained context

Keep the orchestration handoff in root's ignored `workdir/` and give its location
to delegated agents. It must let a successor find unfinished work, identify its
owner and worktree, distinguish verified results from pending work, and identify
the next action or blocker. Link existing issue, PR, and artifact evidence.
Use any concise format; no routine progress log is needed. Refresh context when
ownership or the next action changes so recovery does not depend on chat history.

## Takeover

Read the handoff, issue, and PR, then verify the current head SHA, checks, and
worktree status against that context. Root confirms the previous owner has
stopped before recording the transfer in the handoff and PR. Resume existing
work; do not create a second author branch or discard dirty changes. Reuse only
evidence for the current change and repeat review when its SHA is stale.

Record a concrete blocker and next action in the handoff or PR, following
[issue update rules](../../../../wiki/agents/issues.md#agent-use) when a contract
decision is needed. Do not loop on unchanged deterministic failures.

If a merge command reports an error after sending its request, follow the
worktree guide's [remote verification](../../../../worktrees/README.md#merge).

Follow [cleanup](../../../../worktrees/README.md#clean-up-after-merge) to end
sessions and remove worktrees. If no close operation exists, let agents finish
or interrupt active work; report that limitation rather than claiming deletion.
