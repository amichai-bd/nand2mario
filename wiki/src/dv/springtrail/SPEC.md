# Original platformer verification

Status: planned under [#263](https://github.com/amichai-bd/nand2mario/issues/263)
and [#264](https://github.com/amichai-bd/nand2mario/issues/264). The
[game specification](../../sw/springtrail/SPEC.md) owns gameplay;
the [charter](../../project-charter.md#release-acceptance) owns release criteria.
The [foundation proof](https://github.com/amichai-bd/nand2mario/pull/266) checks
the original title and initial world. No complete-game or physical release
acceptance is claimed here.

## Independent expectations

### Movement matrix

Issue #261 uses complementary proofs without accelerating the game's frame
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
This is neither physical-monitor acceptance nor the later #263/#264 milestone.

The [foundation test definition](../../../../src/dv/springtrail/README.md)
freezes the original title/Start/first-world schedule for #260. Its two targets
check all startup/title/world source pixels, ordinary WRAM state writes and a
real UART Start input on the actual composed system. An actual source-shade
fault uses the unchanged oracle. This bounded checkpoint does not claim the
later complete-game reference or release criteria below are met.

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

Focused stages cover initialization/title/start, walk/run/opposing directions,
jump/landing/wall/ceiling/gap behavior, camera and tile-column transitions,
enemy patrol/contact, one-time collection, win, retry and pause/resume/restart.
Include held/new-button distinctions and deterministic state restoration.
Freeze an ordinary successful route and a death/retry route with input times
and independently predicted observable checkpoints.

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

These requirements do not close GAP-012 or #28 by simulation. Silent output is
intentional. [#32](https://github.com/amichai-bd/nand2mario/issues/32) still owns
trusted CI/hardware-job activation; its unfinished route does not block ordinary
reviewed local delivery under the existing external-CI policy.
[#168](https://github.com/amichai-bd/nand2mario/issues/168) retains the historical
finite-Tcl diagnostic and is off the original-game delivery path. No existing
issue's success criteria are waived by this plan.
