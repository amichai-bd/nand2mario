# Approved courier character art

Status: the user approved these original pixel designs on 2026-09-09. The
current [composer](COMPOSITION.md) consumes the shared tile bank and pose maps as
ordinary 8x8 Game Boy object pieces. Approval covers the depicted pixels, shared
tile bank and small 16x16 / large 16x24 pose geometry. These are original art
choices; they are not verified Super Mario Land 1 character dimensions.

## Tile bank and poses

The [editable tile bank](../../../../src/sw/springtrail/assets/courier/unique-tiles.json)
is the authoritative shade data. It is a 256x8 atlas containing 32 unique 8x8
tiles, indexed 0..31 from left to right. Each tile occupies 16 bytes in standard
Game Boy 2bpp form: two bytes per row, low plane then high plane, with the
leftmost pixel in bit 7. The bank encodes to 512 bytes; twelve separate poses
would use 960 bytes. Both sizes exclude pose tables and other game data.
Reuse is exact tile equality; no flip-based deduplication was applied.

![Shared numbered 8x8 tile bank](character-art/tile-bank.svg)

The [pose map](../../../../src/sw/springtrail/assets/courier/poses.json) groups
six named poses under each of `small` and `large`: `STAND`, `WALK1`, `WALK2`,
`WALK3`, `JUMP` and `RETRY`. A piece has `x` and `y` pixel offsets from its
pose's top-left, a zero-based `tile` index, and `x_flip` / `y_flip` flags.
All stored flags are false. Pieces are ordered by row then column, with four
pieces per small pose and six per large pose. Offsets describe artwork placement;
OAM anchors, facing, clipping and object limits are owned by the
[composition contract](COMPOSITION.md).

![Small 16x16 poses and their tile maps](character-art/small-tile-maps.svg)

![Large 16x24 poses and their tile maps](character-art/large-tile-maps.svg)

The tile-map sheets insert a one-pixel gutter between tiles for inspection.
Gutters, captions and tile numbers are not sprite data. Draw pieces directly
adjacent at their stored offsets. Numbers beneath each pose list its tile IDs
row by row. The renderer shows shade 0 as a transparency checkerboard;
shades 1, 2 and 3 use RGB (208,208,208), (104,104,104) and (24,24,24).
These preview RGB values do not assign an in-game object palette register.

## Reproduction and provenance

The original project art was authored as integer shade grids, then factored
into identical 8x8 tiles by a Python script and rendered with the repository's
[sprite preview tool](../../../tools/sw/SPEC.md). No commercial pixel data is
included. JSON files retain the exact editable source; SVGs are review views.

From the repository root, a fresh preview tag renders the tile bank:

```text
python -m tools.sw.preview src/sw/springtrail/assets/courier/unique-tiles.json --tag courier-bank-review --frame-width 8 --frame-height 8 --scale 8
```

The command writes to `workdir/builds/courier-bank-review/sprite-preview/`.
Its ordinary sheet layout differs from the grouped SVG above. To reconstruct
a pose, start a transparent 16x16 or 16x24 shade grid, extract columns
`8*tile` through `8*tile+7` from the bank, and place those eight rows at `(x,y)`
for each piece. Use the same preview tool on the resulting shade grid.
The SVG layout is explanatory; JSON owns pixel and placement values.

## Runtime composition boundary

The current SM83 composer reconstructs the approved poses from the shared bank
and emits ordinary 8x8 OAM entries. The [composition contract](COMPOSITION.md)
owns runtime tile allocation, anchors, whole-pose reflection, clipping and OAM
capacity. The [game specification](SPEC.md) owns which poses are selected by
current gameplay and which later movement/size transitions belong to staged
alignment work.

Artwork approval does not by itself define collision boxes, state transitions,
palette writes or timing. Those behaviors remain in their owning game and
verification contracts. Likewise, an SVG review view proves reproducible pixel
composition, not FPGA display or physical release acceptance.

The [approved core asset pack](CORE_ART.md) adds player actions, terrain, items,
enemies, platforms, effects, fonts and UI compositions. It retains separate
source, integration and verification boundaries.
