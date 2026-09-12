# Later SML1 stage inventory

This page inventories the Super Mario Land 1 mechanics that the
[staged alignment](sml1-alignment.md) leaves outside its first aligned
release: boss encounters, stage exits and the bonus game, the two vehicle
stages, and the exceptional transitions around them. It records what the
pinned reference does, what the current image already has, what each
mechanic would need, and whether it fits the mapperless 32 KiB image. It is
an inventory, not a plan of record: nothing here is implemented, approved
art, or a scheduled issue. The owner selects what to schedule.

## Scope and constraints

- Gameplay stays in software. No mechanic here asks for RTL, an MBC, audio,
  or copied code, pixels, maps or addresses.
- The image stays mapperless at 32768 bytes under the
  [game specification](SPEC.md#product-and-implementation-boundary). Where a
  category cannot fit, this page says so and names the deferred 64 KiB MBC1
  profile, [#307](https://github.com/amichai-bd/nand2mario/issues/307), as the
  only future path. It does not propose changing that decision.
- Every classification is `implemented`, `partial`, `missing` or `uncertain`.
  `uncertain` means the pinned files locate the mechanic but its body is an
  `INCBIN`, lives in an unpinned bank, or carries an annotation that needs
  independent confirmation.
- NES Mario and SML2 mechanics are not substitutes. Audio is excluded.

## Reference boundary

Evidence is kaspermeerts/supermarioland revision
`618d00ed6c330928e106719533c6e294ae5d5726`, [bank0.asm][bank0] and
[enemies.asm][enemies], read externally. Addresses below are the reference
ROM offsets that the disassembly labels; a label locates behavior, it is not
a specification. Three limits shape every row:

| Limit | Effect on this inventory |
| --- | --- |
| The normal gameplay state `0x00` at `$0627` and the autoscroll state `0x0D` at `$2376` are `INCBIN` blocks. | Per-frame player control in ordinary and vehicle play is not established from source; the vehicle rows are `uncertain`. |
| Bonus-game states `0x14`, `0x15` and `0x17` to `0x1A` jump to `$5832` to `$5841`, which the source comments place in bank 2. Bank 2 is not a pinned file. | The bonus room's walking, ladder climbing and prize award are `uncertain`; only its entry, drawing, ladder placement and exit are in bank 0. |
| Enemy definitions `Data_3186` (5 bytes per entry), `Data_3375` (3 bytes per entry) and the enemy scripts `Data_3564` are `INCBIN`. | Boss health values, movement patterns, projectile cadence and enemy-to-level assignment are not established. `enemies.asm` gives identities only. |

The game-state jump table at `$02A6` is the map for everything below. Each
state is one entry point, called once per frame from the main loop after the
VBlank wait. The current image's `GameMode` byte and its per-mode dispatch in
`interactions.asm` are the structural counterpart.

## Storage budget

The measured current image, built from `main` with
`python tools/build.py sw build springtrail --tag inv306 --json`, uses 20042
of 32768 bytes; 12726 remain. The parked progression work
([#304](https://github.com/amichai-bd/nand2mario/issues/304)) reports a net
+152 bytes on its own base, which predates the block layer, so roughly 12.5 KiB
remains once it merges. The entity families of
[#305](https://github.com/amichai-bd/nand2mario/issues/305) are unpriced;
this page assumes 1.5 to 3 KiB for three or four families with art.

Estimates below are calibrated on measured section sizes, not guessed from
the reference: `power` 801 bytes for contact classes, three power states,
protection windows, crouch and one shot; `blocks` 568 bytes plus 1184 bytes
of block art for four blocks with head hits, breakage and effects; `movement`
1265 bytes; the parked `progress` 580 bytes for lives, a timer and a
three-stage table; `world` 1728 bytes and `columns` 728 bytes for 96 columns,
about 25 bytes per column of collision and display data; and 16 bytes per
8x8 tile of art. An estimate is a range; the low end reuses existing routines,
the high end adds its own.

## Inventory

### Boss encounters

Reference behavior, all in bank 0 unless noted:

| Behavior | Evidence |
| --- | --- |
| A boss is an ordinary enemy slot whose second `Data_3375` byte is at or above `$C0`; spawning it also requests boss music. Health is the low six bits of slot byte `$0C`. | `SpawnEnemies` at `$249B`, `Jmp_250B`, `ldh [$FFCC]` "health above C0 means boss"; `Call_2A68` `and $3F`. |
| A player shot decrements health once per hit; the hit sound differs for `HIYOIHOI` and `KING_TOTOMESU`. At zero the enemy is replaced by the fourth byte of its `Data_3186` entry and reinitialized. | `Call_2A68` at `$2A68`, ids `$32` and `$08` in `enemies.asm`. |
| In the autoscroll state the same test uses `Call_2AAD` with the fifth byte instead, and `DRAGONZAMASU`, `BIOKINTON` and `TATANGA` get the boss sound; Tatanga at zero health also sets `$D007`. | `$2AAD`; the caller `Call_200A` at `.jmp_2064` selects the routine by `hGameState == 0x0D`. |
| The stage ends when the player stands on tile `$E1`, the boss switch, which jumps to the win routine. The win routine preserves a vehicle animation nibble and enters state `0x07`. | `Call_17BC` at `$17BC` compares the `LookupTile` result; `Jmp_175B` at `$175B`; `Jmp_1B45` at `$1B45`. |
| On a boss level (level nibble equals 3) the end-of-level state calls `ExplodeAllEnemies` and the score countdown state keeps calling `Call_2491` each frame. After the last level (`$43`) the countdown is skipped. | `GameState_07` at `$0C40`, `GameState_05` at `$0C73`. |
| After the countdown a boss level enters the gate sequence: six frames of explosions, then a gate four segments tall whose bottom sits nine tiles under its top is opened one segment per eight frames by writing a blank tile during HBlank, then the player is walked right with a simulated Right press until screen x reaches `$C0`. | `GameState_1C` to `GameState_20` at `$0E15` to `$0EA9`. |
| Boss movement and firing are enemy scripts. Script opcodes are visible: `F1` launch projectile, `F5` fire with a one-in-four `rDIV` chance, `F6` halt until the player is near, `F7` explode all enemies, `FB` restart until near, `FC` place at screen x `$70`, `FD` music. The scripts themselves are `Data_3564`, an `INCBIN`. | `Call_2648` at `$2648`, opcode chain from `.checkF1`; `FC` is annotated "only used for Tatanga?", which is unconfirmed. |

Classification: `missing`; movement patterns and health values `uncertain`.

Current basis: one enemy with an alive flag, an 8x8 box, the three contact
classes and a shot that kills on contact ([POWER.md](POWER.md)); a goal box
that ends the stage; the block layer's tile-keyed table and one 16x16
effect object ([BLOCKS.md](BLOCKS.md)); a per-stage bound table in the parked
progression contract. There is no health counter, no multi-hit entity, no
switch tile, no gate, no scripted movement and no explosion effect.

Needs: a health byte and hit cooldown on the boss slot so one shot or stomp
counts once; two or three original movement patterns as counter-driven
routines, since the reference's scripts are not established; one boss
projectile using the shot mover with its own velocity; a switch tile that
`CellSolid` treats as ground and the goal test treats as the exit; an
end-of-stage sequence with the explosion effect and a gate drawn through the
existing column publisher; and a boss arena, either the tail of an existing
stage or about 24 dedicated columns.

Estimate: 700 to 1000 bytes of code, 512 bytes for a two-frame 32x32 boss,
about 130 bytes for projectile, switch and gate tiles, and 0 to 600 bytes of
arena columns: 1.3 to 2.2 KiB for one boss. Each further boss adds 0.9 to
1.3 KiB. One boss fits. Four bosses fit only if nothing else below is taken.

Dependencies: [#305](https://github.com/amichai-bd/nand2mario/issues/305)
for a second entity slot and its spawn ownership; the parked progression
contract for the stage exit it replaces on a boss stage.

Representative original scenario: enter the arena, take one hit while large
and shrink, land three shots on a patrolling boss with a 2-update cooldown,
stand on the switch, watch the gate open in four steps and the stage advance.
Test shape as [POWER.md](POWER.md#finite-proof-boundary): a frozen Python
reference, one short complete harness, two literal-case halves and one
consumer fault, each inside the 300-second default; a rendered fixture only
when the art integrates. Forecast aggregate 600 to 900 seconds across four
targets plus the affected power and movement regression.

### Stage exit and the bonus game

Reference behavior:

| Behavior | Evidence |
| --- | --- |
| On a non-boss level the end-of-level state reads the player's screen y. Below `$60` or at or above `$A0` it switches to bank 2 and enters the bonus game; otherwise it increments the level. | `GameState_06` at `$0CCB`. |
| The score countdown converts each remaining timer unit into 10 points and a sound on every second unit; it runs `UpdateTimerAndFloaties` in bank 2 for the decrement. | `GameState_05` at `$0C73`, `AddScore` with `$0010`. |
| Entering the bonus game: music, LCD off, all 40 objects cleared, the whole map cleared to space, lives printed as two BCD digits at `$988A`, LCD on. | `GameState_12` at `$3D97`. |
| The room is drawn by loops, not a stored map: a bordered frame, the text `bonus game`, a head icon and marker, four floors of tile `$2D` eighteen wide, and one prize per floor chosen by a `rDIV`-seeded rotation through `0, 1, 2, $E5, 3, 1, 2, $E5`. `$E5` is annotated as a flower; the meaning of 0 to 3 is not stated. | `GameState_13` at `$3DD7`, `.prizePermutations`. |
| The ladder is four segments from `wLadderTiles` at `wLadderLocation`, redrawn under counters `$DA28` and `$DA29`. | `GameState_16` at `$3EA7`. |
| Walking, climbing, and the prize award are states `0x14`, `0x15`, `0x17` to `0x1A` in bank 2. Bank 0 initializes `wPrizeAwarded`, `wBonusGameEndTimer` `$40`, `wBonusGameGrowAnimationFlag` and `wBonusGameAnimationTimer` `$40`. | `$3D1A` initialization; bank 2 is not pinned. |
| Leaving: LCD off, HUD, coins and lives redrawn, LCD on, then the level increment state. | `GameState_1B` at `$0DF9`. |

Classification: entry, drawing and exit `missing`; play and award
`uncertain`.

Current basis: the parked progression contract owns the stage exit, the
lives byte, `PendingLife` and `UpdateLives`, and reserves the add path for a
later reward; `PowerUp` and `GrantStar` are exported; the HUD publisher
already redraws whole rows with the LCD on; the approved font covers the
room's text; `screen-clear` and `screen-level-entry` are approved
compositions. There is no full-screen room mode, no ladder or climb state
and no prize table.

Needs: a room mode that suspends the column streamer and draws a fixed
20x18 map by loops as the reference does, or from a 360-byte table; a
reduced player controller with walk, one ladder climb state and no jump;
four floor rows and a moving ladder; a prize row seeded from an existing
counter, since `rDIV` is not deterministic under the test harness; awards
bound to `PendingLife` and `PowerUp`; and a return that re-enters the next
stage through `EnterStage`. The exit-height test needs a second exit height
in a stage; the current stages have one ground-level goal.

Estimate: 600 to 900 bytes of code, about 400 bytes for 25 room and prize
tiles, 0 to 360 bytes of map: 1.0 to 1.6 KiB. Fits.

Dependencies: the parked progression contract merged; a deterministic seed
decision; a score display wider than one glyph if the countdown is adopted,
which changes the [HUD contract](HUD_COLUMNS.md).

Representative original scenario: clear stage 1 through a raised exit, enter
the room, climb to floor 3 while the ladder moves, collect a life, return to
stage 2 with lives incremented and the timer reset. Test shape as above; the
room draw needs one rendered fixture. Forecast 500 to 800 seconds across four
targets plus the progression regression.

### Vehicle stages

Reference behavior:

| Behavior | Evidence |
| --- | --- |
| Level start compares `hLevelIndex` with 5 and `$0B`, the third stages of worlds 2 and 4 under the confirmed three-levels-per-world advance, and sets the low animation nibble to `$0A` (submarine) or `$0C` (aeroplane) and the game state to `0x0D`. | `GameState_02` at `$06DC`, the level-start path before `.autoscroll`. |
| Animation indices at or above `$0A` skip the walking animation and the walk-right helper, and survive the win routine's mask. | `Call_16F5` at `$16F5`, `GameState_20.walkRight`, `Jmp_1B45.jmp_1B52`. |
| The autoscroll state body is `INCBIN` `$2376` to `$2401`, 139 bytes, annotated "too many calls to far banks". Scroll rate, vehicle control, bullet spawn and vehicle collision are therefore not established. | `GameState_0D`. |
| Player projectile hits use the autoscroll variant with health, boss sounds and the fifth replacement byte. | `Call_2AAD`. |
| Entity identities that the names suggest belong to these stages, with no level assignment in the pinned files: `GUNION`, `GUNION_FIREBALL`, `TORION`, `HONEN`, `YURARIN`, `YURARIN_BOO`, `TAMAO`, `DRAGONZAMASU` for water; `ROKETON`, `CHIKAKO`, `GIRA`, `DIAGONAL_GIRA`, `PIPE_CANNON`, `CANNONBALL`, the three `SMALL_CANNONBALL` parts, `BIOKINTON`, `TATANGA` for air. | `enemies.asm`; assignment is level data outside the pinned files. |
| The final boss sequence: shake by 4 pixels of `wScrollY` every four frames, an explosion every 32 frames, and blocks removed by a rotating bitmask; then the plane moves forward. | `GameState_27` at `$1099`, `GameState_28`. |

Classification: `missing`; every control quantity `uncertain`.

Current basis: the column streamer follows a camera that the game sets, so a
camera that advances on its own is a small change in the camera update, not
in `stream.asm`; the shot mover already handles a straight projectile with a
time-to-live; the world, collision and per-stage bound tables give a stage
its own columns and limits; the enemy step and the three contact classes
exist for one slot. There is no vertical free movement, no forced scroll,
no vehicle art, no multi-slot entities with health, no kill-by-crush at the
left screen edge and no water or sky backdrop.

Needs: a vehicle motion mode that replaces the movement contract for the
stage, with four-direction motion clamped to the visible screen and no
gravity; a forward bullet with a fixed velocity and cooldown; forced scroll
at a fixed fraction of a pixel per update with the player pushed by the left
edge; two or three entity families with health, spawned from a column-keyed
table as the camera reaches them; a boss in the same stage; a stage of about
80 columns on a second world page, which requires the collision base to
select a page rather than a column offset; and backdrop tiles for water or
sky.

Estimate: 900 to 1400 bytes of code, 128 bytes for a two-frame 16x16
vehicle, 16 bytes for the bullet, about 260 bytes for two enemy families,
about 130 bytes of backdrop, about 2.0 KiB of stage columns and a 100-byte
spawn table: 3.5 to 4.1 KiB for the first vehicle stage. The second vehicle
stage reuses the mode and costs 2.2 to 2.6 KiB more, chiefly columns and
art. One fits. Both fit only if the boss and bonus categories stay minimal.

Dependencies: [#305](https://github.com/amichai-bd/nand2mario/issues/305)
for multi-slot entities and spawning; the parked progression contract for a
fourth stage entry; the boss row for the stage's end; a decision on whether
the vehicle stage keeps the movement contract's 1/16-pixel units.

Representative original scenario: enter the stage, hold Up to rise to the
ceiling clamp, fire at a two-hit enemy twice, take a hit and lose the stage,
retry, survive to the boss column. Test shape as above plus one sampled
endurance run of one stage length. Forecast 700 to 1000 seconds across five
targets plus the movement, power and progression regression; the endurance
run is bounded to one stage and stays inside 300 seconds.

### Exceptional transitions

| Transition | Reference | Current basis and need | Classification and fit |
| --- | --- | --- | --- |
| Pipes and underground rooms | Down on tile `$70` at `Jmp_1765`; states `0x09` to `0x0C` at `$161B` to `$16DA`; a sideways pipe exits only while the underground flag `$FFF9` is set; an underground room is 20 tiles wide and does not scroll (`Call_807`). | The streamer publishes fixed maps; `EnterStage` selects a stage. Needs a room stage with scroll disabled, a pipe tile, two transition animations of about 16 updates and a return column. 300 to 500 bytes of code, about 370 bytes of room columns. | `missing`; fits. |
| End-of-stage score countdown | `GameState_05`: 10 points per remaining timer unit, one unit per frame, sound on alternate units. | The score is one glyph. Needs a multi-digit score and a wait mode; about 150 bytes plus the HUD change. | `missing`; fits, but changes the HUD contract. |
| Boss gate and walk-off | `GameState_1C` to `GameState_21`. | Inventoried under bosses. | `missing`; fits. |
| Time up and game over | `GameState_39` to `GameState_3C`. | Owned by the parked progression contract as modes 5 and 6. | `partial` until that work merges. |
| Rescue, impostor, ending and credits | `GameState_21` to `GameState_38`, `$0ECD` to `$14DC`: scripted dialogue, a morphing impostor, the final boss death, a plane leaving and credits. | Narrative content, not a mechanic. The approved `screen-clear` composition is the original equivalent. Not inventoried for implementation; an ending screen costs about 400 bytes as a map. | Not planned. |

## Assets

Approved sources are the three groups in [CORE_ART.md](CORE_ART.md). This
table names reuse and gaps; it approves nothing and creates nothing.

| Category | Reusable approved sources | Missing original content | Proposed owner |
| --- | --- | --- | --- |
| Bosses | `shot-a`, `shot-b` for a boss projectile; `spark`, `spark-a`, `spark-b`, `PUFF1`, `PUFF2` for hits and explosions; `stone`, `post` for a switch base | One boss character in two poses, a hit pose, a switch tile, four gate tiles, an arena backdrop | The boss issue, following the [game-assets](../../../../.agents/skills/game-assets/SKILL.md) workflow |
| Bonus game | Full font and digits for the room text and lives; `life`, `heart`, `leaf`, `gem`, `coin1` as prize icons; `screen-level-entry` and `screen-clear` as room framing | Six border tiles, a ladder pair, a floor tile, a courier climb pose | The bonus issue |
| Vehicle stages | `water`, `spike`, `cloud` as backdrop; `shot-a` as the bullet; `POD FLAP1`, `POD FLAP2` as one air family | A submarine and an aeroplane in two frames each, a torpedo or shell, two water families and one air family, an underwater backdrop set, a crush or sink death effect | The vehicle issue |
| Pipes and rooms | `brick`, `stone`, `ledge` for a room; existing courier poses | A pipe cap pair and a pipe body tile | The transition issue |
| Ending | `screen-clear` | Nothing required | None |

Bank IDs in the approved sheets are review indices, not VRAM allocation.
The current allocation uses tiles 0 to 139 of the 256 object tiles, and the
parked progression work adds nine glyphs, so about 100 tile slots remain
resident. Boss and vehicle art can load per stage with the LCD off, as the
current startup copies do, rather than staying resident.

## Fit against the 32 KiB image

| Selection | Estimated cost | Remaining of about 12.5 KiB after the parked progression work and 1.5 to 3 KiB of entities | Verdict |
| --- | --- | --- | --- |
| One boss | 1.3 to 2.2 KiB | 7.3 to 9.7 KiB | Fits |
| Bonus game | 1.0 to 1.6 KiB | 7.9 to 10.0 KiB | Fits |
| One vehicle stage with its boss | 4.4 to 5.4 KiB | 4.1 to 6.6 KiB | Fits |
| Pipes and one room | 0.7 to 0.9 KiB | 8.6 to 10.3 KiB | Fits |
| One of each above together | 7.4 to 10.1 KiB | 0.0 to 3.6 KiB | Fits at the low end only; the high end exhausts the image |
| SML1 shape: twelve stages, four bosses, two vehicle stages, the bonus game, pipes | About 30 KiB of stage data, art and code beyond the current image | Negative | Does not fit mapperless. [#307](https://github.com/amichai-bd/nand2mario/issues/307) is the only path, and it stays deferred until a demonstrated need. |

Estimates carry about 30 percent uncertainty either way; the high ends are
the honest planning figures. Stage data dominates: at about 25 bytes per
column, nine more stages of 80 columns cost about 18 KiB before any code
or art, which is why the full shape cannot fit regardless of code size.

## Roadmap distinction and unresolved measurements

Core-stage completion is the alignment page's first aligned release:
composition, publication, HUD, movement, contact and power, blocks,
progression and the entity families. Nothing on this page is part of it.
Full non-audio feature coverage would add every category above, and the fit
table shows it cannot be mapperless. The owner chooses which categories, if
any, to schedule after core completion; each scheduled category becomes its
own issue with a frozen reference, literal cases and a runtime forecast, as
[POWER.md](POWER.md) and [BLOCKS.md](BLOCKS.md) were.

Unresolved reference measurements that no current or parked contract owns:

- Boss health values and the replacement entries (`Data_3186`, `Data_3375`).
- Boss and enemy movement scripts (`Data_3564`) and projectile cadence.
- Autoscroll rate, vehicle speed and bullet parameters (`GameState_0D` body).
- Bonus-room walk, climb and award rules (bank 2, unpinned) and the prize
  meanings 0 to 3.
- Enemy-to-level assignment (level data outside the pinned files).
- The score award per remaining timer unit is visible as 10 points in
  `GameState_05`; the timer decrement it calls is in bank 2.

Independent confirmation of an uncertain annotation belongs to the issue
that adopts it, never to this page.

[bank0]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/bank0.asm
[enemies]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/enemies.asm
