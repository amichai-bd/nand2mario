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

Every command uses its own build tag. CPU/OAM/entity-fault targets retain300
seconds total wall. State batches guard160,000 dots; OAM short/full guard70,000/
160,000. Both complete entity renderers declare420 seconds from the measured
short and full source windows326492/326588. The two retained pose renderers
explicitly declare480 seconds for their expanded357132/361188-dot windows:
current throughput forecasts about417 seconds, leaving insufficient margin at
420. These are independently reviewed target allowances, not inherited defaults.

The finite queue includes ten state runs (short plus nine batches), four OAM,
three entity renderer, one state fault, four retained CPU shorts and two retained
pose renderers. Maximum planned allowances total7800 seconds;9000 seconds
includes retained setup/oracle failures. This aggregate does not extend a target.
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

Publication retains the unchanged 4412-dot source bound and 4480-dot check.
The complete visible update, scene, HUD, progression, map preparation and
interrupt/dispatch overhead must fit the same 65664-dot visible interval.
Per-fixture watchdogs are not a proof of that whole-path requirement.
Current game and pause compatibility also require their complete short harnesses;
full scripted source-model histories supplement the retained execution evidence.
