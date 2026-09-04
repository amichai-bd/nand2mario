# Scenarios

Good: Root delegates issue 42 to an author in `worktrees/42-fix-timer/`.
The author opens a draft PR, fixes a CI failure, and gets an independent review.
A fix changes the SHA, so the reviewer checks again. The author posts the ready
report, undrafts, and squash merges. Root verifies closure and cleans up.

Good: A spec describes planned behavior before implementation. The PR names the
open implementation issue and closure criteria. The reviewer checks that this
sequencing is allowed by the current issue.

Bad: Accept a stale review, edit root main, silently leave code/spec drift, or
stop babysitting after opening the PR.

Not a trigger: A design question with no issue work to start or finish.
