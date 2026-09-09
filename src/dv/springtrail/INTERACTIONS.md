# Interaction proof

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

The model/routines can be checked independently of the frame-loop scheduling
decision. They are linked into the game image, but are not yet called by its
frame loop. No added display latency has been implemented or accepted here.

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

Before measurement, forecast the three-report smoke at 20â€“40 seconds and full
unit at 90â€“140 seconds. A later composed game/fault pair is provisionally
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

`map_restore.asm` is linked but not called by the current frame loop.
`BeginMapRestore` selects static9800, clears SCX/history and restarts column0;
`RestoreMapPair` writes two complete18-row columns into9C00. The final pair
selects9C00 only after column31's final write. Other LCDC bits are preserved.
The future caller must invoke these routines only during VBlank and ensure
static9800 is the restored initial view. Streaming must never modify9800.

Instruction counting gives Begin96 dots and each column792 dots including
RET. The pair takes1764 dots normally or1800 on its final switch, excluding
the caller's24-dot CALL. These are source counts, not measured execution.
The two-column plus OAM/HUD bound, map equality, repeated partial restart and
pause behavior still require the combined renderer proof before activation.

## Scene preparation boundary

`PrepareScene` writes36 ordinary WRAM bytes at C100 for nine OAM entries:
player, enemy, four items, goal, score and mode. It is not called by the frame
loop yet. Signed coordinate flooring and camera subtraction precede byte
encoding; fully off-screen or collected objects use OAM Y0. Score and mode
are screen-relative at (144,0) and (72,0). `scene_reference.py` owns the
independent expected bytes, including a literal initial scene and clipping
at x=-8/-7 with fractional Y.

The original tile pairs are player12, enemy16, item18, goal20,
score22+2*score and mode32+2*mode. The new art pairs are installed in the atlas; the OAM publisher is linked
but not called by the live loop. Lower tiles are blank for eight-pixel objects.
The original16 tiles are unchanged. No extra display frame is active.
Actual CPU scene/map byte and combined VBlank budget checks remain pending.

The static and scrolling maps contain terrain and title lettering only; item
and old fixed-counter background markers have been removed. Items and score
will use OAM. New atlas and restored full pixels remain pending checks.

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

Before measurement, forecast short50–70 seconds, full120–180 and fault30–50,
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
