# Current entity verification

The [owning entity contract](../../../wiki/src/sw/springtrail/ENTITIES.md)
defines four original classes, their contacts, fixed slots, reset and offscreen
behavior. Expected states come from `entities_reference`; approved tile maps and
pixels come from `entities_art` and `entities_frames`, never DUT observations.
The PR and tagged artifacts own execution results and producing identities.

## Finite acceptance matrix

| Contract | Actual CPU or pixel witness | Independent host checks |
|---|---|---|
| Carry, support, jump-off and half-open landing | neutral-carry, jump-off, landing, right-edge-no-land, blocked-carry | Fractional terrain rejection detaches rider without player displacement |
| Moving endpoints | moving-right, moving-return, moving-left | Stage placements include the rider envelope; endpoint clamps reverse velocity |
| Falling lifecycle | fall-arm, fall-delay, fall-start, fall-absent, fall-stays-absent, rider-released-at-absence | Full countdown/offscreen trajectory, no implicit respawn |
| CURL | curl-outside/range, active-end/cooldown-end, small/large/protected/star, stomp-immune, shot-immune | Inclusive trigger range, state/timer and immunity literals |
| Patrol and contact order | patrol-stomp, stomp-second-pose, stomp-hidden, patrol-endpoint, patrol-stomp-before-curl, fatal contact | Stomp kills patrol before fatal CURL; reversed order would leave patrol alive |
| Pause, reset and stages | pause-freeze, resume, Select/full reset, actual WON-to-stage1/2 | Resume preserves NewLevel; resets repopulate records and clear reserved bytes |
| Fixed capacity | invalid/live slots, explicit absent-slot spawn; six OAM cases | Invalid/live spawn preserves owner; entry40 does not write, canaries remain intact |
| Complete rendering | Normal and changed fixed scenes, each blank plus one complete image | All174 tile encodings, complete independent160-byte OAM and every pixel |
| Current observation | Source-built ROM decoder3, current state-player/play tests | Full records, reserved-zero failures, default/delayed/changed-phase positive routes |
| Retained feature coverage | Current mus/pus/bks/gps shorts and mr/pr pose images | All152 old case projections remain exact with current123-field expectations |
| Fault sensitivity | Accepted MovingX store16-to0 mutation after first marker | Unchanged neutral-carry state checker must reject the downstream lost movement |

The state suite has41 named ordinary-operand calls in nine batches a..i, at most
five calls each. It observes all123 player, power, block, progression and entity
bytes, including reserved zeros. Shared InitGame/UpdateGame/SpawnEntity routines
run on the CPU. The last case seeds player x361/y112 and falling platform
x368/y128: the platform advances to y130, terrain rejects carry, the player stays
at x361/y112 and rider becomes zero.

The OAM suite has six cases in three two-case parts: normal, changed, maximum
large scene, reflected/cracked scene, signed clipping and exhausted entry40.
It observes285 bytes: complete123-byte state, all160 shadow bytes and adjacent
canaries. Ordered writes must match exactly; only declared composer scratch and
stack writes are permitted. The maximum scene has35 entries and a zero tail.

The two renderer fixtures seed ordinary fixed state, load all174 approved tiles
by CPU writes, initialize all32 ring columns through shared routines, and call
PrepareScene/HUD/Progress plus the unchanged HRAM DMA/IRQ publisher. Each checks
46,080 pixels (blank plus full scene),320 DMA bytes, HRAM-only active-DMA CPU
access, both STAT/VBlank pairs, the HUD split and complete settled ending.
Normal uses patrol WALK1, dormant CURL and solid platforms; changed uses STOMP2,
active CURL, the moving endpoint and crack2. These are renderer operands, not
claims about an autonomous gameplay route or physical display.

## Commands and budgets

Use the canonical Python/cocotb and Intel-model preload through `tools/build.py`:

- `sim test python-entities-short`, then `python-entities-a` through `-i`.
- `sim test python-entities-oam-short`, then `python-entities-oam-a/b/c`.
- `sim test python-entity-render-short`, then `python-entity-render-normal/changed`.
- `sim test python-entities-fault`: an intended raw failing state proof.
- Current compatibility: `python-mus`, `python-pus`, `python-bks`, `python-gps`,
  `python-mr` and `python-pr`; retain qualified unchanged full-branch evidence.
- Current game/pause compatibility: `python-mgs` and `python-pgs`, with complete
  source-model script histories and qualified retained full-run paths.

Every command uses its own build tag. CPU/OAM/entity-fault targets retain300
seconds total wall. State batches guard160,000 dots; OAM short/full guard70,000/
160,000. Both complete entity renderers declare420 seconds from the measured
short and complete source windows recorded by each generated fixture. The two
retained pose renderers explicitly declare480 seconds: their expanded source
windows projected about417 seconds at the measured throughput, leaving
insufficient margin at420. The hidden-piece optimization reduces those source
windows without changing the complete pixel/publication checks. These are independently reviewed target allowances, not inherited defaults.

