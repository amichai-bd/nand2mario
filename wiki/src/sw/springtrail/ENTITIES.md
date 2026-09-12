# Bounded enemies and platforms

Planned contract for the [four required entity classes](https://github.com/amichai-bd/nand2mario/issues/305).
The implementation and acceptance below are pending. The existing movement,
[power](POWER.md), [blocks](BLOCKS.md) and [progression](PROGRESS.md) contracts
remain in force except for the explicitly added entity contacts described here.
No gameplay runs in RTL; the image remains mapperless 32768 bytes with three stages.

## Reference boundary

Reference revision: `618d00ed6c330928e106719533c6e294ae5d5726` of
[kaspermeerts/supermarioland](https://github.com/kaspermeerts/supermarioland/tree/618d00ed6c330928e106719533c6e294ae5d5726).
Its [entity definitions](https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/enemies.asm)
identify CHIBIBO/STOMPED (00/01), MEKABON/HEAD/BODY (16/17/18),
HORIZONTAL_PLATFORM (0A) and DROP_BLOCK/FALLING (36/37). These establish the
selected classes and separate active states, not numerical equivalence.
The [bank0 dispatcher](https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/bank0.asm)
separates entity spawning, contact and drawing from hardware sprite storage.
The following constants, placement and bounded state machines are original local
choices. No commercial code, graphics or ROM is copied or needed. CURL is a
single triggered hazard; it does not reproduce the reference's separate head/body.
Further classes remain in the [later inventory](sml1-later-stages.md).

## Slots, updates and persistence

There are exactly four fixed ownership slots: patrol, CURL, horizontal platform,
and falling platform. No dynamic allocator, projectile pool or general entity
engine is introduced. Stage entry initializes all four from literal stage tables;
reset also restores the ordinary progression state. An invalid slot index is
rejected without a write. A live slot cannot be overwritten by another spawn.

The patrol keeps EnemyX, EnemyVX and EnemyAlive as its authoritative state,
including the existing stage-specific bounds, half-pixel step and8x8 contact box.
Its16x16 art is centered around that box, with its bottom on the same floor.
The other slots use signed Q4 positions. Their state advances once per PLAYING
update, never during pause/title/retry/time-up/clear/over. Offscreen entities
continue deterministic state updates; leaving the screen does not respawn them.
Dead patrol and expired falling platform stay absent until stage entry/reset.
There is no viewport-derived spawn, random delay or hidden update cadence.

Update order: progression/timers and existing power input, platform motion and
possible rider carry, ordinary player motion/terrain collision and camera,
block resolution, patrol and CURL updates, shot update, fall death, enemy/hazard
contacts in patrol-then-CURL order, items, goal. A fatal patrol contact ends
contact processing; otherwise its resulting hurt/protection state is visible to
CURL in that same update. Platform landing is resolved immediately after ordinary
player motion and before the fall test; camera is updated after any carry/snap.
A game-state transition still consumes the existing update exactly as PROGRESS
specifies. Rendering only reads the prepared resulting state.

## Contacts and selected behavior

### Patrol

Keep current patrol bounds, speed and power contact precedence. Invincibility
kills first; the existing top-margin stomp rule bounces using jump index13;
otherwise hurt protection ignores contact, large player shrinks, small player
enters retry. Shot contact removes the enemy once. Killing does not add a new
score/life reward. Store a16-update stomp display countdown; it advances only
while PLAYING and then hides all patrol pieces. Shot/star kills hide immediately.
WALK1/2 alternate every8 playing updates; STOMP1/2 split the countdown at8.

### CURL triggered hazard

One fixed8x8 contact box at each stage's literal position, with16x16 centered art.
Dormant is harmless. If absolute player-left minus hazard-left is at most32pixels,
it enters active with timer32; the same update is active for contact. Active
counts down once per following PLAYING update; at zero it becomes dormant with
cooldown32. Cooldown decrements and cannot trigger until the following update.
No detached projectile is created. Active CURL ignores stomp and player shots;
invincibility destroys it until stage entry. Other contact uses the existing
hurt/protection/retry rules. Dormant/cooldown display CURL DORMANT, active CURL ACTIVE.

### Horizontal platform

One24x8 one-way top surface. It moves one pixel per PLAYING update within an
inclusive32-pixel horizontal interval; clamp at either endpoint and reverse for
the next update. It ignores static terrain as an entity; placement must keep its
path clear. A rider is a player whose prior bottom equals the prior platform top,
whose prior horizontal half-open box overlaps, and whose jump state is supported.
Capture prior player x/y, grounded/jump state and both old platform positions
before moving either platform. This snapshot alone establishes the prior rider.
Carry by the platform's actual delta before ordinary player movement unless a
new jump edge was accepted. Clamp/collide carry against existing terrain; a
blocked carry detaches, never crushes or teleports through a wall.

Landing requires non-upward player motion, old bottom <= old platform top and
new bottom >= new platform top, with overlap at the resulting horizontal position.
Snap player top to platform top minus16pixels, set grounded, zero vertical
velocity/jump state. The first qualifying platform in slot order owns contact.
Underside and side contacts do nothing; jumping off does not inherit momentum.
Walking beyond the half-open top detaches and resumes ordinary falling.

The motion routine must recognize exact platform support in its jump/support
path: a prior supported rider may accept an A edge just like a terrain rider.
After horizontal movement, supported jump-state0 with a matching platform top
and current half-open overlap remains grounded with zero vertical velocity;
terrain-only support rejection must not spuriously select the falling pose.
This is a narrow one-way support predicate, not a tile-map change: ascending
motion, side scans and block head-hit reporting never see platform solidity.
Landing uses the pre-update player/platform snapshot and the resulting positions,
not an observed sprite, previous OAM byte or already overwritten coordinate.

### Falling platform

One24x8 top with the same landing rules. First rider contact arms a16-update
countdown without moving that update. It displays CRACK1 while timer>8 and CRACK2
while1..8. At zero it falls two pixels per PLAYING update, including a remaining
rider under the same carry rules. It becomes absent when its top reaches144;
its rider detaches and ordinary fall death applies. It never respawns on re-entry.
Before contact it uses SOLID. Pause freezes both countdown and position.

## Literal stage placement

Each stage retains its current patrol placement. New triples are
`CURL(x,y); moving(left,right,y); falling(x,y)` in pixels:

| Stage | CURL | Moving interval | Falling |
|---|---|---|---|
| 0 | (328,120) | (176,208,112) | (368,112) |
| 1 | (352,120) | (144,176,112) | (320,112) |
| 2 | (328,120) | (112,144,112) | (368,112) |

These are ordinary stage contents, not test-only entities. The entire swept platform and16-pixel rider envelope is clear against
each stage's literal terrain; checking only the platform body is insufficient.
No stage geometry is changed by these placements. All positions fit even the632-pixel stages.

## Storage and artwork

C078..C08F belong to blocks; C090..C096 to progression, C097..C09C to its prepared
cache. New persistent state is C300..C32F (three16-byte records for CURL, moving,
falling) and C330..C337 (patrol animation/stomp countdown and rider/contact state).
Each record has x:i16,y:i16,state:u8,timer:u8,vx:i8, reserved9bytes zero.
Transient operands use C338..C34F and are not persistent host fields. Exact symbol
names and unused-zero invariants must be shared by the ROM-bound host decoder.
C100 shadow and C200/C220 caches are unchanged. No entity writes OAM directly.

Use the existing enemies-tiles.json/enemies-maps.json approved source. Local tile
indices0..10 and19..32 pack in that order into25tiles, runtime IDs149..173,
400encoded bytes in VRAM. The unchanged full41-tile source atlas occupies
656 ROM bytes at7200..748F; startup copies only the selected25tiles, using
the existing asset/copy mechanism. Existing149tiles remain unchanged. Enemy art
uses palette0/shade0 transparency. Whole facing reflection moves pieces and
flips pixels; platforms are unreflected. Missing art approval is not a gate.

Reserve entity code0400..09FF and entity render/contact helpers5A00..5FFF; fixed
linker section overlap checks are mandatory. The fresh baseline uses20197bytes,
leaving12571 total bytes but fragmented holes. If actual allocation exhausts the
image, keep three stages and shorten stage geometry/reuse tiles before cutting
art states; do not move the shipping game to MBC1.

OAM order: courier, patrol, items, goal, shot, block effect, CURL, moving, falling.
Maximum is35 entries for large courier plus live shot and four-piece block effect
(33 for small). Remaining entries are zero. At the physical ten-objects-per-line
limit, earlier entries win; later pieces may be absent, with no state change.
A defensive emit at entry40 rejects the piece without writing beyond C19F.
HUD y<16 clipping and signed camera projection retain existing rules.

All entity work and shadow preparation are outside VBlank. The existing worst
restoration publication ends at4412 of4480 dots; its68-dot margin is not a budget
for extra entity work. Publisher bytes are unchanged unless a separately reviewed
bound proves the changed path. New visible preparation must fit before its same
next publication; no extra frame latency or timing/clock change is permitted.

## Acceptance boundary

The [finite verification plan](../../../../src/dv/springtrail/ENTITIES.md) owns
literal input/state/pixel cases and measured budgets. Current ROM-bound UART
state decoding and reconstruction must be updated and host-tested early, using
the source-built image and independent models. Unsupported ROM/schema profiles
remain rejected. Physical proof is separate; no FPGA/monitor claim follows from
these software fixtures. Missing unrelated current composer/HUD/interaction
matrices remain in their existing named coverage issues.
