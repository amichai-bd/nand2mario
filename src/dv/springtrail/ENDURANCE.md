# Continuous UART play and lifecycle

This fixture checks sampled UART endurance against the current independent
entity and progression models. It does not establish physical acceptance from
host tests or source execution. Board use follows the
[physical acceptance contract](../../../wiki/src/dv/springtrail/SPEC.md#physical-acceptance)
and requires explicit authorization, verified device/wiring/voltage, and
serialized access. It does not qualify VGA or physical controls.

<a id="retained-script"></a>

## Image and expectation binding

[endurance.py](endurance.py) builds Springtrail from current sources and binds
all 32,768 loaded/read-back bytes to that build's hash before traffic. The
expected wire identity is checked separately. An incompatible image is refused;
there is no permanent accepted-ROM hash. Build and result records retain the
image identity, source-derived LCD anchor, input journal and sample metadata.

The LCD anchor comes from [startup_anchor.py](startup_anchor.py), using the
built ROM and symbols, and must match the current frozen anchor used by the
runner. It is not selected from a board trace. Write `L` for this anchor and
`P = 70,224` dots for a frame. Setup checkpoints are `C(n) = L + n*P + 4,096`:
load and release input at dot zero, reach C(2), apply Start, reach C(3), release
Start, then reach C(5) before RUN. Load/reset epoch changes are checked.

[entities_reference.py](entities_reference.py) supplies complete game states;
[entities_frames.py](entities_frames.py) renders the approved art, entity
placements, block layer and progression HUD. The input schedule advances those
states using acknowledged INPUT application dots and source-frame identity.
Under the existing HALT/clock premise, ReadButtons accepts its direction and
action row reads at VBlank +316 and +388 dots. An input applies to a row only
when `applied_dot < read_dot`; equality keeps that row's prior value. Events
between the reads can therefore produce a mixed button mask, but never a mixed
expected image. Multiple events are processed in application order.

Each accepted packed frame must equal one complete reachable prediction across
all 23,040 pixels. There is no patrol exclusion or per-pixel union of candidates.
Pixels do not select future model state. Lives, countdown, OVER and reset are
part of that prediction: first retry spends one life and restores 400; 40 neutral
updates decrement the countdown to 399; the next retry leaves zero lives; the
Start from RETRY with zero lives reaches OVER, and a released/new Start restores
two lives and 400.
Entity phases and stage state remain part of the full expected frame.

## Fixed continuous schedule

Select the plan explicitly: `short` is two fixed20-second cycles and exercises
complete harness cleanup; `routine` is30 cycles/600 continuous seconds for ordinary
sustained hardware qualification; `full` retains90 cycles/1,800 seconds for explicitly
selected endurance milestones. These are not automatic gates for unrelated PRs.
The same alternating actions and lifecycle checks apply:

1. Even cycles hold Right+B (33); odd cycles hold Right+A (17), for 5.5 seconds.
   The settled route sample follows application by at least 280 frame periods.
   Its mode and HUD follow the complete lifecycle prediction, including OVER.
2. Release input for 0.1 seconds, hold Start (128) for 0.15 seconds, and check
   the predicted mode/frame at least three frame periods after application,
   including OVER when Start was accepted from RETRY with zero lives.
   Release Start before continuing.
3. The full plan uses cycles0/30/60; short retains its cycle0 pair. Routine uses
   cycles0/12/24, each proven to produce PAUSED then PLAYING with one life. These
   probes apply the same extra pair of released Start presses.
   The retained sample names `pause` and `resume` are labels, not mode claims.
   Cycles 0 and 60 produce PAUSED then PLAYING, with one life. Cycle 30 follows
   OVER: its first extra Start resets to PLAYING with two lives, and its next
   Start enters PAUSED. The model follows these actual lifecycle effects.
4. Remain RUNNING to the fixed cycle boundary. A cycle exceeding 20 seconds or
   a next-cycle start more than one second late fails.

There is no host HALT, RUN_DOTS, RESET, load or input-source switch inside the
continuous interval. In-game pause remains an ordinary input action. After the
last boundary, wait one additional second and sample while RUNNING. Both elapsed
monotonic time and public dot progress at 4,194,304 dots/second must cover the
planned interval. Only then HALT and release input.

Every sample checks running/paused state, image validity, UART input source,
requested/effective mask, reset epoch, complete frame length and source completion
at row 143. Frames must be fresh within two periods, with increasing sequence,
dot and retirement progress. Public 64-bit counters are read without tearing.
Full packed frames, hashes, metadata and acknowledged input dots are retained.
This is sampled endurance, not observation of every frame or retirement.

Finally perform three explicit RESET/full-upload/read-back/title/Start/play
cycles using the same derived checkpoints. Finish PAUSED, UART-selected,
input/effective input zero, with a certain session and released ownership.

## Budgets and failure handling

Whole-process caps are300 seconds short,780 routine and1,980 full, including
build, setup, checks, three selected-image exports and cleanup inside the supervised
worker. The continuous interval is measured separately. Qualify the routine forecast
from the complete short before physical execution. The worker refuses new cycle/lifecycle work at cap
minus 24 seconds; the supervisor terminates its own worker tree by cap minus
12 seconds and retains the budget result. There is no automatic extension or
unchanged retry. A complete short, including final sample and all three reset
cycles, precedes a full physical run; measured overhead must support its cap.

Any assertion, transport error or cleanup failure retains FAIL. Preserve the
original finding and any cleanup finding. HALT and INPUT 0 cleanup are attempted
only with a certain client; an uncertain reply permits no further traffic.

[test_endurance.py](test_endurance.py) and
[test_endurance_current.py](test_endurance_current.py) cover the fixed schedule,
coherent image prediction, lifecycle and input timing, plus wrong pixels/image,
epoch, stale frame, input, missing progress, duration, lifecycle and cleanup
failures. Synthetic endpoint failures are host checks, not physical fault proof.
Exact commands, versions, source/image identities, raw results and final state
are required for a new board qualification.


## Selected PR image attachments

[endurance_images.py](endurance_images.py) selects exactly three already checked
UART snapshots: origin-title,000-retry and000-pause. It verifies the original
packed-byte hash and encodes native160×144 lossless2-bit indexed PNGs using the
existing approved four-shade encoder. No state reconstruction or model image may
supply these bytes. Captions identify the sample, ROM hash, source frame/dot/epoch
and PNG hash; they contain no local adapter or machine identity.

Use supported GitHub CLI `--attach` to publish them in the run's PR. Pin a CLI
version whose real help exposes that flag. Upload success is only
UPLOADED_UNVERIFIED: read back all three durable GitHub asset URLs and download
through supported authenticated access, then compare each PNG hash before PASS.
Publication has a separate120-second command bound and measured result after the
physical endpoint is safely released. Failure is retained and never represented
as a successful attachment. Do not commit PNG bytes or substitute expiring
artifact/local links; PR attachments must survive worktree cleanup. Keep only
selected durable images and concise provenance, not a full snapshot archive.

A600-second run from reset does not reach the low32-bit dot wrap at1,024 seconds.
Retain focused counter/coherency proofs or explicitly selected longer coverage;
do not seed counters or claim the ten-minute result satisfies the30-minute
milestone. Actual-board snapshots do not prove the physical VGA monitor.

## Historical physical evidence

The results below belong only to image
`35aae757bde0ec9a15d6d6c84f14b45b451c341d2d4775f43ed8a9a762625192`.
Its LCD anchor was 167,840. Its earlier model used a patrol exclusion and lacked
the current progression/entity qualification; these are not current-image
results or evidence for the stricter full-frame oracle above.

| Plan | Whole seconds | Continuous seconds | Samples | Checked pixels | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Short | 102.7 | 42.409 | 15 | 344,544 | PASS on historical image |
| Full | 1,862.5 | 1,802.419 | 195 | 4,445,280 | PASS on historical image |

Both included four complete loads and the final safe state. Earlier evidence on
images `616de11b...` and `b551c562...` is also historical; neither its anchors nor
its older route/sampling rules define this fixture. Current source/model checks
do not turn any of these results into new FPGA evidence.
