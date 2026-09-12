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

Use seven consecutive full groups of 8/8/8/8/8/8/2 rows, preserving the
complete ordered matrix without omissions or duplication. A one-case short uses the same completion,
ordinary HALT, stable hold, epoch/retirement and END checks before full runs.
The negative changes an actual first courier tile store with the unchanged
oracle, and must fail at that byte; setup errors are not sensitivity evidence.

Source and linked non-fixture section hashes must agree with the current game.
The historical composition builder guard remains unchanged. The entity capacity guard is included in current source qualification;
pre-entity receipts are not current execution evidence.
No assets, mechanics or hardware behavior change here.

The initial five-run plan used 18/18/14 full groups. Its complete short passed
in 45.047 seconds (44.781 supervisor seconds), at 22,671 paused dots. This
measurement does not support 18-case execution inside 300 seconds. The revised
batch has short, seven full groups and one fault: 2,700 seconds aggregate
ceiling, including the completed short, with each run still capped at 300.
Target 120 seconds per run. No per-target allowance is increased. The conservative
8-case source forecast below is about 256 seconds using the entire short wall
per dot; it is a forecast, not acceptance. Shared serialized access remains.

Remaining acceptance: encoded fixture/shared-section qualification, literal
oracle guards, short/full/fault actual receipts, owning catalogue/docs and
required checks, then independent current-head review. Host equality alone
never establishes actual CPU execution.

## Fixture and checker ceilings

The operand ROM seeds C000..C0EF with a nonzero sentinel once, then poisons all
160 shadow bytes. Each call seeds ten input bytes and copies explicit ObjectX/Y
operands; no expected output is present in its ROM. The checker records all
writes during the call, rejects writes outside the OAM page, named composer
scratch and bounded stack, and preserves all other initialized state bytes.
The inherited trace checker still enforces retirement order/epoch, terminal
HALT and exact END count; the shared runner supplies the settled pause.

The current source gives conservative call terms: at most six pieces, each
with EmitPiece620 plus courier overhead296; setup220; projection500; zero-tail
at most144 bytes times52; marker/dispatch200. Sum13904 is below16000 dots per
marked call. The 620-dot reservation exceeds the current maximum of 528, including capacity
checking. The three initialization loops and their setup fit 12,000 dots.
Per-case input/setup is below 600; terminal/control reserve is 1,000. Eight
calls fit 12000+8*(16000+600)+1000=145800 below150000 dots; the tighter
13904-dot call bound gives129032 dots, about256 seconds at measured short
throughput. One short fits29600 below40000.
These are source ceilings, not elapsed-time forecasts or observed results.

## Current integration

The merged entity profile retains all 50 rows. Each fixture links all 21 shared
sections against the current game and initializes the 56 persistent entity bytes
at C300..C337 as additional unrelated-state operands. The checker rejects writes
to those bytes during composition. EmitPiece's current maximum of 528 dots fits
the conservative 620-dot reservation above. The extra initialization costs 1368
dots and remains inside the 12,000-dot setup reservation.

`python-courier-short`, `python-courier-a`, `python-courier-b`, and
`python-courier-c` through `python-courier-g` use the shared continuous unit runner, including ordinary HALT,
settled hold, exact END accounting, and bounded completion. Their cocotb watchdogs
are 40 ms for short and 60 ms for full, outside the 40,000/150,000-dot guards.
`python-courier-fault` uses the same short image and checker. Its one-shot hook
changes the actual first C102 CPU output from tile 42 to zero after the call
marker; the real memory write and passive write ledger consume that output.
The required failure is COURIER_OAM, with the mutation receipt retained.
