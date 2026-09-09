# Stackdrop execution proof

The [game contract](../../../wiki/src/sw/stackdrop/SPEC.md) owns behavior.
The independent `reference.py` and `cases.py` select all expectations before
execution. The original CPU unit performs73 updates: all28 rotations with
release/held history, horizontal/gravity/drop boundaries, one/four cleared rows,
score saturation and spawn failure/restart. Complete state, decimal score and
all96 board cells are reconstructed from public committed writes at every
checkpoint. Fifteen group ends prepare all118 image bytes for comparison.
The four-row clear additionally copies the full image to VRAM and checks all118
ordered address/data writes. No expected-result data is stored in the ROM.

The game and unit place rules/render/tables at identical addresses; verify their
complete linked section bytes. A separate entry in the same original unit ROM
stops normally after its first three updates. Its short target exercises the
same load, terminal marker, HALT, END and artifact path before the full run.

## Bounds fixed before runtime

Instruction-count upper bounds, rounded upward: Shape116 dots, Address220,
Valid1800 (four cells), Prepare6500 (96 board cells, four active cells,16 preview
clears, four preview cells and six HUD cells), ClearRows12600 (12 eight-cell
scans/copies, at most96 top clears and four score increments), Lock17000 including
spawn. One hard drop performs at most13 Valid calls, followed by Lock; including
update dispatch,42000 bounds any selected update. Combined with Prepare6500,
ReadButtons/Render4472 and loop/wake overhead below256, this is below53204,
leaving over17000 of70224 dots. These are conservative source bounds, not
measured timing claims.

For the fixed73 calls, at most40 ordinary collision checks plus13 hard-drop
checks, five locks, two board resets,15 prepared images and15 operand loads,
with1800 per extra spawn check and all call/marker overhead, fit under500000
dots. This explicit bound includes initialization and the one VRAM copy. The
short entry has only three updates and one preparation. Actual durations and
frontiers must be recorded; no unchanged timeout retry is authorized by a bound.

The local Render bracket must measure4496 dots:4472 for the two calls plus24
for loading/storing the end marker. The composed game must separately check
actual VBlank start to last VRAM write, including HALT wake/dispatch, and that
Update/Prepare finishes before the following VBlank. A local bracket alone does
not establish that whole-frame schedule.

Each simulation targets120 seconds and retains the300-second whole-process cap.
Run the short complete target first, then the full unit and its one intended
fault. The fault changes one actual WRAM store after the first update marker;
subsequent CPU reads preparing the image must fail the unchanged image oracle.
No product RTL behavior or positive stimulus changes for the fault.