The finite queue includes ten state runs (short plus nine batches), four OAM,
three entity renderer, one state fault, four retained CPU shorts and two retained
pose renderers. The source-equivalent hidden-piece change additionally selects
three fresh OAM groups and two current game/pause shorts. The measured completed
runs plus these five bounded checks remain within the declared9000-second
aggregate, including retained setup/oracle failures. This aggregate does not
extend a target; original failures retain their own receipts.
Short harnesses include final pause, settled hold, terminal marker and exact END.
Every failure remains a failure in its original receipt; corrected-checker replay
is separately identified and cannot relabel a raw result.

## Current and retained inputs

`current_unit_cases` keeps the original152 before/after field projections for
motion, power, blocks and progression. Missing initial fields are suite-constant
ordinary operands; the CPU copies them before every marker from one compact
source table. The checker still observes all123 bytes. Direct-call literals
remain unchanged; game/reset expectations use the independent current entity
world. No expected result is injected into the fixture.

The visible computation must finish within65,664 dots before the same next
publication. The owning source bound covers UpdateGame, PrepareScene, HUD,
progress and columns, dispatch and STAT service. Entity work never runs in
VBlank. The unchanged publication instructions retain4412 of4480 dots in their
heaviest restoration case; the68-dot margin is not available for new work.

Physical qualification remains separate. The required broader composer, HUD
and interaction matrices retain their named open coverage issues; these finite
entity fixtures do not claim universal combinations or game compatibility.

## Timing

The unchanged VBlank publication path takes at most4412 dots within4480.
The reachable visible preparation below takes at most65328 of65664 dots with
a live shot. These are source bounds, not inferred from the largest observed
test case. [`visible_bound.py`](visible_bound.py) derives the scene and shot
columns by running the actual routines on the independent SM83 timing model
over exhaustive branch operands, and `test_visible_bound.py` fails at level1
when any row no longer fits; `python src/dv/springtrail/visible_bound.py`
prints the table. The update, map and other columns are the source partitions
below. Component costs include RET and exclude each outer CALL; Main includes
all five outer CALLs. Other is HUD388 + Progress640 + STAT512 + Main256, or320
for title/reset transitions. Requalify this bound when changing source paths,
state reachability, stage geometry or approved piece positions.

| Reachable profile | Update | Shot | Scene | Map | Other | Total | Margin |
|---|---:|---:|---:|---:|---:|---:|---:|
| stage0 air ascent without ceiling | 24292 | 5544 | 27996 | 2412 | 1796 | 62040 | 3624 |
| stage0 air descent | 25260 | 5544 | 27996 | 2412 | 1796 | 63008 | 2656 |
| stage0 interactive underside hit | 24096 | 5544 | 27996 | 4108 | 1796 | 63540 | 2124 |
| stage0 noninteractive terrain ceiling | 26744 | 5544 | 27996 | 2412 | 1796 | 64492 | 1172 |
| stage0 terrain supported | 27036 | 5544 | 27996 | 2412 | 1796 | 64784 | 880 |
| stage0 groundloss topRow8 | 25932 | 5544 | 27996 | 2412 | 1796 | 63680 | 1984 |
| stage0 groundloss topRow9 | 26208 | 5544 | 27996 | 2412 | 1796 | 63956 | 1708 |
| stage0 groundloss topRow10 | 24596 | 5544 | 27996 | 2412 | 1796 | 62344 | 3320 |
| stage0 groundloss topRow14 | 26916 | 5544 | 27996 | 2412 | 1796 | 64664 | 1000 |
| stage0 moving supported | 26536 | 5544 | 27996 | 2412 | 1796 | 64284 | 1380 |
| stage0 falling supported | 26536 | 5544 | 27996 | 2412 | 1796 | 64284 | 1380 |
| stage0 moving supportloss | 27376 | 5544 | 27996 | 2412 | 1796 | 65124 | 540 |
| stage0 falling successfulcarry supportloss | 26928 | 5544 | 27996 | 2412 | 1796 | 64676 | 988 |
| stage0 falling failedcarry | 27580 | 5544 | 27996 | 2412 | 1796 | 65328 | 336 |
| later-stage ordinary noncarrier | 29956 | 0 | 23320 | 2412 | 1796 | 57484 | 8180 |
| later-stage ordinary carrier upper | 27952 | 0 | 23320 | 2412 | 1796 | 55480 | 10184 |
| early stage restoration/title transition | 29956 | 0 | 23320 | 4108 | 1860 | 59244 | 6420 |
| idle/reset/next-stage modes | 5400 | 0 | 27996 | 4108 | 1860 | 39364 | 26300 |

### Scope and shot reachability

