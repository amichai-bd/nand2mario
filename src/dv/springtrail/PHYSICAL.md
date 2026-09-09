# Scoped scrolling proof

This is the physical part of the [movement matrix](../../../wiki/src/dv/springtrail/SPEC.md#movement-matrix).
It checks original software movement and source-frame preservation. It is not
continuous milestone endurance, physical-control or connected-monitor evidence.

## Preconditions and budget

Before traffic, qualify the current source against the retained reviewed v05-board
fit from PR268, its exact SOF hash and build ID. Verify a fresh single-device JTAG
selection and the documented USB/UART identity, wiring, common ground and3.3V
setup. Program that SOF under the canonical machine mutex; require zero exit and
the programmer's affirmative success. Only that successful global restart permits
the existing shared host-session endpoint-restarted flag. Preserve its sequence
counter. Use the ordinary115200-baud Client/session and the same exclusive lock.

The driver then identifies the exact expected wire build, fully uploads the
fresh original32768-byte game package and reads back every byte. Fresh programming
plus the two loader resets predicts epoch2, which the first snapshot must confirm.
No test state, replacement clock, special hardware register or gameplay shortcut
is used. Keep all output in a fresh tagged directory, including commands, tools,
source/input hashes, transactions, packed frames and final result.

Declare one300-second whole-process supervisor, including preparation, programming,
transport, checks and the standard12-second cleanup reserve. The target is60
seconds; about13 seconds of ordinary game time plus22 snapshot readbacks, full ROM
upload/readback and command overhead is expected to take40–60 seconds. This is a
forecast, not measured evidence. The loop limits below cannot extend the supervisor.

## Independent input and frame schedule

`physical_driver.py` uses normal RUN/HALT intervals. STEP means one instruction,
not a requested number of dots, and is not used. Wall sleeps pace requests only;
all expectations use exact public INPUT application dots and snapshot metadata.

HALT returns a stable dot count. Inputs are changed only while paused in the
visible interval of the independently fixed70224-dot frame. If HALT lands inside
VBlank, at most six ordinary2ms RUN/HALT intervals seek a visible pause before
any input change. Reject any applied dot differing from that paused count or
falling in the whole VBlank/update interval. This excludes either JOYP row being
sampled across an input transition. The actual routine proof reserves enough
VBlank time for ReadButtons, movement, rendering and return to HALT.

`physical_reference.py` starts from the original title/player and steps the
independent integer model once per VBlank. Only the ordered applied-dot journal
chooses button masks. A source snapshot's completion must fall in row143 of its
independently numbered frame, with matching epoch and sequence. The metadata
selects time, never state from observed pixels or CRC. Compare every23040 shade
bytes against `movement_frames.image` for that independently predicted state.

Each waypoint is a fixed software-model x range, with at most eight bounded
RUN/HALT advances. Full snapshot readback occurs while paused, so its serial cost
cannot carry gameplay past the next input. Require increasing frame sequences,
UART source and the commanded effective mask at every checkpoint. Reject a gap
fall, missing frame, wrong range, stale frame or any pixel mismatch.

The22 named checkpoints in the driver cover title/start, before/after camera
entry, three forward gap jumps, both sides of the256-pixel scroll wrap, camera608
clamp and x760 world limit, then reverse scrolling through all three gaps, reverse
wrap, camera0 and x0. Right/B is33, Right/B/A49, Left/B34 and Left/B/A50. Start128
is applied separately while paused. Holding jump through each gap prevents an
extra rising edge on landing. An earlier walk and airborne odd-position corner
remain covered by the actual CPU unit and short composed proof.

The declared x ranges allow a few ordinary frames of UART control latency; their
expected pixels remain exact. No observed sprite location, CRC, or game RAM value
chooses a direction or expected frame. The host control-flow tests use synthetic
responses only to test this schedule and cleanup; they are not hardware evidence.

## Completion

End with normal HALT and INPUT0, public PAUSED/UART/zero effective mask and a
certain durable session. On a known failure, attempt that same safe cleanup.
An uncertain Client completion forbids further traffic and remains a failure;
do not silently reset or replay it. The outer supervisor must report all owned
processes ended and locks released. The
[PR270 evidence](https://github.com/amichai-bd/nand2mario/pull/270) records the
reviewed launcher and actual result against these conditions. This scoped proof
does not complete the later physical release milestone.
