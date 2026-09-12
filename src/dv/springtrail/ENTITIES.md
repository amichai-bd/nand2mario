# Four-class entity proof

Pending implementation of the [entity contract](../../../wiki/src/sw/springtrail/ENTITIES.md).
All four classes are required. This is software/model/publication verification,
not physical acceptance or replacement of unrelated open operand matrices.

## Frozen state witnesses

All coordinates below are pixels unless Q4 is explicit. Each CPU case seeds
ordinary WRAM operands, executes current shared routines and compares complete
entity/player/power/progression state plus ordered shadow output when requested.
Expected values are calculated before execution from this contract, not reports.

| Rule | Literal independent witness |
|---|---|
| Patrol endpoint | Existing stage0 right edge296, x295.5/vx+0.5 ->296/vx-0.5; the next update295.5 |
| Patrol stomp | Overlapping player top105, enemy top120 -> alive0, jump1/index13, countdown16; after8 subsequent updates countdown8/STOMP2; after16 hidden |
| CURL range | x328, player-left295 -> dormant; player-left296 -> active32; active1 -> cooldown32/dormant; cooldown1 -> cooldown0 without retrigger |
| CURL contacts | Active overlap + small -> RETRY; protected hurt -> unchanged life/power; invincible -> absent; stomp/shot alone do not remove CURL |
| Moving boundary | x207/vx+1 ->208/vx-1; next207; x176/vx-1 ->176/vx+1 |
| Carry | Supported player x184/y96 on platform x176/y112 -> x185/y96 after+1 carry with neutral input; accepted jump detaches with no inherited x delta |
| Landing | Old player bottom111, new113 across top112 -> y96/grounded1; upward crossing or half-open x overlap at exactlyrightedge does not land |
| Carry collision | Wall-clamped carry does not pass through terrain, clears rider; evaluate normal player movement independently afterward |
| Falling trigger | First landing at y112 -> armed16/no y change; armed1 -> falling/y114; falling top142 -> absent at144, rider released |
| Persistence | Dead patrol/absent fall remain absent after offscreen/re-entry; stage entry restores all slots; pause freezes timers/positions |
| Capacity | Invalid slot4 and spawn into live slot leave record/canary bytes unchanged; emission at OAM40 writes nothing; unused tail remains zero |
| Interaction order | Fall death precedes hazard/items/goal; shot/power/blocks retain their owned state; platform contact runs before fall death |

Seed each distinct branch instead of replaying long trajectories in RTL. Full
host-model trajectories cover countdown lengths and all three stage placements.
Host tests also decode every selected approved pose and both facing reflections.

## Pixel/publication witnesses

Independent literal tile remap: source0..10 -> VRAM149..159; source19..32 ->160..173.
WALK1 pieces149,150,151,152; WALK2 149,150,153,154; STOMP1 155,155,156,157;
STOMP2 155,155,158,159; CURL dormant160..163, active164..167; platform solid
168,169,170; crack1 168,171,170; crack2 172,173,170. OAM X/Y encoding and all
160 shadow/DMA bytes must match independent complete expectations.

Use two compact original fixed renderer scenes with player and all classes at
nonoverlapping visible positions: normal patrol/dormant CURL/solid platforms,
then stomp/active CURL/moving endpoint/cracked falling platform. Compare every
retained pixel, all selected tile bytes, exact source epoch/sequence, both DMA
publications, unchanged HUD split and terminal settled pause. Include signed
camera edge, y15/16 clipping and priority/exhaustion in seeded CPU/host cases;
no claim of all possible compositions. A real accepted entity-state store or
OAM tile write mutation must make the unchanged oracle fail at a fixed witness.

## Minimal run plan

Reuse motion_program/motion_unit_check and the current renderer/Intel preload
path. Register dedicated short/entity-full/entity-fault wrappers through existing
builders, not a new runner. Expected commands after registration:

- `python tools/build.py sw build springtrail --tag e305 --json`
- `python -m unittest discover -s src/dv/springtrail -p test_entities_reference.py -v`
- Existing ROM-bound state decoder tests, with the current built image and new fields.
- `python tools/build.py sim test python-entities-short --tag es305 --json`
- `python tools/build.py sim test python-entities-unit --tag eu305 --json`
- `python tools/build.py sim test python-entities-fault --tag ex305 --json`
- Dedicated bounded renderer short/full targets using the existing renderer driver;
  final names, source dot bounds and exact completion are frozen before launch.

No simulation launched yet. Target120seconds/300hard per new simulation including
setup/build/check/cleanup; no inherited304exception. Provisional six-run ceiling
1800seconds is a declared feature aggregate, not a forecast or completed evidence.
Measure one complete short harness first, including settled end and supervisor,
then derive full bound/forecast from actual throughput and finite instruction paths.
Do not replay unchanged whole historical suites. Required host/wiki/policy checks
and every affected current target/profile must remain coherent.

## Remaining-to-merge checklist

