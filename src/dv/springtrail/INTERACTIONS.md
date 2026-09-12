# Interaction proof

## Current operand matrix

The current matrix uses the shared `UpdateGame` routine and the independent
entity/progression model. Its 20 inputs preserve all 123 game, motion, power,
block, progression and entity bytes, including reserved bytes. Expected output
is checker data only; the CPU fixture receives ordinary input operands.

| Obligation | Existing current case or new operand |
|---|---|
| Start with direction | Motion `title-direction` |
| Patrol right arrival and departure | Entity `patrol-endpoint`; new `patrol-right-depart` |
| Patrol left arrival and departure | New `patrol-left-arrive`, `patrol-left-depart` |
| Contact and retry restart | Power `walk-hit-small`; motion `retry-restart`; progression life-spend cases |
| Half-open enemy contact edge | New `patrol-edge-touch`, `patrol-edge-overlap`, separated by one Q4 unit |
| First pickup award | Power `item-large-box`; its small-box counterpart checks the contact-height boundary |
| Remaining pickup awards | New `item-1-award` through `item-3-award`, score 1→2→3→4 |
| Each pickup is once-only | New `item-0-once` through `item-3-once`, each with its own collected bit already set |
| Fall precedes item and goal | New `fell-before-item`, `fell-before-goal` |
| Goal, frame counter wrap, retry/advance | New `goal-frame-counter-wrap`; progression WON stage-advance/final-reset and retry-spend cases |
| Pause/resume and paused Select reset | Motion pause/resume chain and `select-restart`; entity `pause-freeze` |
| Select ignored during play | New `select-ignored-playing` |
| Current fatal/nonfatal contact priority | New CURL fatal/nonfatal pairs at item and goal; existing entity patrol-before-CURL pairs |

The Fell inputs deliberately exercise the authoritative flag at collection
coordinates. They prove guard order, not simultaneous events on a natural route.
The CURL overlap inputs similarly relocate ordinary entity operands to isolate
priority. They do not alter level placement. Existing progression cases retain
stage-specific goals, boundaries and reset behavior; no all-stage cross product
is implied by the historical four-pickup obligation.

The planned execution is one complete short followed by four groups of five
calls, plus an actual output mutation with the unchanged oracle. Every call
observes the full state. Completion must include CPU terminal marker, settled
pause, hold and END. Per-target total wall limit is 300 seconds. Full grouping
remains subject to complete-short throughput; no current CPU acceptance is
claimed by the literal host tests or by historical reports below.

## Historical execution

