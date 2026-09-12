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
The reachable visible preparation below takes at most65652 of65664 dots.
These are source bounds, not inferred from the largest observed test case.
Component costs include RET and exclude each outer CALL; Main includes all
five outer CALLs. Other is HUD388 + Progress640 + STAT512 + Main256, or320
for title/reset transitions. Requalify this bound when changing source paths, state reachability, stage
geometry or approved piece positions.

| Reachable profile | Update | Scene | Map | Other | Total | Margin |
|---|---:|---:|---:|---:|---:|---:|
| stage0 air ascent without ceiling | 24292 | 34368 | 2412 | 1796 | 62868 | 2796 |
| stage0 air descent | 25260 | 34368 | 2412 | 1796 | 63836 | 1828 |
| stage0 interactive underside hit | 24096 | 34368 | 4108 | 1796 | 64368 | 1296 |
| stage0 noninteractive terrain ceiling | 26744 | 34368 | 2412 | 1796 | 65320 | 344 |
| stage0 terrain supported | 27036 | 34368 | 2412 | 1796 | 65612 | 52 |
| stage0 groundloss topRow8 | 25932 | 34368 | 2412 | 1796 | 64508 | 1156 |
| stage0 groundloss topRow9 | 26208 | 32688 | 2412 | 1796 | 63104 | 2560 |
| stage0 groundloss topRow10 | 24596 | 34368 | 2412 | 1796 | 63172 | 2492 |
| stage0 groundloss topRow14 | 26916 | 34368 | 2412 | 1796 | 65492 | 172 |
| stage0 moving supported | 26536 | 33528 | 2412 | 1796 | 64272 | 1392 |
| stage0 falling supported | 26536 | 33864 | 2412 | 1796 | 64608 | 1056 |
| stage0 moving supportloss | 27376 | 33528 | 2412 | 1796 | 65112 | 552 |
| stage0 falling successfulcarry supportloss | 26928 | 33864 | 2412 | 1796 | 65000 | 664 |
| stage0 falling failedcarry | 27580 | 33864 | 2412 | 1796 | 65652 | 12 |
| later-stage ordinary noncarrier | 29956 | 31060 | 2412 | 1796 | 65224 | 440 |
| later-stage ordinary carrier upper | 27952 | 31060 | 2412 | 1796 | 63220 | 2444 |
| early stage restoration/title transition | 29956 | 29380 | 4108 | 1860 | 65304 | 360 |
| idle/reset/next-stage modes | 5400 | 34536 | 4108 | 1860 | 45904 | 19760 |

### Scope and source invariants

The current reset-reachable layout has one once-only mushroom block. The ordinary thrower acquisition gap is owned by [#515](https://github.com/amichai-bd/nand2mario/issues/515); any change to that layout must requalify this bound. ResolveMushroom marks it used before the sole PowerUp call. EnterStage clears power and block state together. Thus live power is at most1 and ShotTTL remains0. Later stages have no matching interactive block columns and remain small with no effect or invincibility. Seeded thrower/shot fixtures remain supported and required; this live-frame proof does not replace their routine budgets.
After ordinary publication, BlockDirty is clear. A fresh interactive head hit may request two columns and uses Map4108; ordinary profiles use the one-column Map2412. Restoration is a separate profile. At most17 ordinary updates complete32 columns, so resetX24 plus2px per update stays<=58 and Camera0; no block or entity platform is reachable during that interval.
New scene source CFG caps before X savings are36048 for stage0 (34pieces/noShot) and32572 later (28pieces/small/noShot/noEffect). Current approved offsets and all legal integer cameras give at least10/10/9 fixed X-hidden pieces by stage. Each such piece reduces528 to360, saving168. Carrier-specific hidden counts are15/13,15/11,17/9 for moving/falling. Ground-loss row9 atX630..682 has20 hidden pieces. At Camera0 the stages have22/20/19 hidden pieces.
Five outer CALLs are120 dots. Active main overhead256 also includes visibility polling, mode dispatch, JP WaitFrame and DI/token/EI/HALT. ReadButtons occurs before publication and outside this visible interval. Title transition uses320. The existing single STAT IRQ allowance512 is separate. HUD388 and Progress640 include their RETs.

### Population and tail monotonicity

Every admitted EmitPiece takes at least308dots including RET but excluding the caller: nonreturning capacity checks40, X calculation104, the shortest SceneHidden branch32, XOR4, four ordered stores/loads/DE advances plus RET128. Omitting one piece therefore removes at least308dots (plus any caller/setup cost) and adds at most four ClearSceneByte iterations,4*52=208dots. The maximum34/28-piece populations safely bound smaller courier/effect populations with longer zero tails. Capacity refusal is inapplicable below40. Hidden deductions apply only to the24 always-emitted fixed slots, not optional courier extras, effects or shots.

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