Stage0 reaches the thrower in ordinary play: the once-only mushroom block makes
the player large and the once-only coin block then promotes a large player, as
[BLOCKS.md](../../../wiki/src/sw/springtrail/BLOCKS.md#contents) specifies. A
live shot is therefore reachable in every stage0 play profile, including a
rider on either platform, and the Shot column charges each of them. Its value is
the exhaustive `StepShot` maximum5136 over every stage0 cell, tile-crossing
offset, velocity sign and block state, less the40-dot no-shot return, plus the
`PowerInput` spread424 between its cheapest path and the spawn path and the
24-dot throw-timer decrement: 5544. Later stages keep no block on their pages
(every block column lies below the stage1 base), stage entry clears power and
shot state, so they stay small with no shot or effect. A reset clears the same
bytes before any restoration frame, and no block is reachable while the ring
restores, so the restoration and title rows use the small population. Idle
modes run no world update; a frozen shot only adds its piece to the scene.
Seeded thrower/shot fixtures remain supported and required.
After ordinary publication, BlockDirty is clear. A fresh interactive head hit may request two columns and uses Map4108; ordinary profiles use the one-column Map2412. Restoration is a separate profile. At most17 ordinary updates complete32 columns, so resetX24 plus2px per update stays<=58 and Camera0; no block or entity platform is reachable during that interval.
Five outer CALLs are120 dots. Active main overhead256 also includes visibility polling, mode dispatch, JP WaitFrame and DI/token/EI/HALT. ReadButtons occurs before publication and outside this visible interval. Title transition uses320. The existing single STAT IRQ allowance512 is separate. HUD388 and Progress640 include their RETs.

### Scene population

`PrepareScene` is a fixed sequence of composers whose costs add. The scene cap
is the base composition11168 plus each composer's largest branch delta
(courier568 for the large mirrored hidden record walk, shot1096, effect848,
patrol36, CURL28, falling52), plus every emitted piece at the exhaustive
`EmitPiece` maximum388, the zero tail for that population and the248-dot
spread of pose selection. The full population is35 pieces: large courier6,
patrol4, items8, goal2, shot1, effect4, CURL4 and two platforms of3, giving
27996. The small population is28 pieces with no shot or effect, giving23320.
`EmitPiece` takes its x and y offsets in B and C, keeps HL for the record and
tile walkers, refuses entry40 before any write, and still publishes X, tile and
flags for a hidden piece with Y0; every branch of its clipping tests is inside
the388-dot maximum. The tail clears four bytes per68-dot iteration and returns
DE at C1A0 as before. The OAM byte order and every shadow byte are unchanged:
`test_visible_bound` composes the ordinary acquisition route and the OAM
maximum, mirrored and clipped operands on the timing model and compares all160
bytes with the independent scene model, and the OAM, courier, renderer and CPU
fixtures prove the same bytes on the RTL.

### StepPlayer and contact partitions

Terrain-supported player Y is tile-aligned, so XCells has at most2 iterations. Current support rows10/11/12/13/16 correspond to player rows8/9/10/11/14. Row8 X cells are cheap76; row9 has one cheap76 and one at most776; row10 support row12 uses MotionSupport1084; row14 cells and support are cheap. EntitySupport is an X-miss at row8/9/10 source regions (1644 instead of1980). Resulting conservative Step maxima are8492/9192/8524/8176/7492; global9192.
Ground-loss rows8/9/10 use Step11440/12140/10104 after the same EntitySupport restriction, with Before3484. Row8 and row10 player bottom remains below104 after the downward4px step, so patrol/CURL overlap exits by the first Y comparison (Overlap628, CurlContact860) and cannot run enemy contact. Row9 is horizontally far from patrol/CURL. Goals are X-misses in all three regions. No platform can accept a landing in these regions, giving Landing1776. Four pickups can have at most one full horizontal overlap. Row14 retains generic noncarrier Step9072 and Landing3052.
A fresh interactive underside hit has pre-move Y96..99, so X cells are cheap. The bounded source paths give Step8064. It cannot be the first fresh jump from nearby ground, so Before1800. Its block X regions cannot touch either platform, so Landing1776. Resolve retains the full1524 and Map4108. A noninteractive ceiling retains generic air Step9436 and full1524 Resolve as an overestimate, but cannot create BlockDirty; Map remains2412.
For actual carriers, successful carry aligns feet with the current platform. Subsequent support loss means X leaves that platform; a failed carry marks that slot detached. The other platform is far, and vertical motion does not change X. Therefore neither can accept EntityLanding:1776. Moving carry preserves tile-aligned Y, giving Before7720 and lossStep9072. Successful falling carry uses candidate-Y alignment: aligned sum16792 or unaligned17196. Failed falling carry is separate: Before8776 plusStep9072, because the rejected candidate Y need not share old-player alignment.


The source locators are `src/sw/springtrail/entities.asm` (carry/support/landing),
`movement.asm` (StepPlayer and cell walks), `blocks.asm` (CellSolid), `interactions.asm`
(contacts), `blocks.asm` (grant and dirty-column ownership), `progress.asm`
(stage/reset), `scene.asm` and `courier.asm` (composition and tail), and
`main.asm`, `hud.asm`, `map_restore.asm`, `stream.asm` (publication/preparation).
The bounds include bounded cell loops, fixed populations, finite camera ranges
and the stated reachable-state partitions; arbitrary seeded unit operands use
separate fixture watchdogs and do not redefine the live-layout bound.
