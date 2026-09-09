# HUD and prepared columns

This contract freezes the implementation and verification scope of
[#300](https://github.com/amichai-bd/nand2mario/issues/300). Implementation is pending.
The [alignment owner](sml1-alignment.md) defines the staged release.

## Coordinates and artwork

The visible picture is 160 by 144 pixels. Rows0..15 are a stationary background
HUD; rows16..143 are the 160 by128 playfield. Preserve the original96 by18
collision world and every movement constant. Playfield x is world x minus the
full-width Camera; screen y equals world y. Thus display columns contain world
tile rows2..17. The hidden first two world rows remain collision data, and the
existing ground stays at screen y128. No vertical camera or scaling is added.

Keep courier anchors, approved poses, palettes and horizontal clipping from
[composition](COMPOSITION.md). Disable objects during HUD scanlines and enable
them after line15 has completed. Pieces crossing the HUD boundary therefore
retain their correct lower pixels; hiding whole overlapping pieces is incorrect.
Remove score/mode entries from OAM. The shared160-byte publisher and inactive
tail clearing remain unchanged.

Reuse the existing terrain and approved courier pixels. The HUD uses approved
core glyphs for the existing score0..4 and TITLE/PLAY/RETRY/PAUSED/WON states;
it introduces no life or timer value. Exact glyph sources are the named
`glyph-*` maps in [core-maps.json](../../../../src/sw/springtrail/assets/core/core-maps.json)
and [core-tiles.json](../../../../src/sw/springtrail/assets/core/core-tiles.json).
Existing terrain remains [tiles.json](../../../../src/sw/springtrail/tiles.json).
Keep shade0..3 and E4 palettes. Allocate only selected glyph tiles after the
existing74 tiles, with explicit build bounds. A generated tile sheet and
assembled HUD/world SVG must link here and in the issue before final acceptance.
Unchanged artwork needs no renewed approval; any changed pixels do.

## Original encoding and publication

Keep the literal collision world as its existing owner. Encode each display
column independently, in top-to-bottom order, using original count/tile pairs.
Count1..16 repeats the following tile that many rows; count0 ends the column.
Exactly16 rows must precede the terminator. Blank runs use tile0. There are
at most16 pairs and33 bytes per column, and96 explicitly indexed columns.
The build rejects truncation, missing/early terminators, trailing bytes, invalid
counts, overflow, unallocated tile IDs, invalid column counts and indices.
Independent literal terrain rules must equal all1536 decoded cells.

Decode into a16-byte WRAM cache during scene preparation. VBlank publishes
that completed cache; it does not decompress content. The destination is
map row2 through17, column(worldColumn AND31). At most one entering column is
needed per ordinary update because horizontal speed is at most2 pixels.
Moving right publishes floor(Camera/8)+20; moving left publishes floor(Camera/8).
No-change tile position publishes none. Reject world columns outside0..95;
the camera remains within its unchanged0..608 range. SCX uses Camera modulo256.

Preserve restart restoration: static9800 contains the initial world and HUD,
9C00 is the scrolling map with the same HUD. A published restart selects9800
and resets camera/history/restoration. Prepare and publish two initial columns
per update until all32 columns of9C00 are restored. Switch only after final
VRAM writes. At16 moving updates player x is at most56, before camera movement.
Pause may continue restoration while world state remains paused. Repeated
restart discards partial preparation and restarts the restoration counter.
Streaming never modifies the static initial-world rows.

## Frame and interrupt ownership

Preserve one JOYP sample and one UpdateGame per frame, and the approved one
additional displayed frame. The prepared OAM, HUD, column caches and camera
belong to one logical update and publish together in the following VBlank.
Title removal and restart map selection use the published transition.

Use real VBlank and LYC interrupts: IE3, STAT40, LYC15. Clear IF during setup;
do not clear pending STAT as a side effect of the main frame wait. VBlank resets
SCX/SCY to0, disables objects for the HUD, and signals one main-loop publication.
Main samples inputs and publishes only in VBlank, then computes the next update
during visible time. The STAT handler saves every register it modifies, waits
for line15 HBlank, writes the published SCX (SCY remains0), and enables objects
before line16. It must not read the next update's mutable Camera.

The [qualified diagnostic](../../../../src/dv/display308/README.md) establishes
the line15 request projection and readable HBlank behavior. Its HALT-entry bound
is not automatically the game bound: include completion of the interrupted
instruction and the actual handler in the new static count and trace check.
Check line15 completes before scroll/object-enable writes, and both commits
precede line16 mode2. All publication must finish within4560 VBlank dots;
preparation must finish before the next VBlank. Freeze assembled instruction
counts before simulation. Keep LCDC unsigned tiles, selected map,8x8 objects
and no window; alter individual bits rather than copying a reference byte.

Pinned external research is [bank0.asm](https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/bank0.asm)
at618d00ed6c330928e106719533c6e294ae5d5726: LoadNextColumn prepares a16-row
cache, DrawColumn publishes into a wrapping map, and VBlank/LCDStatus separate
HUD scroll. These establish organization only. The encoding, maps, code and
pixels here are original; uncertain annotations supply no timing oracle.

## Remaining acceptance

- Validate encoding bounds and every decoded column against independent terrain;
  build malformed/truncated/overflow/unallocated-tile negatives.
- Shared actual CPU routine cases cover blanks/repeats, first/last columns,
  left/right boundaries,31-to0 ring wrap, restart/pause and complete cache writes.
- Freeze actual combined publication/ISR/preparation bounds and ROM sections;
  retain unchanged collision/movement/publisher qualification.
- Complete a short Intel-preloaded harness including final HALT, settled hold,
  END and watchdog, then bounded composed pixels for HUD, entering columns,
  wrap and sprite/HUD crossing. Use fixed expectations and a real downstream
  split/column fault with the same checker. No replacement of full pixels by CRC.
- Reconcile changed startup/image expectations and reject historical consumers;
  exact asset packaging, linked previews, required checks and current-head review.

Target120 seconds per simulation and300 seconds ordinary aggregate; each run
has a300-second whole-process hard bound. Freeze exact cases and forecasts
before launch and use measured short cost. No full baseline replay, new framework,
RTL change, banking or hardware run is implied.
