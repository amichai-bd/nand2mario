# Current courier operand proof

The [composition contract](../../../wiki/src/sw/springtrail/COMPOSITION.md)
and [approved courier art](../../../wiki/src/sw/springtrail/CHARACTER_ART.md)
own geometry. The [power contract](../../../wiki/src/sw/springtrail/POWER.md)
owns additional poses. This fixture checks current shared CPU composition,
not gameplay transitions or a rendered full game.

## Frozen operand matrix

Fifty cases use explicit ordinary operands, never expected OAM in the ROM.

| Group | Cases | Operands and obligation |
|---|---:|---|
| Base and power poses |36|Composer IDs0..17, each facing0 and32, small-origin(24,32), visible. Exact approved row-major tile/flag/coordinate order.|
| Piece edges |8|Pose11, alternating facing, origins(-16,32),(-15,32),(-8,-8),(-7,-7),(159,143),(160,144),(256,32),(-264,32). Distinguish entire/partial clipping and signed high-byte rejection.|
| Projection |4|Actual ScenePosition before composition: signed Q4 X4095/camera256 -> -1; X-1/camera0 -> -1; X4112/camera256 ->1; X0/camera256 ->-256. Y-1,-1,511,512 respectively floors to-1,-1,31,32. These are explicit art-origin operands; no implicit collision-box centering.|
| Explicit hiding |2|Poses0/right and17/left at(24,32), SceneHidden1; all piece Y bytes zero while X/tile/flags retain their specified values.|

Each case calls the actual shared ComposeCourier, then the shared
ClearSceneByte entry with A=0 and DE immediately after the courier pieces.
This is the existing zero-tail loop, not SceneTail (which may compose other
entities). Its input pointer remains within C100..C19F. Projection
cases additionally call shared ScenePosition. The oracle derives poses0..11
from editable courier maps and poses12..17 from approved core maps through the
existing independent power_frames courier function. It compares every ordered
byte from C100 through C19F, including zero tail, against those inputs.
The fixture poisons the shadow before the first case; subsequent changes from
six-piece to four-piece output also expose stale tail. The checker rejects
missing, duplicated or reordered writes and unrelated-state writes during the
marked call. Scratch operands and CPU stack are explicitly separated from
preserved game/motion/power/progression state.

## Execution and binding

Use three bounded full groups: poses0..8 (18), poses9..17 (18), and all14
edge/projection/hidden cases. A one-case short uses the same completion,
ordinary HALT, stable hold, epoch/retirement and END checks before full runs.
The negative changes an actual first courier tile store with the unchanged
oracle, and must fail at that byte; setup errors are not sensitivity evidence.

Source and linked non-fixture section hashes must agree with the current game.
The historical composition builder guard remains unchanged. The entity work
may add a capacity guard to the shared composer; final qualification and
execution bind the merged version rather than claiming earlier inputs current.
No assets, mechanics or hardware behavior change here.

Initial plan: short plus three full groups plus one fault, each total wall
limit300s, aggregate ceiling1500s. Target120s per run. Exact static dot ceilings
and measured short throughput must be recorded before full execution; this is
not an allowance increase or a claim that the initial forecast has passed.
The entity acceptance queue has priority. New targets use the existing Intel
preload, continuous UART driver, transitive-input validator and catalogue.

Remaining acceptance: encoded fixture/shared-section qualification, literal
oracle guards, short/full/fault actual receipts, owning catalogue/docs and
required checks, then independent current-head review. Host equality alone
never establishes actual CPU execution.