- [x] Contract and independent literal state/art matrix reviewed before product code.
- [ ] All four classes in ordinary three-stage game, safe slots/OAM/WRAM and32KiB fit.
- [ ] Early current ROM/state decode/render profile qualification; fail closed otherwise.
- [ ] Pure model/asset/host negatives and complete short/full CPU/pixel/fault evidence.
- [ ] Visible preparation and retained4480-dot publication bound qualified on current code.
- [ ] Editable assets/previews, current owning docs/catalogue/inputs aligned.
- [ ] Required checks, exact-head independent review and normal delivery.

## Current finite execution mapping

The accepted short executes `neutral-carry` through shared UpdateGame and checks
all123 player, power, block, progression and entity bytes, including reserved
zeros. It finished in44.108seconds at paused dot21832 (routine16092dots,
2252retirements), with HALT, settled hold and exact END count. This is short
harness evidence only. Its producing commit is13abae2; later fixed-slot helper
addition changes link addresses, not that executed routine path.

`entities_cases` now divides40 named cases into eight five-call batches. Each
uses the same complete state encoder/checker. The coarse ceiling per call is
6000dots for123-byte seeding and dispatch plus24000 for the routine; five calls
and terminal give151000dots, guarded at160000. This is a conservative test
ceiling, not a claim about visible preparation. Based on short throughput, allow
180-270seconds per five-call batch including setup; the hard cap remains300.
Measure each batch and stop on failure. No larger304 allowance applies.

| Criterion | Named CPU cases / retained independent witness | Remaining gap |
|---|---|---|
| Carry/support/jump/half-open landing | neutral-carry, jump-off, landing, right-edge-no-land | blocked fractional carry needs isolated actual-routine case |
| Moving endpoints | moving-right, moving-return, moving-left | none in state matrix |
| Falling lifecycle | fall-arm, fall-delay, fall-start, fall-absent, fall-stays-absent; full offscreen trajectory host test | rider-released-at-absence supplied; execution pending |
| CURL trigger/cooldown/contact | curl-outside, curl-range, curl-active-end, curl-cooldown-end, curl-small/large/protected/star | curl-stomp-immune, curl-shot-immune, patrol-stomp-before-curl / patrol-before-curl-fatal supplied; execution pending |
| Patrol animation/stomp | patrol-stomp, stomp-second-pose, stomp-hidden, patrol-endpoint | full OAM pose checks below |
| Pause/reset/stages | pause-freeze, resume, select-reset, full-reset, enter-stage1/enter-stage2 via actual WON transition | execution pending |
| Fixed slot protection | invalid-slot, live-curl-no-overwrite, live-patrol-no-overwrite, spawn-curl, spawn-falling | OAM40 and adjacent-canary emission proof |
| Current host observation | source-built decoder3 records,17 reader tests; same-position phase regression and default-win tests | complete affected host results pending |
| Full scene/publication | independent entities_frames uses174 selected tiles and all160 OAM bytes | actual ordered OAM, two fixed pixel scenes, DMA, fault and timing proofs remain |

Eight CPU batches plus the retained short provisionally allow2700seconds at the
hard per-run cap. Additional OAM/renderer/fault runs will have exact finite
commands and an updated aggregate before launch; the earlier six-run1800second
ceiling was a planning estimate, not authorization for longer individual runs.

The first five batches passed25 state cases in533.914743seconds. The initial
sixth batch failed at ordinary resume (25.404seconds): its oracle incorrectly
expected NewLevel1. The preserved resume contract keeps NewLevel0; the oracle
is corrected without product changes. Real WON-to-stage1/2 operands replace
model-initialized stage-update-only operands. Host tests bind both distinctions.
Only the affected sixth batch is repeated; previous positive batches are reused.


## Final finite queue and measured allowance

The state matrix has41 cases in nine batches. The last case uses ordinary
UpdateGame with a rider at x361/y112 and a falling platform at x368/y128.
The platform advances to y130; terrain rejects the carry, leaving the player at
x361/y112 and rider zero. This checks blocked carry without a product test hook.

The complete renderer short reached settled pause186626 and finish in218.336
seconds. Its original raw result is FAIL: the upload oracle incorrectly expected
zero bytes in unused legacy tiles1..15. The fixture loaded the approved source
correctly. The corrected upload oracle reads those original assets; the pixel
oracle and fixture image remain unchanged. A retained-trace replay qualifies the
correction separately and never changes that original result.

The full normal/changed fixtures end by326492/326588 dots. Proportional measured
forecast is382 seconds each, so only these two targets declare420-second total
wall allowances under the current builder policy. Independent budget review is
required before launch. All CPU, OAM and fault targets retain300 seconds.
Nine CPU batches plus short, four OAM runs (short plus three two-case parts),
renderer short plus two full scenes and one state fault give5640 seconds in
maximum planned allowances;6000 seconds includes the retained setup/oracle
failures. This feature aggregate is not a per-target allowance.

The fault target reuses the accepted neutral-carry short and changes one actual
C310 WRAM store from16 to0 after the first call marker. It must fail the unchanged
complete state oracle because the platform step and resulting carry are lost.
This is the required entity-state fault, separate from both full pixel positives.
