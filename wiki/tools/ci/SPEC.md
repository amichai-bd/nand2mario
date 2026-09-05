# Trusted product CI design

Status: inactive bootstrap under #115. The [requirements](PRD.md) define scope.
The checked-in configuration has `enabled: false`, and the hosted waiter job has
an unconditional false guard. Neither a command flag nor remote input can override
these gates. Activation requires a separately reviewed change under #32, including
real repository/workflow/account/environment identity verification and exact-source
licensed positive/negative samples. Existing Pages and required checks stay intact.

## Admission

The local operator supplies an exact 40-hex main SHA, numeric run ID and attempt,
and one fixed profile. Paths to installed tools are local arguments only. Remote
fields never supply commands, paths or executable names. The controller loads one
fixed repository configuration and rejects unknown fields and profiles.

Before consuming an attempt, query the configured repository ID/full name,
authenticated account ID, immutable workflow ID/path and content blob, current run
and attempt, original and triggering account IDs, dispatch event, main branch and
exact SHA. Require exactly one active waiter job whose fixed name includes that
profile. The configured environment must exist with a custom branch policy allowing
only branch main, and main must be protected. Initial SHA must equal current main;
final publication allows only that same SHA still reachable from protected main.
API errors, missing fields, unexpected identities or ambiguous collections fail.

The local controller checkout must be clean, with HEAD equal to the authorized
SHA. Reject assume-unchanged/skip-worktree index flags and compare every tracked file
with its authorized Git blob, allowing only CRLF-to-LF checkout normalization
for text. Git status alone is insufficient source identity. Child
execution uses a separate detached checkout created at that same immutable SHA;
no remote job source is executed before admission. Apply the same authorized-blob
checks to the execution checkout before each child and when validating its result;
recomputed hashes of hidden modified files cannot establish authorized-source proof. Reviewed main code, installed
tools, the controller account and the local operator are trusted. This is not a
sandbox for malicious code carrying those authorities.

## Serialization and recovery

Acquire a fixed machine-wide exclusive lock before any status mutation or tool
execution. Hold it through evidence finalization. A persistent machine journal records the repository/run/attempt/profile tuple
before pending publication. It is independent of checkout location: the OS machine
application-data directory on Windows, or `/var/lib` on POSIX, followed by
`nand2mario/workdir/trusted-ci/<repository-id>`. #32 must provision this directory
with access limited to the trusted controller account; missing access fails closed.
There is no command-line journal-path override. Any existing
journal entry or remote exact-context status rejects reuse, including an interrupted
attempt. Never clear history automatically or resume partial execution; dispatch a
new attempt. A crash leaves inspectable in-progress state. Hosted concurrency is
additional queueing, not a replacement for this lock.

Recheck admission and cancellation before each child and before final publication.
A rerun, cancelled job, changed workflow/account, lost protection or rewritten main
invalidates publication when observed. API checks and status creation are not an
atomic GitHub transaction; the hosted waiter rechecks admission and latest status
immediately before acceptance. A cancelled waiter cannot turn a late status into
a successful hosted job. Main advancing normally does not retarget the admitted SHA.
No background loop launches work; each local invocation is explicit.

## Profiles and records

Only fixed Questa baseline good/broken and Quartus clocking/invalid profiles exist.
Use fresh UUID-derived tags and the shared builder with rebuild requested. Record
every command, raw exit, source/tool hashes and complete artifact inventory. Invalid Quartus runs still require generated HDL, project/checked constraint
files, generation/compile/failure logs and every tool version record. The missing
endpoint must be the intended `reset_0` failure after successful generation. The invalid
compile classifier accepts only the complete observed missing-endpoint cascade:
scoped missing pin, `reset_0`, failed SDC read/fitting and exact flow summaries,
plus the existing classified optional LogicLock and electrical notices. IDs alone
are insufficient: message, path, severity and counts must match. Extra, duplicated,
missing or unrelated warnings/errors reject the negative sample. Generation logs
and successful compile/audit/netlist logs retain the builder's strict diagnostic
classification. This explains an intentional constraint failure, not a timing waiver. Expected
negative outcomes require the exact registered failure diagnostic and nonzero raw
exit; a generic failure or missing tool is not a successful negative sample.

