# Scenarios

Good: Root delegates issue 42 to an author in `worktrees/42-fix-timer/`.
The author opens a draft PR, fixes a CI failure, and gets an independent review.
A fix changes the SHA, so the reviewer checks again and posts the ready report.
The author undrafts and squash merges. Root verifies closure and cleans up.

Good: A spec describes planned behavior before implementation. The PR names the
open implementation issue and closure criteria. The reviewer checks that the
current issue allows this sequence.

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

## Decisions

Apply the [agent work rules](../../../../AGENTS.md#work):

- An issue authorizes a wiki navigation change. Follow the existing layout
  convention without reconfirming the navigation change.
- Two specifications require different navigation behavior and neither takes
  precedence. Ask which behavior is intended; continue an independent authorized
  wording fix while the navigation change waits.
- A wording issue reveals a useful navigation redesign. Stay within the issue
  and ask before adding the redesign.
