# Preview cleanup

Record each local preview in the handoff or PR: loopback address, port, exact
command, owner session or process, and served directory. A terminal interrupt or
session exit is a stop request, not proof that child processes ended.

## Verify shutdown

1. Stop the preview through its owner session.
2. Inspect the recorded port for a listener. If one remains, inspect its exact
   PID, executable, command line, parent PID, and served directory.
3. Stop only a PID that matches the recorded preview. Never kill all Python,
   browser, or same-name processes.
4. Inspect the port and owned process tree again. Continue cleanup only when
   both are gone. If identity is uncertain, stop and report it.

On Windows, `Get-NetTCPConnection` identifies the listening PID and
`Get-CimInstance Win32_Process` shows its identity. `Stop-Process -Id <pid>` is
allowed only after that PID matches the recorded preview.

## Recover partial worktree removal

`git worktree remove` may unregister a worktree before file removal fails.

1. Check `git worktree list --porcelain` before retrying Git cleanup.
2. Resolve the leftover path. Confirm it is the exact target under this
   repository's `worktrees/` directory.
3. Inspect all leftover content, including hidden files. Preserve and report any
   content; do not force-delete it.
4. Remove only a verified empty leftover directory with an exact, non-recursive
   path. Then run `git worktree prune` and verify the result.

Do not claim cleanup from an interrupt, a missing Git registration, or a failed
remove command. Verify the listener, process, registration, and path state.
