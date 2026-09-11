# Externally blocked hosted checks

Local validation is the normal path: the
[PR policy](../../../../wiki/agents/pull-requests.md#hosted-and-local-checks)
lists the commands an author runs before merge, and only `PR policy` on pull
requests and the `Pages` build on `main` remain hosted. This procedure covers
those two jobs when a hosted service or account condition prevents their
execution. Apply the [standing authorization](../../../../AGENTS.md#verification-and-safety)
only when evidence shows that condition. Record the cause and actual run
status/link. A job that found a code, test, policy or review failure still
blocks delivery; unexplained failure is not an external outage.

## Validate and review

Read the currently required checks from protection and run their workflow
commands locally at the reviewed head. For `PR policy`, that is the workflow's
embedded script with live PR/issue metadata; `tools/ci/tests/test_pr_policy.py`
exercises the same script. Meet scoped acceptance and the normal local checks
too. Reuse results only with explicit relevant-input/behavior equivalence,
producing SHA, commands, outcomes and limitations. If a required equivalent
cannot be established, name the missing evidence and pause delivery.
Independent current-SHA readiness and resolved conversations remain mandatory.
Record local results and actual hosted state in the PR.

## Merge and restore

Re-read the reviewed head and assessed base; abort if either changed. Try the
[normal exact-head squash merge](../../../../worktrees/README.md#merge), then
`--admin` if only external hosted checks block it. Never fabricate check statuses
or alter workflows to report success.

If administrator enforcement still blocks the authorized merge, serialize with
root and save the exact current protection settings in the owning worktree.
Use `try`/`finally`: temporarily disable only administrator enforcement, recheck
head/base and issue the exact-head squash merge, then restore its saved value
in `finally` on success, failure or uncertain response. Keep required contexts,
app identities, strictness and all other protection unchanged. Verify restoration
against the saved settings; do not overwrite concurrent configuration changes.
If restoration fails, stop delivery/cleanup and report the unresolved change.
Missing admin rights does not authorize a different bypass.

After any uncertain merge response, inspect remote state before retrying. If it
already merged, report that result. If it remains open and unchanged, an exact-SHA
REST merge is an alternative to a failed CLI/GraphQL request; do not mistake a
server error for evidence that protection must change. No permanent protection
change is authorized.

## Verify and clean up

Root verifies remote merge and intended issue disposition. For externally blocked
main checks or deployment, record actual status and local equivalents or qualified
reuse. Local wiki/browser success does not prove Pages publication; report it as
blocked or unverified until observed successful. Follow
[cleanup](../../../../worktrees/README.md#clean-up-after-merge) once the PR summary
is complete and no active user/dependency needs the worktree. External hosted
blockage alone does not require retaining it. Preserve unfinished work and user
files; do not claim hosted green or successful publication.
