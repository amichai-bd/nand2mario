# Movement proof

The owning [verification matrix](../../../wiki/src/dv/springtrail/SPEC.md#movement-matrix)
separates the actual CPU routine proof, short composed game and whole-game FPGA
scrolling. The latter two acceptance stages are still being prepared.

## CPU unit checkpoint

`python-st-unit` loads an original software unit ROM through the existing Intel
preload, actual CRC scan and Client adoption. The unit and game link the same
movement, renderer and literal world at addresses 2000,2800,1400 hexadecimal.
Their complete section bytes must be identical before execution. There are no
expected results in the unit ROM: only ordinary WRAM operands and input masks.

The ROM executes 84 steps: walk/run/opposed direction, complete held-jump arc,
release/rejump, gap fall and hold, side/head/landing contacts, fractional contact,
both horizontal bounds, camera anchor/tile boundary/256-pixel wrap/right clamp.
Each step calls the actual movement routine and emits the resulting 14 state
bytes through ordinary WRAM writes. Boundary cases also call the actual
renderer. Compare all emitted bytes and selected OAM/SCX/new-column writes to
the independent integer model and literal world; input history selects expected
states, never observed DUT values. The unit loop preserves actual state between
successive steps within each group.

Normal software marker writes bracket the routines. Require every measured
movement/render call to finish within 4560 dots, conservatively including call
and marker overhead, so VBlank writes can complete before the next scanline.
This measures routine execution, not continuous full-game frame cadence.

The existing optional passive trace retains every public write/retirement.
Reject unknown/truncated lines, wrong/missing/reordered report bytes, incorrect
markers, extra input/pixels and missing terminal/END records. Require the actual
terminal marker, normal host HALT, no reset/fault and bounded cleanup. Expected
results are frozen in `movement_reference.py` and `unit_cases.py`; the original
driver is `src/sw/springtrail/unit.asm`.

Declare the existing 300-second whole-process cap, 120-second target and
200000-dot unit progress bound. Host/model and section-identity checks plus
independent source review precede this first actual CPU run. Its measured
duration will inform the selected aggregate; no budget exception is implied.
