# Springtrail

Status: planned original game under [#259](https://github.com/amichai-bd/nand2mario/issues/259).
No Springtrail code, assets or gameplay are delivered by this specification.
The [charter](../../project-charter.md) owns the hardware and release boundaries;
the [game verification plan](../../dv/springtrail/SPEC.md) owns acceptance.

## Product and implementation boundary

Springtrail is a working title for a silent, original monochrome platformer:
one scrolling trail, a small courier character, platforms and gaps, a walking
enemy, collectibles and a finish marker. All character designs, tile/sprite art,
level layouts, text and code are original. Familiar run/jump mechanics do not
authorize copying a commercial game's characters, graphics, music, maps or ROM.
There is no commercial cartridge to locate, download, rebuild or reproduce.

Implement gameplay as SM83 assembly in planned `src/sw/springtrail`, built by the
existing [Python software pipeline](../../../tools/sw/SPEC.md). Use exactly
32768 ROM bytes, no mapper and no cartridge RAM, in the existing
[`dmg-direct-v1` profile](../../rtl/interfaces/MAS_interfaces.md#direct-entry-and-reset).
Use its generated constants, entry state and normal Game Boy graphics, timer,
interrupt and JOYP registers. The game reads standard JOYP; UART and physical
controls reach it through the existing shared input owner, without game-specific
hardware MMIO. ROM bytes remain immutable while running.

Do not put movement, enemies or game state in RTL. Keep the approved original-DMG
model, 25 MHz system architecture, register macros, Intel storage/models and
clock/reset/CDC contracts. Change hardware only for an independently demonstrated
compatibility defect in its owning contract. Do not add an MBC, SDRAM, a game
engine, an AI framework, a compiler or audio to deliver this game.

## Player-visible rules

The game has title, playing, paused, retry and won states. Core reset starts at
the title. A retry or restart restores the initial player, camera, enemy,
collectibles and score; it does not preserve a hidden life counter or randomness.

| Button | Behavior |
|---|---|
| Left / Right | Move horizontally while playing; both held cancel horizontal intent |
| B | Run while held with a direction; otherwise use walking speed |
| A | Jump on a new press while grounded; holding A does not queue another jump |
| Start | Title: start; playing: pause; paused: resume; retry/won: restart the level |
| Select | Restart the level only while paused; ignored elsewhere |
| Up / Down | No gameplay action in this level |

Pause freezes player/world simulation, enemy movement, collection and the game
timer, while the ROM's display/input loop and host transport remain active.
Resume continues the preserved state without queued movement/jump events.
This in-game pause is distinct from host HALT and emulated CPU HALT.

Use a single original 96-by-18 grid of 8-by-8 tiles, viewed through the normal
160-by-144 DMG image. An 8-by-16 player has an axis-aligned collision box.
The camera follows horizontal player position, clamped to the level edges;
camera movement cannot change world-space collisions. Platforms are solid from
all sides; there are no slopes, moving platforms or one-way surfaces. Gravity,
jump, landing and wall/ceiling collision must be deterministic. Falling below
the level or contacting the enemy enters retry. The walking enemy reverses at
its specified patrol endpoints. No stomp or combat mechanic is required.

Each collectible increments the visible counter once and disappears until
restart. Touching the finish marker while alive enters won; collecting every
item is optional. Death takes precedence over collection or winning on the same
update. Pause/restart decisions precede world updates. A small HUD distinguishes
score, pause, retry and win without relying on host-only state.

The following constants are frozen for dependent implementation. Positions and
velocities use signed 16-bit units of 1/16 pixel (range -2048..2047.9375).
Walking speed is 1 pixel/frame and running
speed is 2; horizontal velocity changes immediately with intent (no acceleration
or momentum). Gravity is 1/4 pixel/frame squared, jump impulse is -5.25 pixels/frame,
and downward velocity is capped at 4 pixels/frame. The initial player top-left is
(24, 112), grounded on tile row 16, with camera x=0. The camera anchor is screen
x=72 and its clamp is 0..608 pixels. The enemy starts at (256, 120), moves right
at 1/2 pixel/frame, and patrols x=240..296 inclusive.

Each VBlank samples JOYP once. Process restart/pause first, then horizontal
intent, grounded jump edge, gravity, horizontal motion/collision, vertical
motion/collision, enemy motion, death, collection, goal, and camera, in that
order. A jump applies its impulse before that update's gravity. Resolve each axis
against all solid tiles touched by the half-open collision box, using floor of
the fixed-point coordinate. Snap to the contacted tile edge and clear velocity
on that axis; only downward contact sets grounded. Test interactions after both
axes. Falling means player top-left y >=144. The enemy uses an 8-by-8 box.

The literal level has ground in rows 16 and 17 except gap columns 22..25,
46..49, and 70..73. Additional solid platforms occupy row 12 columns 10..14,
row 10 columns 31..35, row 12 columns 56..60, and row 11 columns 80..84.
All other cells are empty. Collectibles are 8-by-8 boxes at (96, 88), (264, 72),
(464, 88), and (656, 80); the 8-by-16 goal starts at (736, 112). Collectible
and goal tests use half-open rectangle overlap. These mechanics are planned;
the foundation displays the initial view without implementing movement or
interactions. No parameter is selected from DUT output.
Update the game once per normal emulated frame using a documented input-sampling
point. There are no wall-clock or nondeterministic random inputs.

## Delivery sequence

| Stage | Scope and prerequisite |
|---|---|
| [#260 Foundation](https://github.com/amichai-bd/nand2mario/issues/260) | Original build/header/assets, numeric rules, title/start and first world view |
| [#261 Movement/world](https://github.com/amichai-bd/nand2mario/issues/261) | Run/jump, collision, gaps and the complete scrolling level after foundation |
| [#262 Interactions](https://github.com/amichai-bd/nand2mario/issues/262) | Enemy, collectibles, win/retry and pause after movement |
| [#263 v0.9 verification](https://github.com/amichai-bd/nand2mario/issues/263) | Independent complete-game reference and the preserved release criteria |
| [#264 v1.0 physical acceptance](https://github.com/amichai-bd/nand2mario/issues/264) | Reviewed board execution and endurance after applicable simulation/setup gates |

These issues are planned work, not completion evidence. The original v0.5
program and its [accepted matrix](../../dv/v05/SPEC.md#revised-milestone-matrix)
remain a separate regression baseline. Preserve its qualified results without
claiming they implement or verify Springtrail.
