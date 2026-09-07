# Continuous original v0.5 verification

The [v0.5 contract](../../../../wiki/src/dv/v05/SPEC.md) owns the program,
retirement fields, pixel phases and fixed input schedule. These tests drive the
actual UART endpoint and observe the composed CPU, PPU and shared input owner.
The milestone and loading faults use real UART loading. Only the named short
implementation targets preload ROM; no target uses snapshots as its every-frame oracle.

| Target | Required outcome |
|---|---|
| python-v05-startup | Original build, full UART load/readback, blank and first normal frame, checked pause |
| python-v05-continuous | The same startup followed by all 600 intervals and 18 input transitions |
| python-v05-image-fault | Actual ROM write at 0200 changes F3 to 00; LOAD_END rejects BAD_IMAGE |
| python-v05-pixel-fault | Actual first eligible source shade changes 1 to 0; exact pixel mismatch |
| python-v05-short | Preloaded complete path, two inputs, six frames and final pause |
| python-v05-progress-fault | Actual stopped gb_tick reaches the active-time watchdog |

Fault runs require failing Python/XML and nonzero outer builder; preserve the
actual raw simulator exit independently. The continuous target uses a 36000s
wall bound and 12s simulation deadline. The measured startup completed 307.348ms
in 758.318s; scaling that rate to about 10.4s and adding margin gives the finite
full-run budget. This is a budget estimate, not measured full-run throughput.

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
It exercises the same completion checks as the full target. Its 600-second wall
and 150 ms simulation limits are bounds, not measured results.
`python-v05-progress-fault` stops actual gb_tick at dot 50000 during HALT and must
fail the active-time watchdog. Neither target proves the unchanged full 600
intervals/all 18 transitions; that milestone remains open under #88.

Preload uses the actual original software pipeline and recorded image hash,
supported Intel ROM/presence initialization, and the real loader's CRC scan and
public initial-state reads. It does not inject CPU state or replace the retained
real UART loading/readback and actual image/pixel defect proofs.
