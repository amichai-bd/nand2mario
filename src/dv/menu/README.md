# Menu test plan

Contract: [game menu](../../../wiki/src/sw/menu/SPEC.md) on the
[loader profile](../../../wiki/src/rtl/cartridge/MAS_loader_profile.md).
DUT: the built menu image running on the real
[`n2m_v05_system`](../../rtl/system/n2m_v05_system.sv) with the
[SDRAM controller](../../rtl/storage/n2m_sdram_ctrl.sv) and
[device model](../../rtl/storage/n2m_sim_sdram.sv). Expectations come from
[`reference.py`](reference.py), which composes frames from the layout rules
and the font's shade JSON, and from the loader contract; never from the ROM's
tilemap or DUT state.

[`fixture.py`](fixture.py) is the `menu` preload builder. Before each run it
builds the menu image through `sw build menu` and the
[`exit-demo`](../../sw/exit-demo/main.asm) game through `sw build exit-demo`,
writes the sixteen-slot SDRAM library (`menu-library.hex`), the reference
frames (`menu-frames.hex`: the scripted menu frames, the exit-demo game frame,
then the boot frame in nudge phase 1) and `menu-marks.hex` (the built image's
`Frame` address and the address after its `CALL WaitVBlank`, taken from the
build's own symbol and listing records) into the attempt directory. Slot 1
holds the built `EXIT DEMO` image: a solid bar on map row 8 (pixel rows 64..71 shade 3, the rest shade 0) and,
while Start is held, one write of the game exit value per frame. Slots 0, 2,
7, 8, 9, 10 and 15 hold stub games titled `SPRINGTRAIL`, `V05 BUTTONS`,
`SIXTEEN CHAR ROW`, `CGB ONLY TITLE` + `0x00 0xC0`, `ABC-123 XYZ 789`,
`CGB FLAGGED ROW` + `0x80` and `LAST SLOT`; slots 5-6 hold the 64 KiB
MBC1 stub `BANKED GAME` under one entry at 5 (its bank 2 writes the game
exit value); slot 3 is empty; slot 4 is valid to the menu but its entry
length is 16384, so the engine refuses it; slot 16 is the menu. Ten of the
sixteen rows are therefore valid, more than the three-game registry, and the
titles cover digits, dashes, the full sixteen-cell width, the CGB flag values
in header `0x143`, a two-slot image and the last row. The host-only tests use
a stub with the `EXIT DEMO` title in slot 1, so the menu reference frames do
not depend on the build.

[`tb_menu_system`](tb_menu_system.sv) preloads the device model from the hex
file, swaps the menu in with `WRITE_HOST(LIBRARY_CONTROL)`, selects the board
joypad, runs, and records every display-eligible frame from the system's
pixel source. A press is made at the start of a visible frame, so the menu
samples it in that frame's VBlank and its result shows in the next frame. A
frame shows what the previous VBlank left, so the frame that shows one press's
result is also where the next press is made, and one frame carries both. Only
a repeated mask needs a release frame of its own, and that frame is compared
too: every frame named below is compared pixel for pixel with its reference.
The select observer records the CPU commit into `$6000`-`$7FFF`.

| Requirement | Independent check |
|---|---|
| Boot frame | The first display-eligible frame equals reference frame 0: header, fifteen numbered rows above the window's plate, the star field's eight cells, nine titles with a blank last cell on the CGB-flagged slots 8 and 10, `BANKED GAME` once at slot 5, blank rows for slots 3, 6 and 11..14, the `SHORT IMAGE` title of slot 4, cursor on slot 0, blank status row; `LIBRARY_STATUS` shows bank 34 and result `OK` |
| Cursor | Down, Down, Up show the cursor on slots 1, 2, 1; Up at slot 0 and a repeated Up leave frame 0 unchanged; every frame is 23040 pixels in source order |
| Select | Down then A: the only write into `$6000`-`$7FFF` carries 1; the core boots in `DIRECT_ID` with epoch + 1, `LIBRARY_STATUS` result `OK` index 1 |
| MBC1 select | Five Downs (the fifth frame pixel-exact with the cursor on slot 5) then A: the write carries 5; the core boots in `MBC1_ID` with epoch + 1 and result `OK` index 5; the game's bank 2 code returns to the menu (epoch + 2, index still 5) and the menu runs in `LOADER_ID` |
| Exit register | Down then A starts the built `exit-demo` image in slot 1 (`DIRECT_ID`, epoch + 1, result `OK` index 1) and its first frame equals the independent bar reference; after the swap's core reset returned the input source to its UART default, the board joypad is selected again and Start is pressed: the only write into `$6000`-`$7FFF` carries `$10`, the menu is back in `LOADER_ID` with epoch + 2, result `OK`, index still 1, running without a host `RUN`, and its first frame equals reference frame 0 |
| Refused select | Cursor on the empty slot 3, A: `LIBRARY_STATUS` result `INVALID_SLOT` index 3 and the frame shows `SLOT 03 INVALID`; Up moves the cursor while the message stays; A on slot 2 starts that game with select data 2; `window_ready` stays set across the refused select |
| Nudge phase | The untouched menu animates by itself: displayed frame 15 still carries the plain arrow and the star field's first phase, frame 16 the nudged arrow and its second, both pixel-exact, which pins the phase boundary at 16 for the pointer and the stars together. The return to phase 0 at frame 32 is not simulated; it costs sixteen more simulated frames and follows from the bit-4 constant the image and `reference.phase_of_frame` share, which `test_menu_reference.py` covers |
| Frame budget | Every menu frame body, measured between the marks from the retirement stream, stays inside VBlank's 1140 M-cycles; the run prints each `MENU_COST` and fails with `MENU_VBLANK_OVERRUN` above it. An image swap resets the core and its dot counter, so a measurement that would span one is discarded and the first frame after a return is measured from the new epoch's first `WaitVBlank` exit; the discarded count must equal the swaps the fixture scripts, or the run fails with `MENU_COST_SPANS` |
| Tile range | Every map cell the menu writes, on the background map and the window map alike, names a tile in its 98-tile bank; a write outside it fails with `MENU_TILE_RANGE`. This bounds a row drawn with the wrong bank offset wherever it runs, including the delayed catalogue path no fixture reaches yet |
| Checker | `+pixel_fault` forces the source shade to 2 for the boot frame and must fail with `MENU_PIXEL frame=0 x=0 y=0 expected=0 actual=2` |
| Reference | `test_menu_reference.py`: font tiles equal the approved core glyphs, glyph mapping, the CGB flag rule in the last title cell only, layout rows, status texts, fixture library bytes and catalogue entry packing, snapshot unpacking and the negative pixel check |

## Targets

| Target | Fixture | Expected result |
|---|---|---|
| `menu-frame` | `frame` | `PASS menu-frame checks=9 frames=6 selects=0 commands=6` |
| `menu-select` | `select` | `PASS menu-select checks=8 frames=2 selects=1 commands=8` |
| `menu-select-mbc1` | `select-mbc1` | `PASS menu-select-mbc1 checks=9 frames=2 selects=1 commands=8` |
| `menu-exit` | `exit` | `PASS menu-exit checks=14 frames=4 selects=1 commands=11` |
| `menu-phase` | `phase` | `PASS menu-phase checks=6 frames=3 selects=0 commands=6` |
| `menu-refused` | `refused` | `PASS menu-refused checks=13 frames=6 selects=1 commands=9` |
| `menu-frame-fault` | `frame` with `+pixel_fault` | nonzero exit with `MENU_PIXEL frame=0 x=0 y=0 expected=0 actual=2` |

Run one with `python3 tools/build.py sim test <target> --tag <tag>` on WSL, or
the boot frames with `python3 tools/build.py tests run --label menu --tag
<tag>` and the selection paths with `--label menu-library`; `menu-phase` and
`menu-splash` carry `menu-animation`, `menu-select-mbc1` the `mbc1` and
`system` labels, and `menu-exit` the `system` label, so every aggregate stays
inside the ordinary 300-second budget with headroom; `menu-phase` has to
display 18 frames to reach the phase boundary, which no shorter check can
prove.
Verilator evidence is preliminary; the board evidence is the
[game library sessions](../../../wiki/src/board-bring-up.md#game-library-sessions),
with the exit register in
[session 7](../../../wiki/src/board-bring-up.md#session-7-game-exit-register-from-a-host-loaded-image).
