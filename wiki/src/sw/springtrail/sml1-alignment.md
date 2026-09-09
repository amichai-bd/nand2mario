# Staged SML1 alignment

This page owns the next Springtrail release direction and explicitly tracked
implementation gaps. The [game specification](SPEC.md) describes current behavior.

## Scope and evidence

Align the architecture and observable mechanics with **Super Mario Land 1**,
using original SM83 code, characters, assets and levels. NES Mario and SML2 are
not substitute references. Do not copy commercial code, pixels, maps, addresses
or incidental instruction sequences. Audio remains excluded.

Research is pinned to kaspermeerts/supermarioland revision
`618d00ed6c330928e106719533c6e294ae5d5726`:
[bank0.asm][bank0] and [enemies.asm][enemies]. Read these externally; do not
vendor or rebuild them. A routine label locates evidence, not a complete
behavior specification. Source-confirmed structure is distinguished below from
unmeasured constants and uncertain annotations. Each dependent issue must freeze
its reference identity, diagnostic inputs and expected observable results before
implementation. Confirm uncertain comments independently; never infer expected
values from the new DUT. There is no invented percentage of reference fidelity.

## Divergence matrix

Current paths are under [src/sw/springtrail](../../../../src/sw/springtrail).
Confidence applies to the reference observation, not to future implementation.

