# Contact and power research contract

This is the approved contact/power contract for
[#302](https://github.com/amichai-bd/nand2mario/issues/302). It replaces the
baseline rule that any enemy overlap enters retry. `src/sw/springtrail/power.asm`
and `interactions.asm` implement it against the independent
`src/dv/springtrail/power_reference.py`, which was frozen before the code.
The [movement contract](MOVEMENT.md) is unchanged; this page adds contact
classes, power states, protection windows, crouch and one projectile.

## Reference boundary

Use kaspermeerts/supermarioland revision
`618d00ed6c330928e106719533c6e294ae5d5726`, [bank0][bank0] and
[enemies][enemies]. Nothing is vendored or rebuilt. Routine names locate
external evidence; the original implementation shares no addresses, tables or
instruction sequences. The normal `GameState_00` dispatcher remains an
`INCBIN`, so the consumers of the reference's power-status timer and the frame
at which a status advances are not established. Every duration below is
therefore an original choice unless the row says otherwise.

## Confirmed local behavior

| Area | Confirmed rule | Evidence and limit |
| --- | --- | --- |
| Contact test order | After an entity box overlap, a nonzero invincibility timer kills the entity; otherwise a positional test separates a stomp from a side hit. | `Call_84E`; the entity box is one shared test for enemies and power-ups. |
| Stomp test | The stomp branch requires the player's top to lie above the entity's top by more than a small fixed margin; no velocity is tested. | `Call_84E .jmp_8C7`; reference coordinates are sprite-relative, so the margin is not a pixel oracle for this game. |
| Stomp response | A stomp sets jump status and a fixed short curve index, then a flying pose; the entity is hit and a chain timer of 50 counts limits a chain of three. | `Call_84E .enemyKilled`; the chain rewards score only. |
| Side hit | With no invincibility, a super status at or above 3 skips injury; nonzero super status calls injure, zero calls kill. | `Call_84E .jmp_94B`; status 3/4 are the reference's hurt and protection statuses. |
| Injure | Sets super status 3, clears projectile capability and starts an 80-count timer. | `InjureMario`; the status 3 to 4 to 0 advance lives in the missing dispatcher. |
| Grow | A mushroom sets super status 1 with the same 80-count timer; a flower when already status 2 grants projectile capability with no growth animation, otherwise it acts as a mushroom. | `Call_84E .pickupMushroom`, `.pickupFlower`. |
| Star | Sets an invincibility timer of 248 that decrements every fourth frame and toggles player visibility each decrement. | `.pickupStar`, `Call_1F03`; music-length coupling is excluded. |
| Super box | Super status 2 raises the entity-contact box top by 2 units unless the crouch animation is selected; crouch requires status 2 and grounded. | `Call_84E .jmp_88E`, bank0 `.downButton`. |
| Projectile | One projectile at a time with a time-to-live, removed when out of bounds. | bank0 `Call_1F2D`; its trajectory and bounce tables are not established here. |

## Original resolution

On 2026-09-11 the owner authorized best-effort alignment with explicit original
choices where the reference is silent. These choices are the contract:

- Power states: 0 small, 1 large, 2 thrower. Thrower is large with projectile
  capability and no separate artwork, as in the reference.
- The terrain collision box stays 8x16 for every state; large artwork extends
  8 pixels above it and may overlap ceilings visually. The entity-contact box
  is the terrain box with its top raised by 2 pixels when the state is large
  or thrower and the player is not crouching. Enemy, item and goal tests share
  this contact box.
- Contact classes, tested only while the enemy is alive and after fall death:
  1. Invincible (timer nonzero): the enemy dies; the player is unchanged.
  2. Stomp: the player's bottom edge lies at most 4 pixels below the enemy's
     top edge, in whole pixels of the floored positions. The enemy dies; the
     player enters ascent with jump index 13, saved index 0, grounded clear
     and pose JUMP. No position snap, no score and no chain.
  3. Hit: any other overlap. Ignored while the protection phase is HURT or
     SAFE. Otherwise a large or thrower player becomes small and enters HURT;
     a small player enters RETRY.
- Phases and durations in PLAY updates: GROW 32, HURT 32, then SAFE 96. Timers
  advance at the start of each PLAY update, before input, motion and contact.
  A timer reaching 0 changes HURT to SAFE with 96, and GROW or SAFE to normal.
  Invincibility lasts 248 updates from `GrantStar` and decrements every update.
  Throw pose lasts 8 updates. A projectile lives at most 64 updates.
- `PowerUp` from small sets large and GROW 32, replacing any HURT or SAFE
  window; from large it sets thrower without animation; from thrower it does
  nothing. `GrantStar` sets the invincibility timer to 248. Item ownership,
  spawning and pickup belong to [the block contract](BLOCKS.md#contents).
  Its coin-block release additionally promotes an already-large player to
  thrower; this does not change either entry point or reset behavior.
- Crouch: Down held while the state is large or thrower, grounded and jump
  state 0, decided before motion. Crouching masks Left and Right for that
  update's motion, so movement coasts or stops under the movement contract,
  and the masked byte is what the player's previous-button store records.
  Jump and B edges are unaffected. Small players ignore Down.
- Projectile: a new B edge while thrower, not crouching and no live shot
  spawns one at the player's top-left plus 4 pixels down, moving 2 pixels
  per update horizontally toward the facing direction and 2 downward. Each
  axis moves separately; a solid tile at the leading edge cancels that axis's
  move and reverses its velocity. Leaving the world horizontally or vertically
  removes the shot. A live shot overlapping the living enemy kills it and
  removes the shot. Spawn precedes the shot's own move in the same update.
- Update order: timers, crouch and throw input, player motion, enemy patrol,
  shot move and shot contact, game timer, fall death, enemy contact, items,
  goal. Fall death precedes every contact class; stomp and damage do not
  block collection or the goal in the same update.
- Restart and retry reset every power byte; a dead enemy stays dead until
  then. Pause freezes all timers with the world.

## Visible poses

Displayed pose precedence, evaluated in scene preparation without advancing
state: title STAND; retry RETRY of the current size; HURT phase alternates
large-hurt while `(timer-1) & 4` is nonzero and small-hurt otherwise, so it
ends small; throw timer nonzero selects large-throw; crouch selects
large-crouch; GROW alternates the small form while `(timer-1) & 4` is nonzero
and the large form otherwise, so it ends large; else the motion pose in the
current size, with logical skid mapped to the small or large skid. The player
object is hidden while `Fell`, while SAFE `(timer-1) & 4` is nonzero, and
while the invincibility timer is nonzero with `(timer-1) & 4` nonzero. The
`timer-1` parity aligns every four-update block and ends each window visible.

| Visible state | Source | Pose index and tiles |
| --- | --- | --- |
| Small/large STAND, WALK1-3, JUMP, RETRY | Approved [courier poses](CHARACTER_ART.md) | 0..11, existing VRAM tiles 42..73 |
| Small skid | Approved core `small-skid` | 12, VRAM 94..97 |
| Large skid | Approved core `large-skid` | 13, core 43 and 44 at VRAM 102..103; other pieces reuse loaded tiles |
| Small hurt | Approved core `small-hurt` | 14, core 21 and 22 at VRAM 98..99 |
| Large hurt | Approved core `large-hurt` | 15, the same head tiles plus loaded body tiles |
| Large crouch | Approved core `large-crouch` | 16, loaded tiles only |
| Large throw | Approved core `large-throw` | 17, core 45 at VRAM 100 |
| Shot | Approved core `shot-a` | one 8x8 object, core 54 at VRAM 101 |

All pixels are already approved in [CORE_ART.md](CORE_ART.md); no new or
changed art is introduced. The [player-actions preview](core-art/player-actions.svg)
shows the reused poses. Small crouch and small throw are approved but unused.
Startup copies the six core tiles to VRAM 98..103 with the LCD off.

## State and integration boundary

New gameplay state occupies C06A..C077:

| Byte | Meaning and reset |
| --- | --- |
| C06A | Power state 0 small, 1 large, 2 thrower; reset 0 |
| C06B | Phase 0 normal, 1 GROW, 2 HURT, 3 SAFE; reset 0 |
| C06C | Phase timer; reset 0 |
| C06D | Invincibility timer; reset 0 |
| C06E | Throw pose timer; reset 0 |
| C06F | Enemy alive; reset 1 |
| C070 | Crouch decided this update; reset 0 |
| C071..C072 | Shot X, signed 1/16 pixel; reset 0 |
| C073..C074 | Shot Y, signed 1/16 pixel; reset 0 |
| C075 | Shot X velocity, signed 1/16 pixel; reset 0 |
| C076 | Shot Y velocity, signed 1/16 pixel; reset 0 |
| C077 | Shot time-to-live, 0 none; reset 0 |

`InitGame` resets these bytes. `PowerUp` and `GrantStar` are exported entry
points. The shot appears as one extra object after the goal pair only while
live; all other scene bytes are unchanged. Scene preparation and the retained
4480-dot publication deadline are unchanged.

Literal anchors fixed independently of DUT output:

- A small player at x=252, y=104 falling with jump state 3 onto the enemy,
  which has just moved to x=256.5: the candidate y=108 places its bottom 124,
  four pixels below the enemy top 120: a stomp. The enemy dies, jump index
  becomes 13 and the next update rises 1 pixel.
- A grounded small player walking right from x=252 at y=112 has bottom 128,
  eight pixels below 120: a hit and RETRY. The same contact when large sets
  small and HURT 32; 32 updates later SAFE 96; 96 later normal. Contacts in
  those 128 updates change nothing.
- A large player at x=96, y=97 holding its ascent at profile index 20 has
  contact top 95, so it collects the item whose box spans 88..96; the same
  small player, with top 97, does not.
- A thrower facing right at x=24, y=112 pressing B spawns a shot at (24, 116)
  moving (+2, +2); it touches ground row 16 on its third update and reverses
  to (+2, -2) without moving down that update.

## Finite proof boundary

Literal cases in `src/dv/springtrail/power_reference.py` and
`test_power_reference.py` were frozen before the code. The actual shared SM83
routines run in the short complete CPU harness (`python-pus`), its bounded
full case set in two halves (`python-pua`, `python-pub`), one actual consumer
fault (`python-pux`) and
the rendered-state fixture (`python-pr`). The six motion targets are rerun as
affected regression. The [owning DV plan](../../../../src/dv/springtrail/POWER.md)
records the matrix and measured walls.

[bank0]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/bank0.asm
[enemies]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/enemies.asm