Validate child records against complete fixed argv, working directories, selected
executable paths/content hashes/version probes, source SHA, recomputed builder
fingerprint, complete required files and actual file hashes. The validator uses
shared read-only command plans without rewriting retained artifacts. Cache-only samples cannot count as fresh
licensed execution. Freeze a canonical JSON envelope with admission tuple, fresh
invocation ID, controller/config/profile/input/tool hashes, each command and raw
exit, outcome and all immutable artifact hashes. Hash this complete envelope before
posting the final status. Store the returned status ID separately to avoid circular
hashing. Failure evidence and interrupted journals remain retained under workdir.

## Hosted attestation

Status context contains run ID, attempt and profile. Target URL is the exact
canonical workflow run URL; success description carries the envelope SHA256.
The waiter uses read permissions only and inspects individual statuses for the
exact SHA/context, including pagination. It accepts only the newest individual
status from the configured numeric creator ID in the current attempt time window.
An older success behind newer pending/failure cannot pass; ambiguous evidence,
wrong creator/URL, cancellation or timeout fails. No combined-green shortcut exists.

A digest authenticates the controller's reference to retained evidence; the hosted
waiter cannot independently verify unseen local waves. Anyone holding the same
controller credential is a trusted principal capable of forging its attestations.
Keep status-write credentials local and remove them from child environments.
No credential values or private machine paths appear in published documentation.

## Verification and activation boundary

Host tests exercise wrong admission identities, remote command/path fields,
replay/cancellation, concurrent lock attempts, interrupted journals, changed inputs,
missing/truncated artifact records, negative signatures, and stale/ambiguous statuses.
The shipped CLI fails before API calls or tool execution while disabled. No real
licensed invocation or status post is required or permitted by this bootstrap.

#32 separately reviews activation, existing environment policy, permissions and
actual dispatch/controller samples. A main-only licensed attestation is a postmerge
signal; making it a required incoming-PR context would create a merge deadlock.
Do not substitute an ancestor's status or dummy success for premerge proof.

Primary API contracts: [workflow runs](https://docs.github.com/en/rest/actions/workflow-runs),
[individual commit statuses](https://docs.github.com/en/rest/commits/statuses), and
[deployment branch policies](https://docs.github.com/en/rest/deployments/branch-policies).

## Commands and retained results

Host-only validation, safe while inactive:

```text
python -m unittest discover -s tools/ci/tests -v
```

The configured entry points currently return FAIL with an inactive-bootstrap
explanation before API or licensed calls. After separately reviewed #32 activation,
the local command form is:

```text
python -m tools.ci.controller --sha <authorized-main-sha> --run-id <run-id> --attempt <attempt> --profile questa-baseline --questa-bin <absolute-local-tool-directory>
python -m tools.ci.controller --sha <authorized-main-sha> --run-id <run-id> --attempt <attempt> --profile quartus-clocking --quartus-bin <absolute-local-tool-directory>
```

These are syntax examples, not activation instructions. The controller reads its
local status-write credential from `GH_TOKEN`; the hosted waiter receives only its
read-scoped job credential. The profile is selected locally and must match the
active fixed-name waiter job. There is no hardware, command, checkout-path or
journal-path profile option.

Each attempt retains admission, pending-status response, a separate detached
checkout, child command/stdout/stderr/raw-exit files, canonical envelope and final
status response under `workdir/ci/attempts/<invocation-id>/`. Build tags remain under
the child checkout's `workdir/builds/`. A successful command prints its envelope
path and SHA256; failed publication cannot erase the consumed journal or turn
partial evidence into a reusable success. Cleanup must retain complete files for
independent audit, not only digest pointers.
