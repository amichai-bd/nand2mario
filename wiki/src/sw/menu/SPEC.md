# Game menu

The [menu source](../../../../src/sw/menu/main.asm) is the original SM83
program in library image 16. It lists the game slots from the catalogue
through the banked window, moves a cursor with the joypad, starts the
selected game through the select register and shows the loader's result when
a selection is refused. The [loader profile](../../rtl/cartridge/MAS_loader_profile.md)
owns every register, bound and result code this page uses; the
[SDRAM layout](../../rtl/storage/MAS_sdram.md#address-space-layout) owns the
slot, catalogue and entry format; the [software toolchain](../../../tools/sw/SPEC.md#implemented-linker-and-packager)
owns the `dmg-loader-v1` package profile the image is built in. This page owns
the menu's behavior, memory use, frame layout and verification.

## Behavior

Boot, from the direct entry state with the LCD off:

1. Load the 39 font tiles into VRAM `$8000`, blank the background map at
   `$9800`, set BGP `$E4` and zero scroll, draw the header and the sixteen
   slot numbers, and put the cursor on slot 0.
2. If `$A000` bit 5 (`sdram_ready`) is set, commit bank 34 (the catalogue,
   `LIBRARY_CATALOGUE_ADDRESS / LIBRARY_WINDOW_BYTES`) to the bank register,
   wait for bit 6 (`window_ready`) and draw the sixteen title rows from the
   window. Otherwise skip the catalogue; the frame loop retries below.
3. Draw the status row and turn the LCD on (`LCDC = $91`, background only).

Every frame, at the start of VBlank (`LY == 144`) and finishing inside it:

1. Read both JOYP rows, settling at least 24 dots after each row select, and
   keep the released-to-pressed edges in the generated `BUTTON_*` bit order.
   A held button acts once.
2. A Down edge moves the cursor one slot down, then an Up edge one slot up,
   clamped to slots 0..15; no wrap.
3. An A edge, once all sixteen title rows are listed, writes the cursor's
   slot index to the select register and polls `$A000` bit 7 until the
   loader is idle. An accepted select swaps the image and resets the core;
   the menu never resumes. A refused select leaves its result in `$A002` and
   the index in `$A003`. Before the catalogue is listed, A does nothing.
4. Delayed catalogue path: when bank 34 has not been committed and
   `sdram_ready` is now set, commit it; when it has been committed and
   `window_ready` is set, draw one remaining title row per frame.
5. Redraw the cursor cell and the status row only when they changed, so the
   ordinary frame writes at most two map cells plus one row.

The catalogue is read once, at boot or through the delayed path; the drawn
map is the menu's copy of the titles. Nothing after a selection depends on
`window_ready`.

The menu lists game slots 0..15 only. It reads all 17 catalogue entries
through the window but never lists entry 16, which is itself. A slot is drawn
with its title when its catalogue `valid` byte is `LIBRARY_CATALOGUE_VALID`;
any other entry is drawn as its slot number with a blank title. The cursor
visits every slot, so selecting an empty one is how the player sees
`INVALID_SLOT`. Length and profile are the engine's checks: a `valid` entry
with a wrong length is listed and its selection is refused with the same
result. The menu does not look at the `crc32` or `length` fields. A 64 KiB
MBC1 image has one entry at the first of its two slots and an empty entry at
the second, so the menu lists it once and shows the second slot's number with
a blank title.

Selecting a slot whose image copies but fails the CRC leaves the console
paused with no valid image; the menu code cannot run, so the `BAD CRC` word
is reachable only through the status bytes if the hardware ever reports it
to a running menu. KEY1 or the host recover as the loader contract states.

A game may offer its own back-to-menu action: a direct-profile write of
`LIBRARY_GAME_EXIT_VALUE` (`$10`) to `$6000`-`$7FFF` returns to this menu
exactly like KEY1 ([game exit register](../../rtl/cartridge/MAS_loader_profile.md#game-exit-register)).
The menu itself is unchanged by it.

## Memory map usage

| Range | Use |
|---|---|
| `$0200`-`$04F3` | `code` section: entry `Start`, frame loop, drawing routines and text tables (756 bytes) |
| `$0800`-`$0A6F` | `assets` section: the 39 font tiles, 624 bytes, from `ASSET "Font"` |
| `$4000`-`$7FFF` | The banked window; the image keeps the upper half `$FF` because the hardware maps SDRAM there. The linker refuses ROM1 sections in this profile |
| `$2000`-`$3FFF` write | Bank register: the menu writes 34 once per boot |
| `$6000`-`$7FFF` write | Select register: the cursor's slot on an A edge |
| `$A000`, `$A002`, `$A003` | Status byte, last result, last selected index |
| `$8000`-`$826F` | Font tiles 0..38 |
| `$9800`-`$9BFF` | Background map; only the visible 20x18 cells are written |
| `$C000`-`$C007` | `vars`: `Cursor`, `Previous` and `Pressed` buttons, `Pending` title row, `BankDone`, `ShownCursor`, `ShownKey`, `ShownIndex` |
| `$DFFE` | Stack pointer |

Interrupts stay disabled; frame sync polls `LY`. The joypad rows are
deselected (`PROFILE_JOYP_SELECT`) after each read.

## Frame layout

The visible frame is 20 by 18 background cells, identity palette, no scroll,
no window or objects. Shade 0 is the page, shade 3 the ink.

| Row | Columns | Content |
|---|---|---|
| 0 | 4..15 | `GAME LIBRARY` |
| 1..16 | 0 | Cursor arrow on the selected slot's row, blank elsewhere |
| 1..16 | 1..2 | Slot number `00`..`15` |
| 1..16 | 4..19 | The 16 title bytes of a valid entry; blank for any other entry |
| 17 | 0..19 | Status row |

Status row, from the status bytes each frame:

| Condition | Text |
|---|---|
| `$A000` bit 5 clear | `NOT READY` |
| `$A002` is `NONE` or `OK` | blank |
| `$A002` is `INVALID_SLOT` | `SLOT nn INVALID` |
| `$A002` is `CRC_MISMATCH` | `SLOT nn BAD CRC` |
| `$A002` is `NOT_READY` | `SLOT nn NOT READY` |
| any other `$A002` value | `SLOT nn ERROR` |

`nn` is `$A003` as two decimal digits, or `--` when `$A003` is not 0..16.
The row is padded with blanks to 20 cells.

Title bytes map to font tiles: `A`-`Z` to tiles 0..25, `0`-`9` to 26..35,
`-` to 36, zero and space to the blank tile 37; any other byte draws the
dash so a foreign title stays visible. The sixteenth title byte is header
`$0143`, the CGB flag when the title is 15 bytes long: `$80` and `$C0`
there draw the blank tile, and any other value follows the same rule as the
other cells. Those two values in cells 1..15 still draw the dash. Tile 38 is
the cursor arrow.

### Font

![Menu font tiles 0..38](images/font-tiles.svg)

The [font atlas](../../../../src/sw/menu/assets/font-tiles.json) is one row
of 39 8x8 tiles: the approved
[core font](../springtrail/CORE_ART.md#effects-icons-and-text) glyphs `A`-`Z`,
`0`-`9` and dash (core tiles 56..92, copied because assets stay inside their
target tree), an all-zero blank and an original right-pointing arrow. The
[reference test](../../../../src/dv/menu/test_menu_reference.py) requires the
copied glyphs to equal their core sources. Reproduce the sheet from the
worktree root with
`python -m tools.sw.preview src/sw/menu/assets/font-tiles.json --tag <tag> --frame-width 8 --frame-height 8 --scale 8`;
the checkerboard is the review tool's transparency convention, not menu pixels.

## Verification

The Verilator matrix below is the preliminary evidence. The board criterion
is proven by the [game library sessions](../../board-bring-up.md#game-library-sessions):
after a host library load the menu frame, the cursor frames after a
host-injected joypad Down (`host input`), and the menu frame after the return
from a started game were read back with `SNAPSHOT`/`READ_FRAME` and matched
`reference.py` pixel for pixel, and a host-injected A started the selected
slot; the board has no physical joypad. The owner's physical KEY1 hold returned
from a running game to a pixel-exact menu frame; the host return exercised the
same swap.

`python tools/build.py sw build menu --tag <tag> --json` builds the image;
its result records `profile: dmg-loader-v1` and `profile_id: 2`.

[`reference.py`](../../../../src/dv/menu/reference.py) composes the expected
frame from this page's layout rules and the font's shade JSON, never from
the ROM or the DUT. `frame(entries, cursor=0, result=0, index=255, sdram_ready=True)`
returns the 23040 row-major shades for a catalogue given as
[`unpack_entry`](../../../../tools/n2m/host/library.py) rows (`valid` and 16
`title` bytes per slot). `check_pixels(packed, entries, **state)` compares a
`host snapshot` frame (5760 packed bytes) pixel for pixel and raises
`MENU_PIXEL x= y= expected= actual=` at the first difference;
`expected('menu', entries)` and `expected('cursor-N', entries)` name the
fresh menu and a moved cursor. The board session reads the stored catalogue
with `host library status` and passes its rows.

[`fixture.py`](../../../../src/dv/menu/fixture.py) is the registered `menu`
preload builder: it builds the image and the
[`exit-demo`](../../../../src/sw/exit-demo/main.asm) game, lays out a library
with the built `EXIT DEMO` image in slot 1 (a solid bar on map row 8; Start
writes the game exit register), stub games in slots 0, 2, 7, 8, 9, 10 and
15 (slot 10 carries the CGB flag `$80` and slot 8 the CGB-only flag `$C0` in
header `$0143`), a 64 KiB MBC1 stub game in slots 5-6 whose bank 2 returns
through the game exit register, an empty slot 3, a valid entry with a
foreign length in slot 4 and the menu at 16, and writes `menu-library.hex`
and `menu-frames.hex` (the scripted menu frames, then the exit-demo game
frame) for the testbench. [`tb_menu_system`](../../../../src/dv/menu/tb_menu_system.sv)
runs the real `n2m_v05_system` with the SDRAM controller and device model,
swaps the menu in through the host return, selects the board joypad and
compares every captured display-eligible frame; the
[test plan](../../../../src/dv/menu/README.md) maps checks to targets.

| Target | Proves |
|---|---|
| `menu-frame` | The boot frame equals the reference for the fixture library; Down, Down, Up move the cursor with a pixel-exact frame after each press; Up at slot 0 and a repeated Up at slot 0 change nothing (each step is one sampled press; a hold across frames is not simulated) |
| `menu-select` | Down then A commits 1 to the select register; the game boots in `DIRECT_ID` with epoch + 1 and `LIBRARY_STATUS` result `OK` index 1 |
| `menu-select-mbc1` | Five Downs reach the 64 KiB entry listed once at slot 5 (pixel-exact frame, slot 6 blank); A commits 5 and the game boots in `MBC1_ID` with epoch + 1 and result `OK` index 5; its bank 2 code returns to the menu through the game exit register (epoch + 2, index still 5, the menu running in `LOADER_ID`) |
| `menu-exit` | Down then A starts the built `exit-demo` image in slot 1 with a pixel-exact bar frame; Start makes it write `$10` to `$6000` and the menu returns by itself: `LOADER_ID`, epoch + 2, result `OK` index 1, running without a host `RUN`, the boot frame pixel-exact again |
| `menu-refused` | A on the empty slot 3 is refused: `LIBRARY_STATUS` reports `INVALID_SLOT` index 3 with `window_ready` still set and the frame shows `SLOT 03 INVALID`; Up keeps the message; A on slot 2 starts that game |
| `menu-frame-fault` | The frame comparison rejects a forced wrong source shade with the exact `MENU_PIXEL` diagnostic |
| `src/dv/menu/test_menu_reference.py` | Font provenance, glyph mapping, layout rows, status texts, fixture library bytes, snapshot unpacking and the negative pixel check |

Every target runs within the ordinary wall budget; `menu-select-mbc1` and
`menu-exit` carry the `mbc1`/`system` and `system` labels so the `menu`
label aggregate stays inside it.
