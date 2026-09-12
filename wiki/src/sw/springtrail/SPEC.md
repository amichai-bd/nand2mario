# Springtrail

The [original game source](../../../../src/sw/springtrail/main.asm) implements
title/start, movement, scrolling, interactions and game flow. Physical-presence
release acceptance remains in the charter's
[remote acceptance](../../project-charter.md#remote-acceptance) split.
The [charter](../../project-charter.md) owns the hardware and release boundaries;
the [game verification plan](../../dv/springtrail/SPEC.md) owns acceptance.

## Product and implementation boundary

The next release follows the [staged SML1 alignment contract](sml1-alignment.md).
The rules and 32 KiB profile below remain the delivered baseline until their
named implementation issues replace them with measured original equivalents.
Separate banking qualification does not change this baseline profile.

Springtrail is a working title for a silent, original monochrome platformer:
one scrolling trail, a small courier character, platforms and gaps, a walking
enemy, collectibles and a finish marker. All character designs, tile/sprite art,
level layouts, text and code are original. Familiar run/jump mechanics do not
authorize copying a commercial game's characters, graphics, music, maps or ROM.
There is no commercial cartridge to locate, download, rebuild or reproduce.

Implement gameplay as SM83 assembly in `src/sw/springtrail`, built by the
existing [Python software pipeline](../../../tools/sw/SPEC.md). Use exactly
32768 ROM bytes, no mapper and no cartridge RAM, in the existing
[`dmg-direct-v1` profile](../../rtl/interfaces/MAS_interfaces.md#direct-entry-and-reset).
Use its generated constants, entry state and normal Game Boy graphics, timer,
interrupt and JOYP registers. The game reads standard JOYP; UART and physical
controls reach it through the existing shared input owner, without game-specific
hardware MMIO. ROM bytes remain immutable while running.
After each JOYP row-select write, wait at least24 DMG dots before reading the
selected row. This prevents transitional direction bits from becoming actions;
the [settling proof](../../../../src/dv/springtrail/JOYP_SETTLE.md) owns validation.

Do not put movement, enemies or game state in RTL. Keep the approved original-DMG
model, 25 MHz system architecture, register macros, Intel storage/models and
clock/reset/CDC contracts. Change hardware only for an independently demonstrated
compatibility defect in its owning contract. Do not add an MBC, SDRAM, a game
engine, an AI framework, a compiler or audio to deliver this game.

## Player-visible rules

The [shadow OAM publisher](../../../../src/dv/springtrail/OAM_DMA.md) transfers
the complete C100-C19F image through standard FF46=C1 DMA from HRAM at FF80.
Scene preparation emits the current 8x8 objects and clears all remaining bytes.
The shared publisher supports all 40 entries without interpreting an active
count; the [composition contract](COMPOSITION.md) owns geometry and limits. Initialize
the HRAM routine before LCD enable, then publish in the existing VBlank slot
after map work. Its wait keeps CPU accesses in HRAM until transfer completion;
the ordinary stack is accessed only before and after DMA. Input sampling,
once-per-frame updates and the approved prepared-scene delay are unchanged.

The [approved original character art](CHARACTER_ART.md) supplies the 32-tile
courier bank and twelve pose maps. The [8x8 composer](COMPOSITION.md) supports
both facing directions, signed clipping and small/large geometry. Normal play
uses the [movement and animation contract](MOVEMENT.md) in the size selected by
the [contact and power contract](POWER.md).

The game has title, playing, paused, retry and won states. Core reset starts at
the title. A retry or restart restores the initial player, camera, enemy,
collectibles and score; it does not preserve a hidden life counter or randomness.

| Button | Behavior |
|---|---|
| Left / Right | Move horizontally while playing; Right takes priority when both are held, subject to reversal hold |
| B | Select the run speed class under the movement contract; a new press throws one shot while the player is a thrower |
| A | Jump on a new press while grounded; holding A does not queue another jump |
| Start | Title: start; playing: pause; paused: resume; retry/won: restart the level |
| Select | Restart the level only while paused; ignored elsewhere |
| Down | Crouch while large and grounded under the power contract; small players ignore it |
| Up | No gameplay action in this level |

Pause freezes player/world simulation, enemy movement, collection and the game
timer, while the ROM's display/input loop and host transport remain active.
Resume continues the preserved state without queued movement/jump events.
This in-game pause is distinct from host HALT and emulated CPU HALT.

Use three original stages inside one 18-by-256 grid of 8-by-8 tiles, viewed
through the normal 160-by-144 DMG image. The
[progression contract](PROGRESS.md) owns the stage table: stage 0 is the
unchanged 96-column world at base column 0, and stages 1 and 2 are 80 columns
wide at base columns 96 and 176. The stage index selects the collision base,
the camera and player x limits, the goal, the enemy bounds and the items. An 8-by-16 player has an axis-aligned collision box.
The camera follows horizontal player position, clamped to the level edges;
camera movement cannot change world-space collisions. Terrain platforms are solid
from all sides. The [entity contract](ENTITIES.md) adds one-way moving and falling
platform tops, with explicit carry, jump-off and blocked-carry rules; there are no slopes. Vertical motion,
jump, landing and wall/ceiling collision must be deterministic. Falling below
the level enters retry. The walking enemy reverses at its specified patrol
endpoints while alive. The [contact and power contract](POWER.md) classifies
enemy contact as invincible, stomp or hit: a stomp or a live shot kills the
enemy until restart; a hit shrinks a large player into a protection window and
sends a small player to retry. The triggered CURL hazard follows patrol contact
and cannot be stomped or removed by a shot. Its star-contact, activation and
cooldown rules are owned by [Entities](ENTITIES.md).

The [interactive block contract](BLOCKS.md) adds four 16-by-16 blocks over the
unchanged terrain: an ascending head hit uses one block per update, an item or
hidden block releases its content once, a brick breaks only under a large or
thrower player, and the consumed state survives scrolling and pause until a
restart. Coins increment an undisplayed counter, not the score.

Each collectible increments the visible counter once and disappears until the
next stage entry. Touching the finish marker while alive clears the stage;
collecting every item is optional. Death takes precedence over collection or
clearing on the same update; a stomp or a non-fatal hit does not. An expired
countdown precedes every contact class.
The [progression contract](PROGRESS.md) owns the lives, the countdown timer and
the stage lifecycle: a retry spends one packed-BCD life and re-enters the
current stage, a cleared stage advances to the next one, and the last stage or
a spent last life resets the game to stage 0 with two lives. Pause/restart decisions precede world updates. The stationary background
[HUD](HUD_COLUMNS.md) occupies screen rows 0..15. Row 0 shows the mode word and
the score; row 1 shows the lives, the countdown and the stage number beside the
approved life and clock icons.
The playfield retains world y coordinates in rows 16..143; neither the collision
world nor the ground at y=128 moves. HUD clipping hides only object pixels above
row 16, preserving the lower part of a crossing piece.

The [movement contract](MOVEMENT.md) owns counter/phase-based acceleration,
coasting, reversal hold, run selection, jump profiles, release response and pose
cadence. These are approved original best-effort rules, not a claim of complete
SML1 equivalence. Positions and reported velocities use signed 16-bit units of
1/16 pixel. The initial player top-left is (24, 112), grounded on tile row 16,
with camera x=0. The camera anchor is screen x=72 and its clamp is 0 to the
stage's limit, 608 pixels on stage 0 and 480 on the other two. The enemy moves
at 1/2 pixel/frame between the stage's patrol endpoints; on stage 0 it starts
at (256, 120) and patrols x=240..296 inclusive.

The renderer has one displayed frame of input-to-publication delay (about
16.7 ms). Each VBlank
samples JOYP and publishes the scene prepared from the preceding sample.
During the following visible interval, apply that new sample once to game
state and prepare its next scene and HUD/column caches. That computation does
not write display memory or registers. The separate line-15 STAT handler applies
the published camera and enables playfield objects in HBlank; VBlank resets
scroll and disables objects for the next HUD. This preserves one input/game update
per normal frame; it does not add another queued update or display frame.
Title removal and restart map/SCX changes accompany the published scene,
not the newly computed logical transition. Pause freezes game state while
publication continues; inactive map restoration may continue while paused.

Each VBlank samples JOYP once. Process restart/pause first. A playing update
advances power timers and decides crouch and throw. Entity preparation snapshots
and advances platforms, then applies prior-rider support and carry. StepPlayer
selects run/jump state, advances animation and resolves horizontal and vertical
motion. Entity landing and camera calculation follow. The update resolves a
head-hit block, advances the patrol, CURL and shot, then processes contacts in
the [entity contract's order](ENTITIES.md). Scene preparation reads the resulting
state without advancing animation. The [movement contract](MOVEMENT.md) and the
[power contract](POWER.md) own their motion and power rules.
Resolve each axis
against all solid tiles touched by the half-open collision box, using floor of
the fixed-point coordinate. Snap to the contacted tile edge and clear velocity
on that axis; only downward contact sets grounded. Test interactions after both
axes. Falling means player top-left y >=144. The enemy uses an 8-by-8 box.

Stage 0 has ground in rows 16 and 17 except gap columns 22..25,
46..49, and 70..73. Additional solid platforms occupy row 12 columns 10..14,
row 10 columns 31..35, row 12 columns 56..60, and row 11 columns 80..84.
All other cells are empty; the block layer adds no terrain and occupies world
rows 10 and 11 at page columns 38, 52, 64 and 88, which places every block on
stage 0. Its collectibles are 8-by-8 boxes at (96, 88), (264, 72), (464, 88),
and (656, 80); its 8-by-16 goal starts at (736, 112). The
[progression contract](PROGRESS.md) lists the other two stages, whose literal
rows live in the same [world source](../../../../src/sw/springtrail/world.asm). Collectible
and goal tests use half-open rectangle overlap against the power contract's
contact box. The [interaction routines](../../../../src/sw/springtrail/interactions.asm)
[power routines](../../../../src/sw/springtrail/power.asm) and
[block routines](../../../../src/sw/springtrail/blocks.asm) implement these
mechanics. No parameter is selected from DUT output.
Update the game once per normal emulated frame using a documented input-sampling
point. There are no wall-clock or nondeterministic random inputs.

<a id="delivery-sequence"></a>

## Regression boundary

The [verification plan](../../dv/springtrail/SPEC.md) defines composed, rule and
physical acceptance separately. The original v0.5
program and its [accepted matrix](../../dv/v05/SPEC.md#revised-milestone-matrix)
remain a separate regression baseline. Preserve its qualified results without
claiming they implement or verify Springtrail.
