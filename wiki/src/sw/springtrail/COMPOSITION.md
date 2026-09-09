# Courier composition

The [composer](../../../../src/sw/springtrail/courier.asm) emits ordinary OAM pieces.
The [approved art](CHARACTER_ART.md) owns all pixels and twelve pose maps.

## Coordinates and allocation

Keep the logical 8x16 collision box and all movement/input/update rules.
The original artwork is centered on that box: its left is floor(PlayerX/16)-4,
its feet are floor(PlayerY/16)+16. Small top is floor(PlayerY/16); large top is floor(PlayerY/16)-8 pixels.
These are intentional original anchors, not claimed SML1 dimensions.
For camera subtraction use full signed pixel coordinates before OAM encoding.
Each 8x8 piece is visible only when -7 <= x < 160 and -7 <= y < 144;
partially visible pieces retain their coordinates. Entirely clipped/hidden pieces
use Y=0. Hardware handles the remaining partial pixel clipping.

Existing tiles 0..41 stay at VRAM8000..829F. The approved 32-tile courier bank
uses IDs42..73, VRAM82A0..849F (512 bytes). OBP0=E4 preserves shade ordering;
shade0 stays transparent. Tiles and map plus courier bank remain in the assets
ROM section0C00..13FF; composer tables/code use a separate ROM1 section at5200, after
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
Use the [HRAM DMA publisher](../../../../src/sw/springtrail/oam_dma.asm)
unchanged, once per prepared publication.

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

## CPU fixture budget

The32 cases are24 pose/facing calls, four clip/hidden calls, three directional
start/restart scenes and one signed-camera/fractional scene. Poisoning occurs
only initially and before the first full scene. The one-case harness checks
terminal completion and settled pause before full execution.

A longest syntactic branch path through EmitPiece costs at most580 dots;
CourierPiece overhead is bounded by296 per piece and setup220 per pose.
There are140 direct pieces, then four20-piece scenes. Full-scene overhead
includes signed coordinate conversion, state selection and the80-byte tail.
Allow260000 total dots, including both160-byte poison loops, operand writes,
three UpdateGame calls and terminal readiness. The 70-ms simulation watchdog
and 300-second whole-process wall bound remain fixed.

Conservative dot accounting: direct pieces140*(580+296)+28*220=128800;
four scenes at25000 each=100000 (includes their80 pieces, seven signed
coordinate projections, selection and tail clearing); two poison loops7728;
operand/setup instructions10000; three bounded UpdateGame calls12000; terminal
and pause allowance1024. Sum259552 is below260000. These are ceilings, not
claims that the actual execution consumes them. The game and unit image have
identical bytes for all nine shared non-code/non-asset sections.


## Bounded composed proof

The current game proof uses the actual ROM and all 74 loaded tiles. It checks
all 23,040 pixels of the initial blank frame and all 23,040 pixels of the next
TITLE frame against independent original-art expectations. INPUT 129 is applied
60,000 through 62,000 dots after the initial LCD-enable write. The next visible
interval executes one ordinary update and prepares its complete 160-byte scene.
The following VBlank publishes those bytes through DMA before the test pauses.
It does not claim to capture pixels of that third frame.

The public LCD-enable write supplies the phase origin, not an expected image or
state. Startup must lie between 100,000 and 130,000 dots: the prior 81,352-dot
initialization gains 512 tile bytes at 52 dots each; replacing its at-least
5,996-dot preparation with the conservative 25,000-dot scene bound gives an
upper bound of 126,980 dots. The unchanged UpdateGame bound is below 20,000 dots;
PrepareScene is below 25,000 and dispatch below 1,000. Thus preparation must
finish within 46,000 visible dots, before the same next VBlank at 65,664.

A complete short harness stops after at least 160 blank pixels, with initial
DMA, trace END, ordinary HALT and settled pause checked. The full target has a
285,000-dot progress limit and an 80-ms simulation watchdog. Each execution
retains the ordinary 300-second whole-process limit.

The negative changes tile 42 to tile 0 once at the actual Intel OAM write
boundary of the first LCD-on publication, after checking the original byte.
It skips the initial LCD-off DMA, which would be overwritten before TITLE is
visible. The unchanged full-frame oracle must reject the resulting image.

The older nine-object frame and renderer helpers are historical-only. Their
ROM/source guards reject this composition. Current checks are
`python-courier-unit`, `python-cgs`, `python-cgu` and `python-cgx`; historical
endurance cannot silently validate a new ROM.
