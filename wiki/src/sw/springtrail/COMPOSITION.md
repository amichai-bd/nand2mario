# Courier composition

Planned implementation for [#292](https://github.com/amichai-bd/nand2mario/issues/292).
The [approved art](CHARACTER_ART.md) owns all pixels and twelve pose maps.

## Coordinates and allocation

Keep the logical 8x16 collision box and all movement/input/update rules.
The original artwork is centered on that box: its left is floor(PlayerX/16)-4,
its feet are floor(PlayerY/16)+16. Small top is PlayerY; large top is PlayerY-8.
These are intentional original anchors, not claimed SML1 dimensions.
For camera subtraction use full signed pixel coordinates before OAM encoding.
Each 8x8 piece is visible only when -7 <= x < 160 and -7 <= y < 144;
partially visible pieces retain their coordinates. Entirely clipped/hidden pieces
use Y=0. Hardware handles the remaining partial pixel clipping.

Existing tiles 0..41 stay at VRAM8000..829F. The approved 32-tile courier bank
uses IDs42..73, VRAM82A0..849F (512 bytes). OBP0=E4 preserves shade ordering;
shade0 stays transparent. Tiles and map plus courier bank remain in the assets
ROM section0C00..13FF; composer tables/code use a separate ROM1 section after
collision, with linker overlap checks. Mapperless32768-byte profile is unchanged.

Pose order is STAND,WALK1,WALK2,WALK3,JUMP,RETRY for small, then large.
The composer supports all12 maps. Normal play uses small STAND when grounded
and still, small WALK1 when grounded and moving, JUMP when airborne, RETRY in
retry mode. Title uses STAND. Pause/WON use current grounded/motion pose.
There is no animation counter or size transition: #301 owns cadence and #302
owns power sizes. Facing follows the last nonzero horizontal velocity; initial
and restarted neutral state faces right. Whole-pose reflection maps x to8-x and
XORs the tile X-flip bit. Approved Y-flip flags are preserved.

Global LCDC object-size bit becomes0. Every old8x16 enemy, pickup, goal and HUD
entry becomes a vertical pair of adjacent tiles; their pixels/anchors stay the
same. Keep player, enemy, four pickups, goal, score, mode OAM priority order.
Player pieces are row-major. At most20 small/22 large entries are emitted;
remaining bytes of the160-byte shadow are zero. At most2 courier pieces and
one from each of8 other objects intersect a scanline: maximum10.
Reuse the #299 publisher and HRAM DMA unchanged, once per prepared publication.

## Finite acceptance

- Exact approved32-tile encoding, all12 pose maps and24 facing reconstructions;
  compare independently assembled shades, palette, offsets and tile references.
- Actual SM83 composer cases cover all24 facings, screen edges, signed camera,
  hidden/partially clipped pieces, stale-tail clearing and20/22-object bounds.
- Existing game state/collision fixtures qualify unchanged rules; independent
  scene expectations cover every other object in global8x8 mode.
- Short actual Intel-preloaded composed pixel proof and one wrong-piece fault
  use fixed expected pixels and the unchanged publisher. Complete a small
  harness first, including pause/terminal/watchdog; freeze exact dot counts
  after code layout. Target120s per simulation/hard300s each, target300s aggregate.
  No full-game replay or FPGA rebuild for artwork alone.
- Required local/hosted checks and independent current-head review. Historical
  ROM/image proofs keep their producer identity; this changed image is new.

## Reference boundary

Pinned SML1 source618d00ed6c330928e106719533c6e294ae5d5726:
bank0 Call_1736 delegates to bank3 Call_4823. That renderer selects coordinate
and tile tables, reflects offsets for facing and emits OAM attributes. This
supports the composition structure only. Our geometry, asset bytes and code
are original; no commercial data or instruction sequence is copied.
