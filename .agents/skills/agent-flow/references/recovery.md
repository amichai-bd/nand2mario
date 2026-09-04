# Delegation and recovery

One root orchestrator selects and claims backlog issues. An author may request
a review subagent when nested delegation is supported. Otherwise root spawns
the reviewer and returns its report. Authors never pick unrelated backlog work.

Check available agent capacity before spawning; reserve space for a reviewer.
Limits depend on the runtime, so do not hard-code a slot count. If capacity is
full, finish or pause independent work before requesting review. Native review
does not remove the need for an independent reviewer.

If work is interrupted, read the issue, claim comment, PR, current head SHA,
checks, and worktree status. Root confirms the previous owner has stopped before
transferring ownership in a comment. Resume the existing work; do not create a
second author branch or discard dirty changes. Reuse only evidence for the
current change and repeat review when its SHA is stale.

The author babysits until merge or a concrete blocker. Record blockers and the
next action in the issue. Do not loop on unchanged deterministic failures.

After merge, root verifies cleanup and ends the author and reviewer sessions
using the runtime's supported tools. If no close operation exists, let agents
finish or interrupt active work; report that limitation rather than claiming
an agent was deleted. Never remove a worktree while its agent is using it.
