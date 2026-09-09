# Original platformer verification

The original complete-game baseline is qualified;
[#264](https://github.com/amichai-bd/nand2mario/issues/264) physical
release acceptance remains open. The
[game specification](../../sw/springtrail/SPEC.md) owns gameplay;
the [charter](../../project-charter.md#release-acceptance) owns release criteria.
The [foundation proof](../../../../src/dv/springtrail/README.md) checks
the original title and initial world. The
[movement proof](../../../../src/dv/springtrail/MOVEMENT.md) covers the matrix
below, including selected physical scrolling frames. The
[interaction proof](../../../../src/dv/springtrail/INTERACTIONS.md) adds
actual CPU rules/rendering, composed publication checks and selected UART
success/retry/flow images. Full milestone and physical release acceptance
have separate qualification boundaries below.

The [next SML1-aligned release](../../sw/springtrail/sml1-alignment.md) owns the
staged divergence matrix and dependent measurement gates. Apply the bounded
milestone policy below to changed behavior; old ROM/image evidence remains
qualified only for unchanged inputs and claims. Reuse the combined 8x8/DMA/STAT
qualification only for unchanged relevant hardware; renderer changes require
their own end-to-end checks.

## Independent expectations

### Movement matrix

Movement uses complementary proofs without accelerating the game's frame
cadence. A host integer model freezes walk/run, opposing directions, jump edge
and held-A behavior, landing/side/head collisions, gap fall and world/camera
limits. An original CPU unit ROM calls the byte-identical assembled gameplay
routines, initializing ordinary operand WRAM through software and comparing
public writes to independent literal results. This unit proof does not claim
continuous whole-game cadence or rendering.

A short actual composed-game simulation covers real initialization, JOYP Start,
first movement and sprite rendering through the existing Intel preload and
continuous Python path; an actual output fault must fail the unchanged checker.
Each test obeys the existing 300-second total limit and 120-second target, with
the selected simulation aggregate measured against the 300-second target.

Scrolling uses the actual complete ROM on the reviewed FPGA build. Normal
paused INPUT and bounded RUN/HALT intervals preserve emulated frame timing.
Predict state from exact public INPUT application dots and fixed VBlank cadence;
reject input changes during the VBlank/update interval to exclude mixed JOYP-row
sampling. STEP completes one instruction and is not an advance-N-dots command.
Compare every
pixel of the selected frames, including entering tile columns, sprite/camera
alignment and camera boundaries. Snapshot metadata may confirm the independently
known frame; observed pixels/CRCs must not choose expected state. Freeze the
exact input/run/checkpoint script before execution and verify current build,
device/setup, full ROM upload/readback and final paused/zero-input state.
This is neither physical-monitor acceptance nor complete milestone acceptance.

The [foundation test definition](../../../../src/dv/springtrail/README.md)
defines the title/Start/first-world schedule. Its two targets
check all startup/title/world source pixels, ordinary WRAM state writes and a
real UART Start input on the actual composed system. An actual source-shade
fault uses the unchanged oracle. This bounded checkpoint does not claim the
later complete-game reference or release criteria below are met. The current
targets use the [movement definition](../../../../src/dv/springtrail/MOVEMENT.md)
and its independently updated initialization and sprite expectations.

Use original SM83 code and assets built by the existing Python pipeline. Two
clean builds must produce identical 32768-byte images. Pin source, asset, tool,
layout, header and ROM hashes, plus the exact direct-entry profile and reference
configuration. Expected physics/state transitions and literal HUD/frame
checkpoints must be written from the game rules before looking at DUT results.
Keep assembler/reference licenses and provenance under the existing source policy.

A pinned independent reference executes the same immutable original image and
input schedule. It must model the selected direct-entry state explicitly, not
silently use a commercial boot ROM. Preserve independent ROM encoding checks
and literal rule/frame anchors so a shared model mistake cannot redefine the
game. Do not select expected frame identity, physics, collision or CRC from DUT
internals, decoded signals, observed CRCs or a previous DUT recording.

Use ordinary JOYP inputs through the existing UART/shared-input path. Reuse the
builder, original-image preload, continuous Python observers, host play and
scripted transport infrastructure. Check visible frames/HUD and frozen game-state
checkpoints; where existing public observation permits, correlate ordinary CPU
writes to labeled WRAM state. Do not add privileged gameplay MMIO, state injection
or a general engine/AI framework to make the proof pass.

## Functional and milestone coverage

Interactions use the [interaction proof](../../../../src/dv/springtrail/INTERACTIONS.md):
independent state rules, an original CPU routine ROM, actual initialization and
render checkpoints with a meaningful fault, and ordinary-input complete-level
and failure/retry routes. Its short harness must complete before the full unit.
Logical state restoration alone does not prove restored map/OAM pixels; check
both, including pause and repeated restart during map preparation. Keep exact
render scheduling and physical input plans frozen before their dependent runs.

Focused stages cover initialization/title/start, walk/run/opposing directions,
jump/landing/wall/ceiling/gap behavior, camera and tile-column transitions,
enemy patrol/contact, one-time collection, win, retry and pause/resume/restart.
Include held/new-button distinctions and deterministic state restoration.
Freeze an ordinary successful route and a death/retry route with input times
and independently predicted observable checkpoints.

## V0.9 milestone

This is the one-time complete baseline. Its frozen script,
every-frame/input comparisons and failure rules remain unchanged. Later milestones use the
[future coverage selection and reuse policy](../integration/SPEC.md#milestone-acceptance),
not an automatic repeat of this full sequence. Select bounded scripts from the
delivered success, death/retry and flow routes to cover the required distinct
transitions, retaining independent expectations and explicit evidence mapping.

### Paused frame acquisition

The [capture driver](../../../../src/dv/springtrail/paused_capture.py) uses the
existing UART Client and immutable SNAPSHOT/READ_FRAME across bounded
host batches. Freeze ROM/build/reference bytes, input script and timing before
comparison. This short prerequisite does not complete the milestone matrix.

For the qualified pre-DMA-publisher ROM, LCD starts at dot 76964
and the period is 70224 dots. The later
[DMA publisher proof](../../../../src/dv/springtrail/OAM_DMA.md) owns the new
startup anchor; do not relabel this retained acquisition schedule.
Capture ordinal n starts at 1: pause at C(n) = 76964 + n * 70224 + 4096;
expect literal snapshot sequence n-1 and native callback n+1. C(1) therefore
captures source sequence 0/callback 2 (blank), C(2) sequence 1/callback 3 (title).
Reach C(1)=151284 from reset with counts 70224, 70224, 10836. Later captures
each advance 70224. Require COUNT, exact executed amount/completed dot and
public PAUSED/dot observations. No capture is omitted between checkpoints.

Apply the first gameplay input at C(2), before zero-based source frame 2's
VBlank. The prepared-map pipeline keeps sequences 2 and 3 on the title;
sequence 4 first displays that input's logical update. Reference prefixes and
final pipeline drains must be explicit in the separately reviewed matrix.
Each planned capture fixes its expected sequence, completion-dot range, epoch
and reference offset before SNAPSHOT. Retain all 5760 packed bytes and compare
all 23040 unpacked shades. Observed pixels/metadata never select the expected
state or index. Record every planned INPUT, applied dot and public source/mask.

Publish a continuation record only after all batch frames/inputs and the final
paused frontier are checked and stored. Bind the complete ordered evidence,
immutable plan/reference/ROM/build identities, epoch, next frame/input indices,
exact dot and durable UART next sequence. Before advancing, the next process
checks these bindings, the certain session and the same public paused frontier.
Reset/reload, changed input history, missing/duplicate frames, corruption, stale
state or an unfinished batch forbid continuation. Preserve failure without
reset or replay; uncertain replies retain the existing durable session rule.
A checkpoint alone is insufficient: continuation also binds the preceding
outer supervisor's successful completion within its total wall budget. The
initial origin binds a verified full load/readback and its known reset epoch.

Retain the planned mask across intermediate boundaries. Release it only at a
scripted change or final cleanup. Each batch uses the existing 300-second total
supervisor including cleanup. First qualify two consecutive short batches and
a certain final PAUSED/UART/input-zero state. Full interval/drain counts and
measured aggregate remain part of complete baseline acceptance.

For v0.9, identify the exact self-built ROM and independent reference profile.
Reach the named boot checkpoint within 600 emulated frame intervals, then run
3600 intervals of scripted start/movement/action. Every frame and input
checkpoint must agree with the reference; no unexplained mismatch, hang or reset
is allowed. These quantities are unchanged by the original-game scope revision.

Before milestone execution, freeze and independently review a measured matrix
that accounts for all required intervals and observations under the existing
[verification tiers and budgets](../integration/SPEC.md#verification-tiers).
Use short complementary simulations and separately declared physical work where
authorized, but do not replace the every-frame requirement with selected UART
snapshots, omit intervals or label unchecked frames as passed. A workable full
matrix is still an explicit prerequisite, not an assumed 3600-frame runtime or
a new time-limit exception. No unlimited or automatically extended simulation
is authorized by this specification.

An exact bounded dot command may pause at each frame boundary so every
pixel of all3600 intervals is read and checked, with every scripted input
retained. This is one emulation history: do not reload, reset or replay between
batches. Each host batch remains at most300 seconds; record aggregate measured
duration. Preserve startup and all interval identities across batches. CRC-only
checks, selected frames and missing pixels do not satisfy this approval. It does
not change the separate v1.0 continuous30-minute criterion.

Use actual Intel memories/models and the approved clocks/reset/input boundaries.
Each scoped harness must finish, report final pause/end state and enforce its
watchdog. Prove meaningful actual image, pixel, input and progress faults with
unchanged expectations and the specific first mismatch. Record raw simulator
status separately from Python XML and the builder outcome. Reuse prior evidence
only with exact relevant-input and behavior qualification; v0.5 is not v0.9.

## Physical acceptance

V1.0 requires the applicable [#28 board/display](https://github.com/amichai-bd/nand2mario/issues/28)
and [#156 controls](https://github.com/amichai-bd/nand2mario/issues/156) evidence,
reviewed current FPGA fit/timing/build identity and verified device, wiring,
ground, voltage and exclusive access. Standing authorization does not replace
those checks. Preserve the existing UART and physical source-selection contract.

Fully upload and read back the exact original game image over UART. Scripted
play checkpoints and pre-VGA frame hashes must agree with qualified simulation;
actual VGA, keyboard and shared physical controls must work. Complete one
30-minute continuous session without unexpected reset or lost input, then
repeat reset/load/start three times. Freeze input/endurance checkpoints and
their observability before the run, with a separately reviewed physical budget.
Report sampling limits honestly; the duration does not imply every physical
retirement/frame was observed. End in the documented safe paused/input state and
verify child processes, sessions and locks are released.

Reuse qualified complete-baseline deterministic gameplay/reference and fault evidence when
relevant identities and behavior remain unchanged; select affected checks for
changes. Use the required lifecycle upload/readback to provide applicable
transport evidence rather than adding a duplicate unchanged transport suite.
This removes no required full load/readback or reset/load/start cycle. Freeze
the selected script and continuous session's input/sampling/failure plan under
the linked milestone policy. Paused deterministic acquisition does not count
toward continuous endurance. A connected monitor or simulation result alone
does not prove actual VGA, keyboard or shared physical control operation;
missing #28/#156 evidence remains a release blocker.

These requirements do not close GAP-012 or #28 by simulation. Silent output is
intentional. [#32](https://github.com/amichai-bd/nand2mario/issues/32) still owns
trusted CI/hardware-job activation; its unfinished route does not block ordinary
reviewed local delivery under the existing external-CI policy.
[#168](https://github.com/amichai-bd/nand2mario/issues/168) retains the historical
finite-Tcl diagnostic and is off the original-game delivery path. No existing
issue's success criteria are waived by this plan.

## Interaction display timing

The renderer uses one displayed frame of input-to-publication delay. Freeze input
samples by the documented VBlank boundary and compare each complete image
against the preceding prepared state, including title, pause and restart.
Independent expected images must apply the same single-frame relationship;
never choose a state from observed pixels. Check visible-time computation
has no display-memory/register writes and publication completes in VBlank.
The existing per-test and aggregate budgets and physical acceptance remain.