| Area | Current implementation | Pinned reference locator and confidence | Original replacement and acceptance owner |
|---|---|---|---|
| Character composition | `scene.asm` builds nine 8x16 objects; `main.asm` selects that global object mode | `bank0.asm` sprite paths; geometry/anchors need measurement | [#292](https://github.com/amichai-bd/nand2mario/issues/292): 8x8 pieces, whole-pose mirroring, clipping and object limits; preserve approved art and current collision until its owner changes it |
| Publication | `PublishScene` transfers the complete C100 shadow page through HRAM DMA; preparation builds nine entries and clears the tail | `VBlank`, `DMARoutine`, initialization HRAM copy: source-confirmed DMA organization | [Publisher proof](../../../../src/dv/springtrail/OAM_DMA.md); #292 still owns variable composition |
| HUD and scrolling | `stream.asm`, `world.asm`, `map_restore.asm`, `scene.asm`: raw columns, inactive-map restoration and object HUD | `DrawColumn`, `VBlank`, `LCDStatus`: source-confirmed organization; exact visible boundary unmeasured | [#300](https://github.com/amichai-bd/nand2mario/issues/300): original column encoding and fixed top HUD, STAT playfield scroll; freeze coordinate and publication schedule against qualified hardware |
| Movement and animation | `movement.asm`, `collision.asm`: immediate walk/run speed, fixed jump/gravity, no integrated walk cycle | `Call_1D26`, `Call_16F5`, `Call_1736`: state/cycle paths; numeric response unmeasured | [#301](https://github.com/amichai-bd/nand2mario/issues/301): measured start/stop/reverse, jump edges/hold/air control, collisions and pose cadence |
| Player contact and power | `interactions.asm`: contact death, one player size | `bank0.asm` player/contact paths and `enemies.asm` states: behavior table pending | [#302](https://github.com/amichai-bd/nand2mario/issues/302): stomp/damage precedence, growth/shrink, protection, invincibility and projectile power; freeze boxes and durations |
| Blocks and rewards | `collision.asm`, `interactions.asm`: solid terrain and four once-only pickups | `Call_1B86`, `AddScore`: source locators; category/reward rules pending | [#303](https://github.com/amichai-bd/nand2mario/issues/303): original mutable blocks, head hits, releases and persistent consumed state; coordinate power/entity/reward owners |
| Progression | `interactions.asm`: retry restores all state, one finish marker; no lives/timer | `UpdateLives`, `DisplayTimer`, level-state paths: source locators; survival/reset rules pending | [#304](https://github.com/amichai-bd/nand2mario/issues/304): measured lives/timer/death/continue/level transitions using minimal original levels |
| Entities | `StepEnemy` patrol; stationary terrain platforms | `enemies.asm` platform/stomped/falling entries: classes identified, dynamics unmeasured | [#305](https://github.com/amichai-bd/nand2mario/issues/305): bounded patrol, hazard, moving and falling platform classes; define spawn/despawn, contacts and exhausted capacity |
| Storage | Mapperless 32768-byte `dmg-direct-v1` image | `bank0.asm` header declares four banks/MBC1; source-confirmed | Preserve baseline; [#307](https://github.com/amichai-bd/nand2mario/issues/307) separately owns 64 KiB MBC1/no-RAM profile and loader/fit qualification; no automatic renderer dependency |

## Release order and shared contracts

The **first aligned release includes composition, DMA publication, HUD, movement,
interactions, blocks, progression and entities**,
in these three stages. An intermediate stage is not completion of that release.

1. Reuse qualified combined 8x8-object, HRAM DMA and STAT behavior with original
   diagnostic patterns and the [publisher proof](../../../../src/dv/springtrail/OAM_DMA.md).
   Integrate composition #292 and HUD/column scheduling #300. Existing RTL is not presumed defective; any actual
   violation belongs in a focused hardware bug with its owning contract.
2. Freeze and implement measured movement/animation #301 against those explicit
   display coordinates. Coordinate size/contact contracts with #302.
3. Deliver all core interaction, block, progression and entity scopes #302-#305.
   Agree shared state ownership before dependent code, rather than creating
   circular implementation waits. Additional families, bosses, bonus and vehicle
   stages remain the separate [#306 inventory](https://github.com/amichai-bd/nand2mario/issues/306).

The [approved art](CHARACTER_ART.md) fixes original small 16x16 and large 16x24
canvases. These are not measured SML1 dimensions. #292 defines logical anchors,
piece offsets, facing and screen clipping independently of collision boxes;
#301/#302 own those boxes and power transitions. New art needs approval; already
approved art does not. Record intentional geometry differences without changing
approved pixels to satisfy an assumed reference size.

The approved tile IDs are local asset indices; #292 owns VRAM allocation and
preserves shade/palette ordering. Mirroring reflects piece positions as well as
tile attributes. Use approved poses where suitable; #301/#302 request only
necessary missing skid, crouch, growth or projectile visuals. Missing art gates
its dependent visual integration, not independent physics measurement.

HUD/column integration must reuse one publisher and freeze input sampling, prepared-scene
ownership, DMA completion and IRQ ordering. Preserve the current once-per-frame
game update and approved one additional displayed frame unless an explicit
measured contract revision authorizes a change. Current `DI`/`HALT`/IF polling
does not imply ISR equivalence. Do not lose an update or interrupt while changing
dispatch. #300 reserves the planned 16-pixel HUD but must define its world-to-screen
offset and exact visible split against qualified hardware before calibrating motion. Copying an
LCDC byte would also change tile addressing and map selection; qualify each bit.

Keep the 25 MHz system, DMG dot/frame cadence and standard JOYP interface. ROM
banking is separate: remain within 32 KiB until a demonstrated storage need and
the reviewed #307 memory/loader/packager/fit contract permit a banked image.

## Shared asset checklist

The feature owners below track remaining asset integration. Reuse suitable approved sources; create only missing original
content required by that issue. This adds no feature families or asset framework.

| Owner | Scoped content to account for |
|---|---|
| #292 | Approved courier tiles and pose maps in [CHARACTER_ART.md](CHARACTER_ART.md); composition and game allocation |
| #300 | Terrain/column tiles and fixed HUD graphics |
| #301 | Motion poses, reusing approved poses where suitable; identify any missing state visuals |
| #302 | Power, damage and projectile visuals; identify missing transitions separately from approved courier poses |
| #303 | Interactive blocks, released items and pickups |
| #304 | Progression displays and original fixture maps |
| #305 | Selected enemy, hazard and moving/falling-platform art |
| #306 | Later-content inventory only; no core-release asset implementation |

Each owning specification records a compact list with visible state/use,
existing source to reuse or missing asset to create, exact tile/pose/map source
path, and approval/integration status. Keep editable integer shade grids and
pose/map data with the implementation owner. Render tile sheets and assembled
SVG previews from those values using repository tools, showing 8x8 boundaries
and IDs where useful. Link the preview from both the owning wiki specification
and issue; the editable values remain authoritative.

Unchanged courier art remains approved. Before integrating newly created or
materially changed game artwork, obtain visual approval tied to its exact source
revision and rendered preview. Approval gates only that artwork's integration:
continue independent code and tests while it is pending. Diagnostic placeholders
are not approved final game art. Pose timing, collision geometry and feature
behavior remain separate contracts.

Each feature packages and uses its required assets, checks tile/palette/placement
references, and supplies a short independent rendered-state proof against the
approved appearance. Reuse suitable existing checks. Artwork alone does not
require a full-game replay, another FPGA build or longer simulations; the
existing budgets still apply. This documentation contract creates no assets.

## Baseline and bounded acceptance

### First aligned release matrix

Completion requires all rows below for one identified final original ROM.
Child completion alone does not establish composed FPGA behavior.

| Capability | Required evidence |
|---|---|
| Composition, publication, HUD/scroll | Qualified combined hardware diagnostic and publisher proof plus #292/#300 proofs of object limits, DMA/IRQ ordering, split pixels and column boundaries |
| Motion and poses | #301 independent per-update state/pose cases, including direction changes, jump and collision transitions |
| Interactions and world state | #302/#303/#305 contact/power/block/entity cases, persistence and player/platform interactions |
| Progression | #304 life/timer/death/retry/level-transition cases and their shared HUD/state ownership |
| Final build and FPGA composition | Reproducible clean ROM builds with exact hashes, full UART upload/readback, and independently expected source-frame/gameplay checkpoints exercising the changed capabilities above on a qualified FPGA build |

Before that final run, freeze the smallest deterministic original input script,
checkpoint expectations, relevant faults, evidence-reuse qualification and total
budget in the game DV plan. Account for all required capabilities using valid
child evidence plus affected composed checks; do not invent a frame quota or
repeat the old full baseline automatically. Retain actual results and safe
completion. This is FPGA source-frame/gameplay acceptance, not a substitute for
the separate physical monitor/control gates.

The [complete-game baseline](../../dv/springtrail/SPEC.md#v09-milestone)
qualifies only its identified ROM, rules and images. Approved art does not
establish game integration. Retain qualified evidence for unchanged behavior;
changed state, timing or pixels require new independent expectations, not a
relabeled old result.

Follow the [game DV plan](../../dv/springtrail/SPEC.md) and
[verification tiers](../../dv/integration/SPEC.md#verification-tiers). Each child
freezes a small deterministic script covering its distinct transitions, exact
state/pixel checks, meaningful affected faults and completion/failure handling.
Run the complete harness briefly before expensive acceptance. Target 120 seconds
per simulation and 300 seconds ordinary aggregate; each simulation has a
300-second total hard bound including setup, build, run, check and cleanup.
Declare broader milestone aggregates before execution and measure FPGA builds
separately. Reuse qualified evidence and sampled continuous endurance; neither
3600 frames nor a new multi-hour replay is an automatic child prerequisite.

Physical VGA/control and release gates remain open in
[#28](https://github.com/amichai-bd/nand2mario/issues/28),
[#156](https://github.com/amichai-bd/nand2mario/issues/156) and
[#264](https://github.com/amichai-bd/nand2mario/issues/264). They gate their own
claims, not independent software, DV or UART work. This contract does not claim
hardware acceptance, full SML1 coverage or a complete physical release.

[bank0]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/bank0.asm
[enemies]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/enemies.asm
