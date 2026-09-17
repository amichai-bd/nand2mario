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

1. Load the 98-tile bank into VRAM `$8000`: the 39 font tiles, the same 39 on
   a mid-grey page, the six authored grey cells, the two pointer phases, the
   eight boot splash badge cells and the four star cells. Clear the object
   table, blank the background map at `$9800`, paint the
   [star field](#star-field) over it, set OBP0 to `$E4` and draw the
   [boot splash](#background-map), the header plate and the six status rows
   in WRAM. Blank the window map at `$9C00`, build the
   [bottom plate](#window) into it and set WX and WY; the window itself stays
   off until the list settles.
2. Read `$A000` bit 5 (`sdram_ready`) and `$A003` (the last selected index)
   once each. The status bit alone decides whether the titles are drawn at
   boot. Both together arm the [boot splash](#boot-splash): it needs the
   catalogue listed at boot, and it needs `$A003` to be `$FF`, which the
   loader leaves it only until the first selection since reset.
   - Armed, so this is the first boot and the catalogue lists: the splash
     runs. BGP starts on the first fade step and SCY at 0. Boot draws the slot
     numbers and titles of slots 0..12 only; the last three slot rows and the
     page row below them wrap over the splash and are built instead as four
     finished 20-cell rows in WRAM, with the LCD off, for the slide to copy.
     The cursor object stays off screen and the window stays off, so the
     splash shows neither the cursor nor the plate. The rows drawn here and
     the rows the slide draws account for all sixteen.
   - Not armed: no splash. BGP is `$E4` and SCY the settled 144, the window is
     on with its plate and the cursor object goes on slot 0. A menu that has been
     here before still lists every title at boot, so the list is whole in its
     first frame; a menu waiting for the SDRAM skips the catalogue and the
     frame loop retries it below.
3. With the catalogue available, commit bank 34 (the catalogue,
   `LIBRARY_CATALOGUE_ADDRESS / LIBRARY_WINDOW_BYTES`) to the bank register,
   wait for bit 6 (`window_ready`) and draw the title rows from the window.
   Every title is read here, so a select is live as soon as the list is.
4. Turn the LCD on: `LCDC = $93`, background and objects, while the splash
   runs, and `$F3` once the list is settled, which adds the window and names
   the second map.

Every frame, at the start of VBlank (`LY == 144`) and finishing inside it:

1. Read both JOYP rows, settling at least 24 dots after each row select, and
   keep the released-to-pressed edges in the generated `BUTTON_*` bit order.
   A held button acts once.
2. While the [boot splash](#boot-splash) runs it owns the frame and the steps
   below wait: no navigation, no catalogue row and no status redraw, so the
   press that skips the splash never reaches the list.
3. A Down edge moves the cursor one slot down, then an Up edge one slot up,
   clamped to slots 0..15; no wrap.
4. An A edge, once all sixteen title rows are listed, writes the cursor's
   slot index to the select register and polls `$A000` bit 7 until the
   loader is idle. An accepted select swaps the image and resets the core;
   the menu never resumes. A refused select leaves its result in `$A002` and
   the index in `$A003`. Before the catalogue is listed, A does nothing.
5. Delayed catalogue path: when bank 34 has not been committed and
   `sdram_ready` is now set, commit it; when it has been committed and
   `window_ready` is set, draw one remaining title row per frame. Every row
   is drawn the same way, because the cursor is an object and never re-banks
   a row.
6. Move the cursor object only when the cursor changed, redraw the status
   row only when its key or index changed, and when the nudge phase changed
   rewrite the object's tile and the [star field](#star-field)'s own cells.
   An idle frame writes nothing.

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
| `$0200`-`$0897` | `code` section: entry `Start`, frame loop, boot splash schedule, star field, drawing routines and text tables (1688 bytes) |
| `$0C00`-`$0FAF` | `assets` section: the 39 font tiles from `ASSET "Font"`, the six grey cells from `ASSET "GreyArt"`, the two pointer phases from `ASSET "Pointer"`, the eight badge cells from `ASSET "Splash"` and the four star cells from `ASSET "Stars"`, 944 bytes |
| `$4000`-`$7FFF` | The banked window; the image keeps the upper half `$FF` because the hardware maps SDRAM there. The linker refuses ROM1 sections in this profile |
| `$2000`-`$3FFF` write | Bank register: the menu writes 34 once per boot |
| `$6000`-`$7FFF` write | Select register: the cursor's slot on an A edge |
| `$A000`, `$A002`, `$A003` | Status byte, last result, last selected index |
| `$8000`-`$861F` | The 98-tile bank: font 0..38, the font on the grey page 39..77, grey caps 78 and 79, the gradient cells 80..83, pointer phases 84 and 85, the badge 86..93, the star cells 94..97 |
| `$9800`-`$9BFF` | [Background map](#background-map), all 32 rows: the boot splash above the list |
| `$9C00`-`$9FFF` | [Window map](#window): blank but for the plate's two rows |
| `$FE00`-`$FE9F` | Object table; cleared at boot, then object 0 alone is the cursor |
| `$C000`-`$C0FE` | `vars`, 255 bytes: `Cursor`, `Previous` and `Pressed` buttons, `Pending` title row, `BankDone`, `ShownCursor`, `ShownKey`, `ShownIndex`, `FrameCount`, `ShownPhase`, the splash's `SplashOn`, `SplashNumber`, `SplashRows`, `SplashSkip`, `BootSlots` and `BootDraw`, the star field's `StarCount`, `StarPtr` and `StarTable`, `SplashRowCells`, the four 20-cell wrapped rows built at boot, and `StatusCells`, the six 18-cell status rows |
| `$DFFE` | Stack pointer |

Interrupts stay disabled; frame sync polls `LY`. The joypad rows are
deselected (`PROFILE_JOYP_SELECT`) after each read.

## Frame layout

The frame is three layers, as the
[composite layout](DESIGN_V2.md#composite-layout) decided them.

| Layer | Carries | Registers |
|---|---|---|
| Background | The header row, the sixteen slot rows and the [star field](#star-field), in the 32-row map | SCY for the splash slide; SCX unused |
| [Window](#window) | The bottom plate alone | LCDC bits 5 and 6, WX 7, WY 128 |
| Objects | The [cursor pointer](#cursor-object), one entry | LCDC bit 1, OBP0 |

No frame writes a scroll register mid-frame, so interrupts stay disabled and
the frame loop keeps polling `LY`.

### Background map

The map at `$9800` is 32 rows of 32 cells and carries the boot splash above
the list. The splash fills map rows 0..17, the 18 rows the screen shows at
SCY 0; the list's own 18 rows start at map row 18, so its last four rows wrap
into map rows 0..3, over the splash's own top rows, which the splash leaves
blank. The list's last row is the page: the bottom plate rides the
[window](#window) and the row it used to fill is behind the plate whenever the
list is settled. The slot rows carry the [star field](#star-field) in the two
columns they always leave blank. The settled view is SCY 144: the screen then shows map rows 18..31 and
0..3, which are the list alone, and nothing of the splash is on screen. Only
map columns 0..19 are written.

The splash is the badge and its two lines, from the
[approved sheet](../../../../src/sw/menu/assets/design/v2-splash-tiles.json):

| Map row | Columns | Content |
|---|---|---|
| 4 and 5 | 8..11 | The badge, bank tiles 86..89 over 90..93 |
| 8 | 4..15 | `GAME LIBRARY` |
| 10 | 3..15 | `SELECT A GAME` |

Every other splash cell is the blank tile. The badge and both lines are drawn
once, with the LCD off at boot.

### Boot splash

The splash runs on the first menu boot after a reset, when the catalogue is
available at boot. A return from a game re-boots this image, so the menu
decides again, and `$A003` is what tells the two apart: the loader keeps the
last selected index across the return, and leaves it `$FF` only until the
first selection. So the splash plays once, at power-up or after a host reset,
and a return from a game shows the settled list in its first frame, pixel
for pixel what it showed before. Any reboot after a selection starts settled
the same way, including one after a select the loader refused, because a
refused select writes `$A003` too.

The splash fades the page in through BGP
and then slides the list up through SCY, and the frame counter
alone decides every write, as it does the nudge phase. The schedule is four
constants, held here, in the [image](../../../../src/sw/menu/main.asm) and in
[`reference.py`](../../../../src/dv/menu/reference.py), which read the same
values: the fade `$00`, `$40`, `$90`, `$E4`, `FADE_HOLD` 2 frames a step,
`SLIDE_STEP` 16 and `SKIP_ROWS` 2. That makes 8 fade frames, 9 slide frames
and 17 displayed frames in all.

| Displayed frame | BGP | SCY | Wrapped rows drawn |
|---|---|---|---|
| 0, 1 | `$00` | 0 | 0 |
| 2, 3 | `$40` | 0 | 0 |
| 4, 5 | `$90` | 0 | 0 |
| 6, 7 | `$E4` | 0 | 0 |
| 8 | `$E4` | 16 | 1 |
| 9 | `$E4` | 32 | 2 |
| 10 | `$E4` | 48 | 3 |
| 11 | `$E4` | 64 | 4 |
| 12..15 | `$E4` | 80, 96, 112, 128 | 4 |
| 16 | `$E4` | 144 | 4 |

A slide frame draws the wrapped row its step first counts, after that row's
splash cells have left the top of the screen and before the list row it
carries reaches the bottom. The row is a flat copy of the twenty cells built
at boot, not the text path.

Any button skips. The edge latches; from then on each frame draws at most
`SKIP_ROWS` wrapped rows and takes the schedule's own number for the rows
drawn so far, ending on the settled frame. So a skip is two frames, each of
them a frame of the same schedule, and no VBlank carries more than half the
map. The edge is consumed by the splash and a held button raises no further
edge, so the list never acts on it and a skip cannot move the cursor or
select a game.

Frame 16 is the settled frame: SCY is 144, the list is whole, and the
[window](#window) and the cursor object come on together, which is when the
bottom plate first appears. It is also the
menu's own frame 0, because the frame counter and the shown nudge phase are
reset there, so the [nudge phase](#cursor-object) still follows from the menu
frame number alone whether the splash ran, was skipped, or never ran at all.

### The list

The visible frame is 20 by 18 cells and one object, identity palette
throughout: sixteen background rows, the window's two and the pointer. Shade 0
is the page, shade 3 the
ink and shade 2 the plates. The header and bottom rows are mid-grey plates: a
dithered gradient fill with a rounded grey cap in each outer column, carrying
text on the grey page, where the font's shade 0 becomes 2 and its ink stays 3.
The selection is the [cursor object](#cursor-object), not a map cell, so the
list itself is the same cells whatever the cursor does.

| Row | Layer | Columns | Content |
|---|---|---|---|
| 0 | Background | 0 and 19 | Left and right grey plate cap |
| 0 | Background | 1..18 | Header plate, the 3-to-2 gradient cell; `GAME LIBRARY` on the grey page at columns 4..15 |
| 1..16 | Background | 0 and 3 | The page or a [star](#star-field); column 0 is also where the cursor object draws |
| 1..16 | Background | 1..2 | Slot number `00`..`15` |
| 1..16 | Background | 4..19 | The 16 title bytes of a valid entry; blank for any other entry |
| 16 and 17 | [Window](#window) | 0 and 19 | Left and right grey plate cap |
| 16 | Window | 1..18 | The plate's own 2-to-1 gradient fill |
| 17 | Window | 1..18 | Bottom plate, the 2-to-1 gradient cell; the status text on the grey page, centred |

The window covers screen rows 16 and 17 whenever the list is settled, so the
background shows the header and fifteen slot rows and slot 15's own row is
behind the plate. The cursor still visits every slot 0..15, and on slot 15 the
pointer draws over the plate's upper row with no title beside it. The
[composite layout](DESIGN_V2.md#slot-count) owns that: the smooth scroll of
[issue #793](https://github.com/amichai-bd/nand2mario/issues/793) is what
brings the sixteenth row back into view.

The status text is unchanged; it is centred in the plate's 18 cells with the
leftover space biased left, so `SLOT 03 INVALID` starts at column 2 and
`SLOT 03 NOT READY` fills columns 1..17. Every cell the text does not reach
keeps the plate's gradient fill, and an empty message leaves the whole plate
filled. The image builds the six possible rows as tiles once, while the LCD is
off, so a redraw copies 18 bytes instead of walking the text path.

The six authored grey cells are the
[two caps, three gradient fades and a plate shadow](../../../../src/sw/menu/assets/design/v2-grey-tiles.json);
the frame uses the caps, the 3-to-2 fade on the header and the 2-to-1 fade on
the bottom plate. The 1-to-0 fade and the shadow are loaded with them and are
drawn by no cell today. The 39 grey glyphs are derived at boot rather than
stored: the font uses only shade 0 and shade 3, so the grey copy is the font's
low plane with the high plane set.

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
The text is centred in the plate's 18 cells as above; an empty one leaves the
plate's fill.

### Star field

The two columns the list always leaves blank carry a star field: column 0, the
page the cursor object draws on, and column 3, between the slot number and the
title. DMG has one background layer and the
[composite layout](DESIGN_V2.md#what-each-idea-does-under-this-decision) spends
it on the list, so the stars are cells of the list's own map rather than a band
of their own: they wrap with its 32 rows and ride its SCY, and there is no SCX
drift. No title cell is ever a star, so the field does not depend on the
catalogue and the slot-row draw path never evaluates the rule.

A map cell at column `x` of map row `y` carries a star when

```text
((3 * x + 5 * y) xor (y >> 2)) and 3 == 0
```

and only on the sixteen slot rows, map rows 19..31 and 0..2. That names eight
cells, all of them on screen when the list is settled. The rule is incremental
by design: a step along a row adds 3 and a step down a column adds 5, so the
image carries the sum instead of multiplying, and the exclusive-or of the row's
own high bits breaks the lattice the plain sum would draw.

A star's cell is star tile `(x + y + phase) mod 4` of the four, where `phase`
is the [nudge phase](#cursor-object): the same frame-counter bit that nudges
the cursor. The field therefore twinkles once every 16 frames, follows from the
frame number alone, and changes in the same frame as the pointer. The image
keeps the cells it painted in a short table, so a twinkle rewrites eight cells
rather than walking the map.

### Window

The window carries the bottom plate alone. It is opaque from its top left
corner to the bottom right of the screen, so it cannot be a band: at WX 7 and
WY 128 it takes the last two screen rows and nothing else. Its map is the
second one, `$9C00`, which LCDC bit 6 selects while bit 5 turns the window on;
the background keeps `$9800`. The map is blanked and the plate built into it
with the LCD off, and the window comes on with the cursor, on the settled
frame, so the splash shows neither.

The plate's lower row is the status row and its upper row is the plate's own
fill, the two rows the information footer of
[idea 3](DESIGN_V2.md#3-info-footer) will use. The window draws through BGP,
like the background.

### Cursor object

The cursor is object 0 and the only object the menu uses. Its X is `8`, the
screen's left edge, and its Y is `24 + 8 * slot`, so it sits in column 0 of
the selected slot's row. Its flags are zero: no flip, palette OBP0, and no
background priority, so it draws in front wherever its shade is not 0. Shade 0
is transparent, which is why the pointer's page shows through. One object
never meets the ten-objects-a-line limit, and the rest of the object table is
cleared at boot so nothing else is on screen. A cursor move writes the Y byte
alone and touches no map cell.

A frame counter byte advances once per frame
loop iteration, after that iteration's writes, and bit 4 of it is the nudge
phase: on phase 1 the object's tile is the second pointer, the same arrow one
pixel to the right, so the cursor ticks every 16 frames. The same bit twinkles
the [star field](#star-field), so the page and the pointer change together. The loop runs exactly once
per displayed frame and an iteration's writes appear in the frame its counter
names, so the phase follows from the frame number alone with no console
state: displayed frame `m`, counted from the menu's first display-eligible
frame, carries phase bit 4 of `m`, which
[`reference.phase_of_frame`](../../../../src/dv/menu/reference.py) computes.

### Frame budget

VBlank is ten lines of 456 dots, 1140 M-cycles, and every frame body finishes
inside it. [`tb_menu_system`](../../../../src/dv/menu/tb_menu_system.sv)
measures each body from the `RET` that leaves the `LY == 144` poll to the next
call into it, prints it as `MENU_COST` and fails with `MENU_VBLANK_OVERRUN`
above the budget, so the figures below are measured, not counted. An image
swap resets the core and its dot counter, so the first frame after a return is
measured from the new epoch's first poll rather than across the swap.

| Frame | M-cycles | Share of VBlank |
|---|---|---|
| Idle | 238 | 21% |
| Cursor move or a sampled press, one object byte | 245-262 | 21-23% |
| Nudge phase change: one object byte and the eight star cells | 432 | 38% |
| Boot splash fade frame, one BGP write | 166-196 | 15-17% |
| Boot splash slide frame drawing one wrapped row | 361-376 | 32-33% |
| Boot splash slide frame after the map is whole | 199-260 | 17-23% |
| Skipped splash frame, two wrapped rows | 599-663 | 53-58% |
| Refused select with a 20-character status redraw | 555 | 49% |

The list rows come from `menu-frame`, the nudge from `menu-phase`, the refused
select from `menu-refused` and the splash rows from `menu-splash` and
`menu-frame-fault`, each measured on the image this page specifies. The first
list frame is no longer a class of its own: the bottom plate is built into the
window map with the LCD off, so that frame writes nothing and measures the idle
238 rather than the 483 a status redraw used to add.

A skipped splash frame is the peak, 663, 477 M-cycles inside the budget, and
the idle frame is the floor at 238. The peak is `menu-frame-fault`'s own
second frame: its skip settles the list, which is the frame that turns the
window on, so it carries the LCDC write too. The cap on the skip is what holds that
margin: a skip that finished the map in one VBlank cost 1342 and overran, and
1010 with the rows prebuilt as cells. Two
things keep the ordinary splash cheap: the four wrapped rows are built as
cells with the LCD off, so a slide frame copies twenty bytes instead of
walking the text path, and no frame draws more than two of them. The cursor
object pulled the list's own peak down the same way: a move used to rewrite
two rows of 19 map cells for 722 M-cycles, and it now writes one byte.

The delayed catalogue path draws one title row per frame and the matrix below
never reaches it, because the fixture's SDRAM is ready before the menu boots.
Every row is drawn the same way now that no row is re-banked under a bar; the
counted worst case, sixteen letter cells, is about 1080 of the 1140. The
overrun check bounds it wherever it does run, and
[issue #777](https://github.com/amichai-bd/nand2mario/issues/777) tracks
measuring it.

Title bytes map to font tiles: `A`-`Z` to tiles 0..25, `0`-`9` to 26..35,
`-` to 36, zero and space to the blank tile 37; any other byte draws the
dash so a foreign title stays visible. The sixteenth title byte is header
`$0143`, the CGB flag when the title is 15 bytes long: `$80` and `$C0`
there draw the blank tile, and any other value follows the same rule as the
other cells. Those two values in cells 1..15 still draw the dash. Tile 38 is
the font's arrow, which the object cursor replaced; no cell names it.

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

### Plate and pointer art

![Mid-grey plate cells](previews/v2/5-grey-plates-new-art.svg)

![Cursor pointer phases](previews/v2/2-sprite-cursor-new-art.svg)

The twelve authored tiles are the
[six grey plate cells](../../../../src/sw/menu/assets/design/v2-grey-tiles.json),
the
[two pointer phases](../../../../src/sw/menu/assets/design/v2-cursor-tiles.json)
and the
[four star cells](../../../../src/sw/menu/assets/design/v2-stars-tiles.json);
the 39 grey glyphs are derived from the font at boot rather than stored. The
owner chose the plated list in [design directions](DESIGN.md) and then the six
[menu v2 ideas](DESIGN_V2.md), whose composite layout owns how the remaining
ideas fit; this page owns every frame the image draws.

## Verification

The Verilator matrix below is the preliminary evidence. The
[game library sessions](../../board-bring-up.md#game-library-sessions) proved
the board path on the plated list: after a host library load the menu frame,
the cursor frames after a host-injected joypad Down (`host input`), and the
menu frame after the return from a started game were read back with
`SNAPSHOT`/`READ_FRAME` and matched `reference.py` pixel for pixel, and a
host-injected A started the selected slot; the board has no physical joypad.
The owner's physical KEY1 hold returned from a running game to a pixel-exact
menu frame; the host return exercised the same swap. Those frames are the
plated list, not the grey plates and cursor object this page now specifies;
[issue #794](https://github.com/amichai-bd/nand2mario/issues/794) tracks
reading the composite menu back from the board.

`python tools/build.py sw build menu --tag <tag> --json` builds the image;
its result records `profile: dmg-loader-v1` and `profile_id: 2`.

[`reference.py`](../../../../src/dv/menu/reference.py) composes the expected
frame from this page's layout rules and the font's shade JSON, never from
the ROM or the DUT, and builds the 98-tile bank from the font, the grey copy
of each glyph, the authored grey cells, the two pointer phases, the badge and
the four star cells. `frame`
draws the background, then the window over its last two rows when the list is
settled, then the cursor object, with shade 0 transparent.
`star_here` and `star_tile` are the [star field](#star-field)'s own rule, so
the field is reproduced rather than stored.
`frame(entries, cursor=0, phase=0, result=0, index=255, sdram_ready=True)`
returns the 23040 row-major shades for a catalogue given as
[`unpack_entry`](../../../../tools/n2m/host/library.py) rows (`valid` and 16
`title` bytes per slot). `check_pixels(packed, entries, **state)` compares a
`host snapshot` frame (5760 packed bytes) pixel for pixel and raises
`MENU_PIXEL x= y= expected= actual=` at the first difference;
`expected('menu', entries)`, `expected('cursor-N', entries)`,
`expected('phase-N', entries)` and `expected('splash-N', entries)` name the
fresh menu, a moved cursor, a nudge phase and a
[boot splash](#boot-splash) frame. `splash_state(number)` is the schedule
itself, the BGP, SCY and rows drawn of displayed frame `number`, and
`skip_schedule(number)` the frames a skip shows counted from displayed frame
`number`, the last frame whose draw has completed when the press is sampled.
`splash_at_boot(index, sdram_ready)` is the boot decision itself, which
`test_menu_reference.py` covers for the cold boot and the return. The board session reads the stored catalogue
with `host library status` and passes its rows.

[`fixture.py`](../../../../src/dv/menu/fixture.py) is the registered `menu`
preload builder: it builds the image and the
[`exit-demo`](../../../../src/sw/exit-demo/main.asm) game, lays out a library
with the built `EXIT DEMO` image in slot 1 (a solid bar on map row 8; Start
writes the game exit register), stub games in slots 0, 2, 7, 8, 9, 10 and
15 (slot 10 carries the CGB flag `$80` and slot 8 the CGB-only flag `$C0` in
header `$0143`), a 64 KiB MBC1 stub game in slots 5-6 whose bank 2 returns
through the game exit register, an empty slot 3, a valid entry with a
foreign length in slot 4 and the menu at 16, and writes `menu-library.hex`,
`menu-frames.hex` (the scripted menu frames, then the exit-demo game frame)
and `menu-splash.hex` (every displayed frame of the splash schedule, which
only the splash fixture reads) for the testbench. [`tb_menu_system`](../../../../src/dv/menu/tb_menu_system.sv)
runs the real `n2m_v05_system` with the SDRAM controller and device model,
swaps the menu in through the host return, selects the board joypad and
compares every captured display-eligible frame; the
[test plan](../../../../src/dv/menu/README.md) maps checks to targets.

| Target | Proves |
|---|---|
| `menu-frame` | The boot frame equals the reference for the fixture library; Down, Down, Up move the cursor with a pixel-exact frame after each press; Up at slot 0 and a repeated Up at slot 0 change nothing (each step is one sampled press; a hold across frames is not simulated) |
| `menu-select` | Down then A commits 1 to the select register; the game boots in `DIRECT_ID` with epoch + 1 and `LIBRARY_STATUS` result `OK` index 1 |
| `menu-select-mbc1` | Five Downs reach the 64 KiB entry listed once at slot 5 (pixel-exact frame, slot 6 blank); A commits 5 and the game boots in `MBC1_ID` with epoch + 1 and result `OK` index 5; its bank 2 code returns to the menu through the game exit register (epoch + 2, index still 5, the menu running in `LOADER_ID`) |
| `menu-exit` | Down then A starts the built `exit-demo` image in slot 1 with a pixel-exact bar frame; Start makes it write `$10` to `$6000` and the menu returns by itself: `LOADER_ID`, epoch + 2, result `OK` index 1, running without a host `RUN`, the boot frame pixel-exact again. The returned menu starts settled, with no splash, because `$A003` kept the slot |
| `menu-refused` | A on the empty slot 3 is refused: `LIBRARY_STATUS` reports `INVALID_SLOT` index 3 with `window_ready` still set and the frame shows `SLOT 03 INVALID`; Up keeps the message; A on slot 2 starts that game |
| `menu-phase` | The untouched menu animates by itself: displayed frame 15 still carries the plain arrow and the star field's first phase, frame 16 the nudged arrow and its second, both pixel-exact, which pins the phase boundary for the pointer and the [stars](#star-field) together. The return to phase 0 at frame 32 is not simulated: it costs sixteen more simulated frames and follows from the same bit-4 constant, which `test_menu_reference.py` covers |
| `menu-splash` | The untouched [boot splash](#boot-splash) runs its schedule: all 17 displayed frames match the reference frame by frame, fade then slide, and the last of them is pixel-identical to the menu's own frame 0. The nine slide frames are nine scroll offsets of the 32-row map, so they are also where the [star field](#star-field) is checked riding the list |
| `menu-frame-fault` | The frame comparison rejects a forced wrong source shade with the exact `MENU_PIXEL` diagnostic |
| `src/dv/menu/test_menu_reference.py` | Font provenance, glyph mapping, layout rows, status texts, fixture library bytes, snapshot unpacking and the negative pixel check |

Every target runs within the ordinary wall budget; `menu-select-mbc1`,
`menu-exit`, `menu-phase` and `menu-splash` carry the `mbc1`/`system` and
`system` labels so the `menu` label aggregate stays inside it. `menu-phase`
and `menu-splash` also carry `menu-animation`, a label of their own, so
either can be run alone without the `system` aggregate. `menu-splash` is the
longest single target here: it simulates 18 frames, which is why the fade
holds two frames a step rather than three. Every target also measures each
menu frame body against the [frame budget](#frame-budget); the fixtures other
than `menu-splash` hold A through the boot, which skips the splash and proves
the press is consumed, because an A the list saw would select slot 0.
