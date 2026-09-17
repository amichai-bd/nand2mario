# Menu design directions

Three proposals for the console-style game picker of
[issue #767](https://github.com/amichai-bd/nand2mario/issues/767). None is
implemented: the [menu contract](SPEC.md) still owns the frame the
[menu image](../../../../src/sw/menu/main.asm) draws and
[`reference.py`](../../../../src/dv/menu/reference.py) still checks. The owner
picks one direction; implementing it is separate work.

Each direction reuses the 39 approved font tiles and adds original 8x8 art of
its own. The screens below are the same three states for every direction: the
fresh list with the cursor on slot 2, the next animation phase, and a refused
selection on empty slot 13. The sample library is our own images and empty
slots, not a real catalogue read.

Reproduce every sheet from the worktree root:

```text
python -m tools.sw.menu_art --tag menu-design
```

The [preview contract](../../../tools/sw/SPEC.md#menu-design-previews) owns the
command; the shade JSON under `src/sw/menu/assets/design/` owns the new pixels.

## A. Plated list

![Direction A screens](previews/a-plated-list-screens.svg)

![Direction A new art](previews/a-plated-list-new-art.svg)

The header and status rows become solid plates with rounded caps, and the
selected slot is a full-width inverse bar. The layout keeps all sixteen slots,
their numbers and the sixteen title cells exactly where they are today, so only
the shades change. The animation is a one-pixel nudge of the cursor arrow inside
the bar.

- Tiles: 82 of the 256 in the `$8000` block. 43 added: the 39 font glyphs
  inverted, two plate caps and the nudged arrow with its inverse.
- Bytes: 688 of tile data plus about 140 bytes of code, on top of the image's
  current 1380 bytes. ROM0 has 14492 bytes free, so this is about 6% of the
  headroom.
- Per frame: a cursor move rewrites both affected rows, 40 cells at about
  10 cycles each, so about 545 M-cycles of the 1140 in VBlank (48%). An
  animation phase costs one cell. Today's peak, a twenty-cell status redraw, is
  already about 48%, so the peak does not grow.
- Reference: [`tilemap`](../../../../src/dv/menu/reference.py) gains a `phase`
  argument, builds the inverse bank as `3 - shade` from the same font JSON, and
  adds 39 to every tile of the cursor row. `expected` gains `phase-N` names.

## B. Cartridge shelf

![Direction B screens](previews/b-cartridge-shelf-screens.svg)

![Direction B new art](previews/b-cartridge-shelf-new-art.svg)

A two-row cartridge emblem heads the screen, the list sits in a drawn box, and a
hint bar names the selected slot. Each row carries a filled or hollow cartridge
icon for a loadable or empty slot, and blinking chevrons mark the selection. The
box shows twelve slots at a time with scroll markers, so the slot number moves
from the row to the hint bar.

- Tiles: 60. 21 added: eight emblem tiles, eight box pieces, two cartridge
  icons, two scroll markers and one chevron pair.
- Bytes: 336 of tile data plus about 320 bytes of code for the window top,
  staged redraw and hint bar; about 4% of the free ROM0.
- Per frame: a cursor move inside the window costs four cells, about 170
  M-cycles (15%). A scroll step is the cost: twelve rows of sixteen title cells
  re-read through the banked window, about 4300 M-cycles, nearly four VBlanks.
  It must be staged at two or three rows per frame, so the list visibly rebuilds
  for about 0.1 s per step. A 256-byte WRAM shadow of the titles halves that and
  still needs two frames.
- Reference: `tilemap` gains `phase` and derives the window top from the cursor
  (`min(max(cursor - 6, 0), 4)`). The staged redraw needs a `drawn_rows`
  argument of the same shape as today's `drawn_slots`, and the test has to model
  the staging schedule frame by frame. This is the largest reference change.

## C. Night deck

![Direction C screens](previews/c-night-deck-screens.svg)

![Direction C new art](previews/c-night-deck-new-art.svg)

The whole screen inverts through BGP `$1B` instead of `$E4`: white text on a
black page, with no extra tiles for the theme. The selection is a four-phase
caret that slides one pixel at a time plus brackets around the title, a power
dot in the corner pulses, and the status row becomes a rule when there is
nothing to report. The grid is today's grid.

- Tiles: 49. 10 added: four caret phases, two brackets, three dot states and a
  rule.
- Bytes: 160 of tile data plus about 120 bytes of code; about 2% of the free
  ROM0. The cheapest direction.
- Per frame: a cursor move costs four cells, about 160 M-cycles (14%), and a
  phase frame two cells. The peak stays the existing status redraw, about 48%.
- Reference: `tilemap` gains `phase`, picks caret `(phase >> 3) & 3` and dot
  `(phase >> 4) % 3`, and draws the rule row when the status text is blank. The
  palette is applied once, so `frame` gains the BGP mapping the other
  directions do not need.

## Keeping every frame checkable

All three directions animate from one WRAM byte incremented once per frame loop
iteration. The loop already runs exactly once per frame from the `LY == 144`
poll, so that byte is the frame index modulo 256 and the reference can compute
any phase from the frame number alone, with no DUT state. Whichever direction
wins, the phase divisor belongs in [SPEC](SPEC.md) beside the layout table so
the image and the reference read the same constant.
