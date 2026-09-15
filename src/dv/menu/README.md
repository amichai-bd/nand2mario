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
builds the image through `sw build menu`, writes the seventeen-image SDRAM
library (`menu-library.hex`) and the scripted reference frames
(`menu-frames.hex`) into the attempt directory. Slots 0, 1, 2 and 5 hold stub
games titled `SPRINGTRAIL`, `STACKDROP`, `TRAIL UNIT` and `ABC-123 XYZ 789`;
slot 3 is empty; slot 4 is valid to the menu but its entry length is 16384,
so the engine refuses it; slot 16 is the menu.

[`tb_menu_system`](tb_menu_system.sv) preloads the device model from the hex
file, swaps the menu in with `WRITE_HOST(LIBRARY_CONTROL)`, selects the board
joypad, runs, and records every display-eligible frame from the system's
pixel source. A step presses one button at the start of a visible frame, so
the menu samples it in that frame's VBlank, releases it at the start of the
next frame and compares that frame pixel for pixel with the named reference
frame. The select observer records the CPU commit into `$6000`-`$7FFF`.

| Requirement | Independent check |
|---|---|
| Boot frame | The first display-eligible frame equals reference frame 0: header, sixteen numbered rows, four titles, blank rows for slots 3 and 6..15, the `SHORT IMAGE` title of slot 4, cursor on slot 0, blank status row; `LIBRARY_STATUS` shows bank 34 and result `OK` |
| Cursor | Down, Down, Up show the cursor on slots 1, 2, 1; Up at slot 0 and a repeated Up leave frame 0 unchanged; every frame is 23040 pixels in source order |
| Select | Down then A: the only write into `$6000`-`$7FFF` carries 1; the core boots in `DIRECT_ID` with epoch + 1, `LIBRARY_STATUS` result `OK` index 1 |
| Refused select | Cursor on the empty slot 3, A: `LIBRARY_STATUS` result `INVALID_SLOT` index 3 and the frame shows `SLOT 03 INVALID`; Up moves the cursor while the message stays; A on slot 2 starts that game with select data 2 |
| Checker | `+pixel_fault` forces the source shade to 2 for the boot frame and must fail with `MENU_PIXEL frame=0 x=0 y=0 expected=0 actual=2` |
| Reference | `test_menu_reference.py`: font tiles equal the approved core glyphs, glyph mapping, layout rows, status texts, fixture library bytes and catalogue entry packing, snapshot unpacking and the negative pixel check |

## Targets

| Target | Fixture | Expected result |
|---|---|---|
| `menu-frame` | `frame` | `PASS menu-frame checks=9 frames=6 selects=0 commands=6` |
| `menu-select` | `select` | `PASS menu-select checks=8 frames=2 selects=1 commands=8` |
| `menu-refused` | `refused` | `PASS menu-refused checks=13 frames=6 selects=1 commands=9` |
| `menu-frame-fault` | `frame` with `+pixel_fault` | nonzero exit with `MENU_PIXEL frame=0 x=0 y=0 expected=0 actual=2` |

Run one with `python3 tools/build.py sim test <target> --tag <tag>` on WSL, or
all of them with `python3 tools/build.py tests run --label menu --tag <tag>`.
Verilator evidence is preliminary; the board criterion belongs to
[#681](https://github.com/amichai-bd/nand2mario/issues/681).
