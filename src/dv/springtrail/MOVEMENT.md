# Movement proof

The owning [verification matrix](../../../wiki/src/dv/springtrail/SPEC.md#movement-matrix)
separates the actual CPU routine proof, short composed game and whole-game FPGA
scrolling. Actual execution evidence is still pending.

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
300000-dot unit progress bound. Host/model and section-identity checks plus
independent source review precede this first actual CPU run. Its measured
duration will inform the selected aggregate; no budget exception is implied.

## Short composed game

The original complete game initializes normally through Intel preload and the
actual CRC scan/adoption. The software enables LCDC97 at independently derived
dot48708: the initialization, 160-byte OAM clear, tile/map copies and initial
renderer all execute on the actual CPU. The initial renderer costs656 routine
dots; its CALL and the preceding setup place the LCD write at that fixed dot.

Drive one ordinary UART INPUT129 (Start plus Right) at dot178708..180708,
before the second VBlank at184596. This clears the22 title tiles and performs
one walk update, yielding player(25,112), camera0, OAM(128,33,12,0) and SCX0.
The next complete world image must show the courier one pixel to the right.
The three complete output frames are startup white, title and that first world:
23040 pixels each, literal CRC32 B15161F6,5324BC1F,AE96D493. The literal original
artwork and independent physics select these images; no DUT state selects them.

Check every pixel's shade, coordinate, frame-start/eligibility flags and epoch2,
with strictly increasing dot timestamps. Frame k, row y must occur within
`[48708 + k*70224 + y*456, 48708 + k*70224 + (y+1)*456)`.
This allows real object-fetch stalls within the correct line. It does not claim
an exact per-pixel object timing oracle. Check the actual ordered title clears,
OAM/SCX writes and mode transition inside the normal VBlank interval. Retain all
26-field retirement records and check epoch/sequence/dot continuity; no full
register oracle is claimed. Request normal HALT at254616 and require actual
pause within2000 dots, complete trace trailer, all69120 pixels and no fault/reset.

The existing actual output-shade fault remains checked by the unchanged pixel
oracle. Its first nonwhite forced title pixel must fail; a setup failure is not
fault evidence. Both simulations retain the300-second total cap and120-second
target. The initial unit prefix measured124.389 seconds before its underestimated
dot guard stopped it. The revised unit plus game and fault forecast is390–405
seconds in aggregate, exceeding the300-second ordinary target. Each test still
obeys its300-second hard cap; no budget allowance or coverage waiver is introduced.