Historical execution targets named below are retired; these descriptions and
independent expectations remain historical evidence. See the
[family dispositions and required current coverage](MILESTONE.md#historical-fixture-registrations).


The [game rules](../../../wiki/src/sw/springtrail/SPEC.md) and
[verification matrix](../../../wiki/src/dv/springtrail/SPEC.md) own #262.
No v0.9 or physical release acceptance is implied by these focused checks.

## Finite acceptance map

| Requirement | Proof |
|---|---|
| Patrol endpoints, contact, once-only collection, death priority and goal | Independent integer rules and actual CPU routine cases; composed and physical images for integration |
| Pause, resume and Select-only-paused restart | Consecutive sampled input cases, preserved player/enemy/timer state, no queued jump; physical pause/resume/restart checkpoints |
| Complete level and failure/retry | Ordinary UART inputs, full original ROM upload/readback and independently checked selected frames; no RAM injection |
| Rendering and restored map | Exact prepared OAM/map bytes and timed VBlank writes; current complete-game initialization/input/frame proof and affected output fault |
| Delivery | Current scoped evidence, required checks and independent review |

The approved frame loop publishes the previously prepared state and computes
the next state once per frame from the sampled input. The composed proof below checks
this one-frame display delay. Physical route evidence remains separate.

## Actual CPU routine checkpoint

`python-fs` executes the first three reports and finishes through the
same terminal marker, normal UART HALT, trace END and cleanup as
`python-fu`. It is the complete-harness check before the longer run.
Both use actual Intel preload, normal CRC scan/adoption and the existing
continuous Python/public write trace. Software initializes ordinary operand
WRAM; no expected result is stored in the unit ROM. Complete movement,
interaction and collision sections must match the linked game bytes.

The full ROM has 27 reports in 15 groups, frozen in `interaction_cases.py`:
title Start+Right, both endpoint reversals, contact/retry, exact enemy edge,
each pickup and repeated overlap, death before pickup/goal, goal/restart,
timer wrap, pause/held-A/resume, paused restart and Select ignored during play.
Steps within a group preserve the actual preceding software state.

Each report checks 23 bytes: mode; player x/y/vx/vy as signed little-endian
sixteenth-pixel values; grounded, sampled buttons, previous player buttons,
camera, fall; previous game buttons; enemy x/direction, score, timer and item
mask. Input history and the independent model select expectations. Retirement
epoch, sequence and increasing dots are checked, without a full CPU-register
oracle. Require exactly one matching begin/end pair per report, all initialized
state fields, exact ordered report indices, the final A5 marker and trace END.
Reject unexpected input/pixels, extra writes after terminal, reset or fault.

Each routine bracket must be less than 20000 dots. The 600000-dot progress bound
covers 27 such brackets plus software initialization and reporting; the 200 ms
simulation watchdog is separate. This routine-only bound does not prove the
forthcoming combined rendering budget. The existing 300-second whole-process
limit includes preparation, compile, run, checks and 12-second cleanup reserve.

Before measurement, forecast the three-report smoke at 20-40 seconds and full
unit at 90-140 seconds. A later composed game/fault pair is provisionally
180/80 seconds: the planned selected aggregate may exceed the 300-second target.
These are forecasts, not measured results or cap extensions. Final render and
physical routes must be frozen and reviewed before their execution; unchanged
accepted movement evidence may be qualified, not relabeled as interaction proof.

## Collected-store fault

`python-fx` runs the unchanged full oracle and ROM. At the first WRAM
Collected write of one, the fixture forces only the storage input to zero
across its accepting system edge and releases it on the next falling edge.
The CPU/public write remains one. The next ordinary update reads the missing
bit, collects the same item again and increments score to two. The unchanged
`FLOW_STATE index=10 group=first-once` comparison must reject that downstream
result. Require the mutation record, raw simulator zero, failing Python XML
and nonzero outer result; an unrelated setup failure is not fault evidence.

The completed three-report harness took 26.305 seconds and the full 27-report
run took 70.565 seconds, both including setup and cleanup. The affected fault
is forecast below 70 seconds under the same 300-second hard cap. The earlier
`s262` attempt failed before HDL because its new target names made a Windows
temporary path 267 characters; shorter names reduce that path to 240. It is
retained as a setup failure, not a functional result.

## Inactive map restoration helper

`map_restore.asm` runs from the VBlank publication path.
`BeginMapRestore` selects static9800, clears SCX/history and restarts column0;
`RestoreMapPair` writes two complete18-row columns into9C00. The final pair
selects9C00 only after column31's final write. Other LCDC bits are preserved.
The caller invokes these routines only during VBlank and ensures
static9800 is the restored initial view. Streaming must never modify9800.

Instruction counting gives Begin96 dots and each column792 dots including
RET. The pair takes1764 dots normally or1800 on its final switch, excluding
the caller's24-dot CALL. These are source counts, not measured execution.
The combined renderer proof checks two-column plus OAM/HUD timing, map
equality and repeated partial restart; the physical route checks pause behavior.

## Scene preparation boundary

`PrepareScene` writes36 ordinary WRAM bytes at C100 for nine OAM entries:
player, enemy, four items, goal, score and mode. The frame loop prepares them
during visible time. Signed coordinate flooring and camera subtraction precede byte
encoding; fully off-screen or collected objects use OAM Y0. Score and mode
are screen-relative at (144,0) and (72,0). `scene_reference.py` owns the
independent expected bytes, including a literal initial scene and clipping
at x=-8/-7 with fractional Y.

The original tile pairs are player12, enemy16, item18, goal20,
score22+2*score and mode32+2*mode. The atlas and live OAM publisher use these
pairs. Lower tiles are blank for eight-pixel objects. The original16 tiles are
unchanged. Actual CPU scene/map checks and composed publication checks pass.

The static and scrolling maps contain terrain and title lettering only; item
and old fixed-counter background markers have been removed. Items and score
use OAM. Literal atlas and full composed-image checks cover their appearance;
physical restart images also check restored pixels.

## Combined routine proof

`python-rs` executes three complete renderer reports, including a second
restart of a partially restored map, then reads all576 map bytes, pauses and
requires trace END. `python-ru` executes18 reports: two initial pairs, then
restart and all16 pairs through final map selection. Both initialize the
inactive map with ordinary zero stores; six fixed scene operands exercise
fractional/negative coordinates, both horizontal clipping edges, collected
masks, score/mode, fallen player and far-camera cases. They do not claim
normal once-per-frame gameplay or pause scheduling.

For each report, require all36 prepared WRAM bytes, exact ordered map and
OAM writes, actual36-byte OAM readback, actual LCDC/SCX readback and complete
begin/end markers. The final576-byte VRAM readback must equal the independently
tracked map; partial, missing and duplicate output fails. Preparation is
bounded below12000 dots. The publisher/restoration bracket, including its
CALLs and marker overhead, must be below4200 dots, leaving268+64 dots for the
previously counted game-loop overhead/wake margin within4560. Caller timing
and the final combined game path remain separate integration obligations.

`python-rx` changes one actual prepared Y store128 to0 across its accepting
WRAM edge. The public preparation intent remains128, but the publisher reads
zero and must fail unchanged `RENDER_PUBLISH index=0`. Require mutation,
raw simulator zero, failing XML and outer failure. It is not a changed oracle.

Before measurement, forecast short50â€“70 seconds, full120â€“180 and fault30â€“50,
each under the unchanged300-second hard total limit. Added to the accepted
routine set142.479 seconds, the declared selected aggregate may exceed the
300-second target. Measure the complete short harness before the full run.
No extra simulation cap, live display latency or milestone waiver is implied.

The three-report renderer harness completed in62.914 seconds, including its
full576-byte map readback and pause/END. Its publisher brackets were2860,
2740 and2860 dots. Before the full run, background item/counter markers were
removed from both maps and the independent tile rule; all1728 world entries
match the frozen terrain. This data change does not alter collision solids,
routines, timing expectations, sampling or completion mechanics. The full
run will check the resulting marker-free map rather than qualify old pixels.

The renderer full run completed in149.302 seconds:18 reports,648 OAM and576
map readback bytes, with maximum preparation6068 and publisher2860 dots.
The affected stored-Y fault was rejected in33.129 seconds. All three renderer
runs meet the300-second hard cap; the full run misses the120-second target.
Together with the routine set, measured simulation time is387.825 seconds,
above the declared300-second aggregate target. Full game integration and
physical routes remain open; these component results do not close#262.

## Integrated frame schedule

The user approved one added displayed frame in
[issue262](https://github.com/amichai-bd/nand2mario/issues/262#issuecomment-5602361911).
The live loop samples JOYP in VBlank, publishes the prior prepared scene,
waits for LY below144, then calls UpdateGame and PrepareScene once. Title
removal and restart map/SCX changes occur with the published transition.
The completed ring uses the existing entering-column algorithm at9C00.

The instruction-derived LCD commit is76964 dots: entry stub20, prolog1124,
OAM clear3860, tile copy34976, title-map copy29984, palette32, scene preparation
5996, publication928 and final enable44. The first title-to-world publication
was bounded in PR276 by3920 dots including64 wake margin, ReadButtons160, ClearTitle688,
BeginRestore120, first pair1788, PublishScene928 and all branches/setup.
The measured2860 helper bound already includes map restoration and publication;
it must not be added to another map-pair maximum. Visible preparation and
actual integrated VBlank writes still receive independent runtime checks.
The current [JOYP settling correction](JOYP_SETTLE.md) adds48 dots to ReadButtons
and raises that source bound to3968; the historical measurements below remain unchanged.

`python-gs` is the complete short harness: blank plus title frames, no input,
all preparation/publication observations, pause and END. `python-gu` uses one
normal UART Start+Right129 applied at dots136964..138964, before first VBlank.
It checks blank, title and first-world complete frames, the next prepared
world state and its final VBlank publication. Both check every pixel with
sprite-variable timing bounded inside independently numbered456-dot rows,
all23 state bytes at prepared-scene completion, and all display writes only
in VBlank. Input identity, epoch, retirement continuity and exact trace END
are checked. Full literal frame CRCs are b15161f6/6fc2f93a/fa8827ff.

Short pause request is215852; full is286576. Each must actually pause within
1000 dots, before the following frame, without extra pixels. The100ms simulator
watchdog is separate from the300-second whole-process cap. The short completes
before the full run. Forecast short150 and full220 seconds; the affected
actual output-shade fault is forecast110 seconds, with unchanged expectations.
These further checks increased the already declared aggregate target miss;
no individual hard-cap exception was introduced. The python-springtrail and
python-springtrail-x names selected this flow checker until their
[retirement](MILESTONE.md#retired-targets).

The completed composed short/full/fault took136.194/180.803/95.066 seconds.
All11 raw tool/simulator exits were zero in each run. Short and full passed
XML, every pixel, preparation/publication and pause/END; the affected fault
failed XML and the outer command at frame1/index1/dot147281 (shade0 to1).
The full run applied Start+Right at137356 and paused at286976. Its longest
observed display publication ended3828 dots after VBlank began, within the
3920 source bound. All nine scoped simulations total799.887 seconds, above
the ordinary aggregate target; every individual300-second hard cap was met.
Durable results and source qualification belong to [PR276](https://github.com/amichai-bd/nand2mario/pull/276).
These composed targets and their flow checker bind image `97f5d9da...a593b513`
and are [retired](MILESTONE.md#retired-targets); the current image's composed
proofs are the HUD game and pause/restart targets.
