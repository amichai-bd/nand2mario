# Continuous original v0.5 verification

The [v0.5 contract](../../../../wiki/src/dv/v05/SPEC.md) owns the program,
retirement fields, pixel phases and fixed input schedule. These tests drive the
actual UART endpoint and observe the composed CPU, PPU and shared input owner.
Existing loading faults use real UART loading; named short targets preload ROM.
The [revised matrix](../../../../wiki/src/dv/v05/SPEC.md#revised-milestone-matrix)
defaults composed execution to Intel preload with separate actual UART proof.
Its new window/loading-mode separation remains open in #244. No target uses
snapshots as its every-frame oracle.

`known()` reads one public logic snapshot. It accepts `0/1/L/H`, normalizes weak
bits, and rejects `X/Z/U/W/-` with `V05_UNKNOWN <signal>`. The conversion avoids
per-bit objects and does not consult `COCOTB_RESOLVE_X`. The runner already removes
that ambient setting. In cocotb 2.0.1, direct scalar `int(Logic('L'))` under the
ambient `error` resolver raises despite `is_resolvable`; this unused resolver
corner is not part of the runner's observation contract. Run
`python -B src/dv/python/v05/test_known.py` in the pinned Python DV environment
to check scalar and packed values, single reads, and resolver independence.

| Target | Required outcome |
|---|---|
| python-v05-identity | Read an independent 128-bit build identity through the actual UART and product Client |
| python-v05-identity-fault | The same checker rejects one changed DUT identity bit |
| python-v05-startup | Original build, full UART load/readback, blank and first normal frame, checked pause |
| python-v05-continuous | Legacy 600-interval/18-input schedule; not authorized to run under the revised matrix |
| python-v05-image-fault | Actual ROM write at 0200 changes F3 to 00; LOAD_END rejects BAD_IMAGE |
| python-v05-pixel-fault | Actual first eligible source shade changes 1 to 0; exact pixel mismatch |
| python-v05-short | Preloaded complete path, two inputs, six frames and final pause |
| python-v05-progress-fault | Actual stopped gb_tick reaches the active-time watchdog |

Fault runs require failing Python/XML and nonzero outer builder; preserve the
actual raw simulator exit independently. Every test follows the
[300-second total wall budget](../../../../wiki/tools/n2m/SPEC.md#test-wall-budget),
including preparation, compilation, execution and checking. Target 120 seconds
per simulation and 300 seconds ordinary pre-merge aggregate. The legacy full
stimulus remains for historical interpretation, not execution. #88's revised
matrix and #244's new window/fault/endurance proof remain unpassed. Do not
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
