# Every-frame milestone schedule

[#263](https://github.com/amichai-bd/nand2mario/issues/263) preserves boot within600
frame intervals followed by3600 scripted intervals. Host-paused full-frame
acquisition is approved; [#283](https://github.com/amichai-bd/nand2mario/issues/283)
delivered its reusable driver in PR284. [PR288](https://github.com/amichai-bd/nand2mario/pull/288)
records the complete paused DUT execution of the matrix below.
[#286](https://github.com/amichai-bd/nand2mario/issues/286) owns delivery of the
complete native schedule/ledger prerequisite; it does not close #263.

Freeze the corrected32768-byte ROM SHA256
`b551c56252761d953bcf3b64270d819e3342b710299c3bff6866d4dcae8ba667`, untouched
SameBoy Core213a12ce93d66b105a113debd9396306066a7cfc and direct DMG_B profile.
PR282's two clean builds and refreshed same-byte build qualify image provenance.
The old PR279 image/reference remains historical.

Use source-defined LCD commit76964, period70224 and checkpoint
`C(n) = 76964 + n*70224 + 4096`. Indices below are zero-based source sequences:

| Event | Exact fixed identity |
|---|---|
| Capture at C(n), n>=1 | Source sequence n-1; native callback n+1; all23040 pixels |
| Boot | C1 captures blank sequence0; C2 captures title sequence1, within600 |
| Input i, 0<=i<3600 | Apply while paused at C(2+i), sample in VBlank of frame2+i |
| Consequence of input i | Compute in visible frame3+i, publish in VBlank3+i, display frame4+i |
| Last scripted input | C3601; compute frame3602; display frame3603 |
| Drain | Neutral inputs at C3602/C3603; capture every interval through C3604 |
| Total retained images | Source sequences0..3603 plus both native initialization callbacks |

Inputs never depend on observed pixels, CRC or frame metadata. Native key calls
occur at the first instruction boundary at/after the same checkpoint, at most24
dots late; that visible-phase allowance cannot intersect the VBlank JOYP sample.
The native runner continues to the final checkpoint after its last full callback.
Neutral drain execution remains in the reference interval; it is not a reset or
an omitted interval. Display lag means its newly computed state is not required
to appear in a frame that was already complete.

`milestone.py` freezes the script: the existing original success route, ordinary
Start restart, existing death/retry route, pause/resume and Select restart, then
success/restart routes repeated to3600 updates. Fixed checkpoints include WON360,
death RETRY548, Start retry549, pause551/resume553, pause555/Select restart557,
and pause558/resume560. Later wins occur920/1281/1642/2003/2364/2725/3086/3447.
The final scripted state is PLAYING, score1, camera256; no expected state comes
from a DUT. Repeated contact/once-only score and exact restoration component
proofs from PR276 remain qualified separately from this full frame sequence. Its first
new route holds Start from the restart, preserving edge semantics. The short
complete lifecycle uses four updates129/1/1/1 and two neutral drains, eight source
frames, allowing two four-frame acquisition batches. PR287 qualified the full
route/model and native execution before the full DUT matrix.

Every batch must finish within300 seconds including identity checks, run, full
readback, comparison, pause and cleanup. Measure the short lifecycle before
choosing full batch size and declaring aggregate wall time. Preserve exact ROM,
build, epoch, sequence, paused dot, input history and native ledger across batches;
no reset, replay or skipped frame may recover an incomplete batch. Image/pixel/
input/progress fault coverage and current-head review remain required. #264's
continuous physical milestone and #28/#156 remain separate.

## Native completion

The existing probe's explicit `springtrail-milestone-short` case executes eight
normal callbacks and continues to checkpoint642852; the full
`springtrail-milestone` executes3604 normal callbacks and continues to253168356.
Retain the two initialization callbacks, schedule.json, every row-major image,
actual key applications and terminal record. End may be at most24 dots after the
fixed checkpoint because the native public API advances an instruction. No
additional normal callback is allowed. Normal callback spacing must be70224.

The checker compares every pixel with the independent original model, and checks
sampled C019/mode using fixed indices. At native callback j, displayed model state
is update max(0,j-5); sampled input is zero for j<5 and script input j-5 otherwise;
logical mode is update max(0,j-4). Initial callbacks and first normal frame are
blank. No callback, mask or offset is selected from DUT observations.

The native pre-run forecast was10 seconds short and60-180 seconds full, including
model image comparison; measured results follow below. Each invocation keeps
the existing300-total/288-worker/12-cleanup supervisor and canonical mutex.
The input fault changes actual key API masks. The milestone progress fault stops
after the final required callback but before the terminal checkpoint, requiring
END_TIME rejection despite complete frame/input counts. Legacy progress faults
retain their original100000-dot stop. This is actual truncated execution;
frame fault remains explicitly a serialized-image mutation. Native execution
is complete as recorded below. The full acquisition aggregate was declared after
short native/acquisition measurements, before the full hardware matrix.

| Fault boundary | Scoped evidence and remaining witness |
|---|---|
| Immutable image | PR282 rejects old image identity before native tools; PR284 validates full upload/readback and rejects changed expected image/hash before acquisition. Repeat full corrected-ROM load/readback only at the full-run origin. |
| Actual DUT pixel | PR276's real source-shade mutation and unchanged checker rejection, qualified in PR282; native serialization/host readback mutations only test their own new infrastructure. |
| Input | PR287 actual zero-key fault fails INPUT_MASK on the new schedule. PR284 checks exact applied mask/dot and rejects mismatched transport/plan input; full execution retains every checkpoint. |
| Progress | PR287 actual exit after all callbacks before the fixed checkpoint fails END_TIME. PR284 rejects partial RUN_DOTS, missing/duplicate frames and unbound continuation. |

These proofs complement every-frame positive execution; they do not claim a
host-file mutation is an actual DUT defect or remove any required interval.

## Native result

The complete short at c736d40 retained10 callbacks/eight normal frames/six inputs,
ending642856 in6.047 seconds. Its unchanged executable behavior is qualified
across the child-worktree move; the producing artifacts remain in263.
Full b44ad16 passed in27.741 seconds:3606 complete images,3604 normal frames,
3602 inputs and exact end253168356. Measured qualification0.071s, build4.720s,
link0.428s, native execution3.667s and image checking17.978s are component timings,
not an exhaustive disjoint wall total.

At f91c8dd, serialized-image/input/late-progress faults failed their intended
BLANK_FRAME/INPUT_MASK/END_TIME checks in5.928/5.562/5.343 seconds. The progress
case retained all callbacks/inputs but ended634196 before642852. Every raw tool
and native command exited0; intended checker failures returned outer1. Aggregate
50.621 seconds met300; each invocation met120 target and300 hard limit. The fault
branch changes no positive behavior. [PR287](https://github.com/amichai-bd/nand2mario/pull/287)
owns exact commands, identities and review. No DUT/full milestone acceptance is
inferred from this reference result; #263 retains the full DUT comparison.

## Full paused acquisition budget

The reviewed short lifecycle in [PR284](https://github.com/amichai-bd/nand2mario/pull/284)
captured four frames after full ROM load/readback in18.089420 seconds and four
more in a separate continuation in8.336349 seconds. All eight frames matched
the native reference. These measurements preceded selection of80-frame batches.

The full run uses46 batches:45 batches of80 frames and a final batch of4.
Scaling the continuation measurement gives166.727 seconds per80; adding the
measured9.753-second first-load difference gives176.480 seconds for the first80.
Allow200 seconds per80 for full83,082,240-byte reference validation, cumulative
checkpoint/artifact verification and other overhead. Forecast about2h35 total
physical wall time including coordination; the completed native50.621-second
matrix is recorded separately. These are forecasts, not guaranteed runtimes.
Individual80-frame batches are expected to miss120-second targets. Every batch
still has a300-second total hard limit, including setup, comparison and cleanup.

The first80 is the beginning of the one full execution history, not a disposable
timing run. Before advancing, verify its actual successful outer supervisor,
all80 complete frames/pixels, input frontier and durable checkpoint, then review
the measured remaining forecast. Never reset/replay the first batch to improve
its timing. Every continuation binds the preceding successful outer result,
checkpoint and artifact hashes, same ROM/build/epoch, paused dot, input history
and complete native ledger. Cumulative validation stays inside each300-second cap.
Any timeout or incomplete checkpoint stops further advancement for concrete
failure review; missing intervals cannot be repaired by silent replay or reset.

The first invocation verifies fresh device/setup and the reviewed programmed
build, then performs the corrected-ROM full upload/readback and binds its actual
new epoch. Later invocations do not reload/reset. Serialized machine/session
access, exact RUN_DOTS completion, immutable full snapshot readback, final
PAUSED/UART/neutral/certain state and failure evidence remain mandatory.
Capture every source sequence0..3603 and input0..3601, including boot and both
neutral drain intervals. Retain/account both native initialization callbacks;
none are substituted for source frames. No physical buttons/camera or continuous
#264 release result is claimed by this paused verification.

## Full acquisition result

At producing commit204cefbb, all46 batches passed:3604 complete source frames,
83,036,160 compared pixels and3602 exact input checkpoints in one epoch6 history.
The initial corrected-ROM upload/readback verified all32768 bytes. The final
frontier was PAUSED at253168356 dots,6028674 retired instructions, UART input0
and a certain session. No reset, reload, replay or frame omission occurred after
the initial load. Captures verify pre-VGA source images, not monitor output.

Measured batch aggregate was5318.1169044 seconds (88m38s). First80 took127.3057574
seconds and exceeded the120-second target; every other batch met that target,
and all46 met300 seconds total. The final four-frame batch took12.9698733 seconds.
PR288 retains exact commands, immutable reference/setup/launcher identities,
all batch receipts and independent review. Later documentation changes do not
change the producing hardware, software, capture driver or reference inputs.
