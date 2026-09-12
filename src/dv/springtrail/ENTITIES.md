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

- [ ] Contract and independent literal state/art matrix reviewed before product code.
- [ ] All four classes in ordinary three-stage game, safe slots/OAM/WRAM and32KiB fit.
- [ ] Early current ROM/state decode/render profile qualification; fail closed otherwise.
- [ ] Pure model/asset/host negatives and complete short/full CPU/pixel/fault evidence.
- [ ] Visible preparation and retained4480-dot publication bound qualified on current code.
- [ ] Editable assets/previews, current owning docs/catalogue/inputs aligned.
- [ ] Required checks, exact-head independent review and normal delivery.
