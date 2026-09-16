# Continuous original v0.5 verification

The [v0.5 contract](../../../../wiki/src/dv/v05/SPEC.md) owns the program,
retirement fields, pixel phases and fixed input schedule. These tests drive the
actual UART endpoint and observe the composed CPU, PPU and shared input owner.
Existing loading faults use real UART loading; named short targets preload ROM.
The [revised matrix](../../../../wiki/src/dv/v05/SPEC.md#revised-milestone-matrix)
defaults composed execution to Intel preload with separate actual UART proof.
Its window/loading-mode separation is implemented below; qualification is
recorded in [PR246](https://github.com/amichai-bd/nand2mario/pull/246). No target uses
snapshots as its every-frame oracle.

`known()` reads one public logic snapshot. It accepts `0/1/L/H`, normalizes weak
bits, and rejects `X/Z/U/W/-` with `V05_UNKNOWN <signal>`. The conversion avoids
per-bit objects and does not consult `COCOTB_RESOLVE_X`. The runner already removes
that ambient setting; the ambient resolver's behavior on weak scalars is not part
of the observation contract. Under Verilator every value is two-state, so the
`V05_UNKNOWN` rejection is inert and uninitialized reads surface as mismatches
against the randomized initial values instead. Run
`python -B src/dv/python/v05/test_known.py` in the pinned Python DV environment
to check scalar and packed values, single reads, and resolver independence.

| Target | Required outcome |
|---|---|
| python-v05-identity | Read an independent 128-bit build identity through the actual UART and product Client |
| python-v05-identity-fault | The same checker rejects one changed DUT identity bit |
| python-v05-startup | Original build, full UART load/readback, blank and first normal frame, checked pause |
| python-v05-continuity | Preloaded continuity check: all 18 legacy input transitions at one-frame spacing, 23 frames, every retirement, write and pixel through actual pause; see [Continuity schedule](#continuity-schedule) |
| python-v05-image-fault | Actual ROM write at 0200 changes F3 to 00; LOAD_END rejects BAD_IMAGE |
| python-v05-pixel-fault | Actual first eligible source shade changes 1 to 0; exact pixel mismatch |
| python-v05-short | Preloaded complete path, two inputs, six frames and final pause |
| python-v05-iopeek | Live DMG I/O reads over actual UART pins while RUNNING: 120 LCD samples, advancing dots and divider, clear reserved bits, mode matching the scanline |
| python-v05-iopeek-fault | The same checker rejects a broken actual LY observation route |
| python-v05-progress-fault | Actual stopped gb_tick reaches the active-time watchdog |
| python-v05-bounded | Intel preload, real initialization, first-HALT Right+A, blank-to-normal input rows and every observation through actual pause |
| python-v05-bounded-pixel | Same bounded oracle rejects the actual first eligible shade changed1 to0 |
| python-v05-bounded-progress | Same bounded harness rejects actual stopped tick during first HALT |
| python-v05-physical | Same bounded original program receives atomic physical Right+A; actual UART selection, source isolation and switch-back readbacks |
| python-v05-physical-mask | Actual physical connection loses A; unchanged Right+A checker rejects the applied mask |

Fault targets are registered `expected_exit: "nonzero"` with the first line of
their named test's failure as `signature`, as the
[builder contract](../../../../wiki/tools/n2m/SPEC.md#python-testbenches-under-verilator)
defines: the builder reports PASS only when `results.xml` holds that failure, and
the simulator process exits zero either way. Measured under Verilator 5.052 with
the top-only public build: `python-v05-short` runs in 54 s and
`python-v05-startup` (full UART load and readback, 307 ms simulated) in 150 s,
both inside the default budget. Every test follows the
[300-second total wall budget](../../../../wiki/tools/n2m/SPEC.md#test-wall-budget),
including preparation, compilation, execution and checking. Target 120 seconds
per simulation and 300 seconds ordinary pre-merge aggregate. The legacy full
stimulus remains for historical interpretation, not execution. #88 owns the
revised matrix; PR246 records window/fault/endurance qualification. Do not
schedule a longer run to bypass the cap or treat timeout changes as new evidence.

Retirement/pixel CSV and public applied-input/UART JSONL observations remain
continuous. Flushed phase markers and 10ms simulated heartbeats distinguish
execution progress from buffered output. Controller boundaries refresh the
simulated Client clock before resuming a host command after autonomous time.

Public waveform projections open around initial RUN, LCD startup, the first
image completion, each fixed input window, the following CPU wake/update and its first updated frame, and final
pause. The projection changes recorded signal activity only; stimulus and
checks continue outside the windows. Wave-open/close observations record actual
dots. The full test retains original frame timing, including all intervening
frames; bounded startup success alone does not complete the contract.

## Continuity schedule

`python-v05-continuity` replaces the retired 600-frame `python-v05-continuous`
row, which needed about 10 s of simulated time and cannot finish under any wall
allowance at the measured rate of about 2 ms simulated per wall second. The
continuity schedule in `reference.schedule(continuity=True)` keeps the legacy
transition list unchanged and shortens only the spacing between transitions:
transition j (j = 1..18) is issued 20000 dots after normal frame j+1
completes, at `FIRST_IMAGE_END + j*70224 + 20000` (frame 1 completes at
`FIRST_IMAGE_END`), with a 2000-dot accept window during HALT, and is first
visible in frame j+3. The last transition (release of Right+A) is visible from
frame 21; the run ends after frame 22 completes at dot 1652371
(`CONTINUITY_FRAMES` = 23, frames 0..22), and the final pause must land within
2000 dots after it. The same `Online` monitor checks every retirement
(6358 setup plus 21 updates of 77), every program write, every pixel of all 23
frames, each applied-input reply against its window and mask, the
`continuity_monitor` and `time_progress` monitors (no reset, fault or early
pause; tick count equals elapsed time throughout) and the final pause window.
The target declares the 900-second
[wall allowance](../../../../wiki/tools/n2m/SPEC.md#declared-wall-allowance)
ceiling: runs measured 165..336 s at about 2 ms simulated per wall second
depending on concurrent simulation from other worktrees, and one run was
killed at a 450-second allowance under that contention.

Preserved from the legacy run: every button press and release and the Right+A
pair, in the frozen order, each with its exact apply window; the IF bit 4
request on a selected-line change and the `buttons` field in every retirement;
the VBlank wake and 76-retirement update that publishes the mask; its first
updated frame; every-pixel checking of every intervening frame; continuous
reset/fault/pause and tick-progress invariants from RUN through pause.
Weakened by the shorter window: the run observes 23 frames (0.39 s simulated)
instead of 602 (10 s), so 19-frame idle stretches between transitions and long
steady-state VBlank cadence are not exercised; the legacy frame identities
(update at frame 20j+3) are replaced by j+3; tick-progress drift is checked
over 0.39 s rather than 10 s, so a rare dropped or extra tick is caught only
if it falls inside that window; and the 450 ms simulation watchdog leaves
about 11 percent margin over the roughly 400 ms the schedule and its
command latency take. The matrix keeps sustained endurance on the FPGA, not
in simulation.

## Scoped implementation acceptance

`python-v05-short` runs the complete harness path with verified Intel preload,
Right press/release, all six frames and a real final HALT at 458563..460563.
It exercises the same completion checks as the legacy full target. Historical
#242 passed in 537.281 seconds under the former 600-second cap; this is not a
new 300-second PASS. The 150 ms simulation bound is not measured wall time.
`python-v05-progress-fault` stops actual gb_tick at dot 50000 during HALT and must
fail the active-time watchdog. Neither target proves the revised #88 matrix;
new bounded execution qualification belongs to #244.

Preload uses the actual original software pipeline and recorded image hash,
supported Intel ROM/presence initialization, and the real loader's CRC scan and
public initial-state reads. It does not inject CPU state or replace the retained
real UART loading/readback and actual image/pixel defect proofs.

## Bounded matrix execution

The named bounded target selects duration independently of loading mode. Its
fixed Right+A apply window is50000..52000 after the validated first HALT.
Request HALT at145132, then keep every monitor live through actual pause within
2000 additional dots. The owning fixed pixel schedule determines the expected
partial-row count from pause, never from the observed count. All valid pauses
require6358 complete retirement records, program writes, one input and both
blank startup and normal-frame input rows. The50 ms simulation watchdog is
independent of the300-second total host supervisor (288-second worker allowance).
The120-second runtime target is not claimed before measurement.

## Physical system boundary

Issue247 reuses that exact bounded ROM and oracle. After real load initialization,
the four host observations `(source, host, physical, effective)` must be
`(0,0,0,0)`. Select PHYSICAL through the actual UART while paused, expecting
`(1,0,0,0)`. During first HALT at50000..52000, drive public physical mask17 and
one commit on a system edge with `gb_tick=0`. This is the sole effective input
event and the unchanged oracle still requires6358 complete retirements and all
source pixels through actual final pause.

Readbacks then require `(1,0,17,17)`. UART INPUT2 must produce `(1,2,17,17)`;
INPUT17 and selecting UART produce `(0,17,17,17)`. A public physical commit0
then produces `(0,17,0,17)`. No step after the first physical commit may emit
another effective input event. Public source/effective ports must agree with
the independently prescribed states. These transactions occur before the
first VBlank; no expected CPU or pixel state is selected from observed values.
The original program checks JOYP by reading both rows and publishing its mask
through ordered retirement and map writes.

The mask fault changes the actual UART owner's physical input to1. The
unchanged checker must report `V05_INPUT_WINDOW` for expected17, actual1.
The board wrapper and legacy test modes retain inactive physical inputs.
This proof does not acquire ADC values or establish physical board controls;
those remain in issue156.
