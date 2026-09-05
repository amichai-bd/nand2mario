# Scenarios

Good: Root delegates issue 42 to an author in `worktrees/42-fix-timer/`.
The author opens a draft PR, fixes a CI failure, and gets an independent review.
A fix changes the SHA, so the reviewer checks again. The author posts the ready
report, undrafts, and squash merges. Root verifies closure and cleans up.

Good: A spec describes planned behavior before implementation. The PR names the
open implementation issue and closure criteria. The reviewer checks that this
sequencing is allowed by the current issue.

Good: A preview owner records `127.0.0.1:8000`, its command, process, and served
directory. After Ctrl+C, the port still has a listener. Root confirms the exact
PID belongs to that preview, stops it, and verifies the port and process tree are
clear before removing the worktree.

Good: An author's merge command reports that root already owns `main`. The
author verifies the PR is remotely merged, reports the merge commit and local
error, and leaves branch and worktree cleanup to root.

Bad: Accept a stale review, edit root main, silently leave code/spec drift, or
stop babysitting after opening the PR.

Bad: Treat Ctrl+C as proof, kill every Python or browser process, or force-delete
an uninspected leftover directory after Git unregisters the worktree.

Bad: Use `--delete-branch` from an author worktree or retry a merge because its
post-merge local cleanup returned an error.

Not a trigger: A design question with no issue work to start or finish.
