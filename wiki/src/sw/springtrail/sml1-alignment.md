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
| Character composition | `courier.asm` composes all twelve approved maps as global 8x8 pieces | `bank0.asm` sprite paths; original anchors are defined in [composition](COMPOSITION.md) | Composition and motion cadence implemented; runtime size behavior remains in its separate row |
| Publication | `PublishScene` transfers the complete C100 shadow page through HRAM DMA; preparation builds sixteen entries and clears the tail | `VBlank`, `DMARoutine`, initialization HRAM copy: source-confirmed DMA organization | [Publisher proof](../../../../src/dv/springtrail/OAM_DMA.md) and current [composition](COMPOSITION.md) |
| HUD and scrolling | `stream.asm` prepares original encoded columns; `hud.asm` publishes background mode/score and separates HUD/playfield with VBlank/STAT | `DrawColumn`, `VBlank`, `LCDStatus`: source-confirmed organization, not a copied timing oracle | [HUD/column contract](HUD_COLUMNS.md) and its bounded pixel/publication matrix |
| Movement and animation | `movement.asm`, `collision.asm`: counter/phase motion, jump profiles and stored walk/jump/skid poses | `Call_1D26`, `Call_16F5`, `Call_1736`: source-derived state/cycle rules; complete normal dispatcher unavailable | [Movement contract](MOVEMENT.md): approved original best-effort order/profile binding, literal per-update expectations and explicit reference limits |
| Player contact and power | `power.asm`, `interactions.asm`: invincible/stomp/hit classes, small/large/thrower states, GROW/HURT/SAFE windows, crouch and one bouncing shot | `Call_84E`, `InjureMario`, `Call_1F03`: source-confirmed test order, box adjust and star value; durations and dispatcher binding unavailable | [Power contract](POWER.md): approved original choices, literal cases and explicit reference limits; pickups that call `PowerUp`/`GrantStar` remain with #303 |
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
   Reuse current [composition](COMPOSITION.md) and [HUD/column scheduling](HUD_COLUMNS.md). Existing RTL is not presumed defective; any actual
   violation belongs in a focused hardware bug with its owning contract.
2. Reuse the [movement/animation contract](MOVEMENT.md) against those explicit
   display coordinates. Its best-effort original choices do not establish full
   reference equivalence. Coordinate size/contact contracts with #302.
3. Deliver all core interaction, block, progression and entity scopes #302-#305.
   Agree shared state ownership before dependent code, rather than creating
   circular implementation waits. Additional families, bosses, bonus and vehicle
   stages remain the separate [#306 inventory](https://github.com/amichai-bd/nand2mario/issues/306).

The [approved art](CHARACTER_ART.md) fixes original small 16x16 and large 16x24
canvases. These are not measured SML1 dimensions. [Composition](COMPOSITION.md) defines logical anchors,
piece offsets, facing and screen clipping independently of collision boxes;
The [movement contract](MOVEMENT.md) preserves the current 8x16 collision box;
the [power contract](POWER.md) keeps that terrain box for every size and adds
a 2-pixel contact-box lift for standing large players. New art needs approval; already
approved art does not. Record intentional geometry differences without changing
approved pixels to satisfy an assumed reference size.

The approved tile IDs are local asset indices; [composition](COMPOSITION.md) defines VRAM allocation and
preserves shade/palette ordering. Mirroring reflects piece positions as well as
tile attributes. Current movement reuses approved walk/jump and small skid art; power states
reuse approved hurt, crouch, throw, large skid and shot pixels without new
art. Missing art would gate only its dependent visual integration, not
independent physics measurement.

HUD/column integration reuses one publisher and binds input sampling, prepared-scene
ownership, DMA completion and IRQ ordering. Preserve the current once-per-frame
game update and approved one additional displayed frame unless an explicit
measured contract revision authorizes a change. The real VBlank token wait ignores
STAT-only wakes; DMA masks IME without clearing pending IF. The
[HUD contract](HUD_COLUMNS.md) defines the top16 pixels, unchanged world y and
bounded HBlank split before line16. Copying an LCDC byte would also change tile
addressing and map selection; qualify each bit.

Keep the 25 MHz system, DMG dot/frame cadence and standard JOYP interface. ROM
banking is separate: remain within 32 KiB until a demonstrated storage need and
the reviewed #307 memory/loader/packager/fit contract permit a banked image.

## Shared asset checklist

The feature owners below track remaining asset integration. Reuse suitable approved sources; create only missing original
content required by that issue. This adds no feature families or asset framework.

| Owner | Scoped content to account for |
|---|---|
| [Composition](COMPOSITION.md) | Approved courier tiles and pose maps in [CHARACTER_ART.md](CHARACTER_ART.md); current composition and game allocation |
| [HUD/columns](HUD_COLUMNS.md) | Existing terrain, selected approved font tiles and fixed HUD previews |
| [Movement](MOVEMENT.md) | Approved base walk/jump poses and core small skid; stored pose/facing and cadence |
| [Power](POWER.md) | Approved core hurt, crouch, throw, large skid and shot tiles at VRAM 98..107; no new art |
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
| Composition, publication, HUD/scroll | Qualified combined hardware diagnostic, publisher, [composition](COMPOSITION.md) and [HUD/column](HUD_COLUMNS.md) proofs, including split pixels and column boundaries |
| Motion and poses | [Movement matrix](../../../../src/dv/springtrail/MOVEMENT.md): independent per-update state/pose cases, including direction changes, jump and collision transitions |
| Interactions and world state | [Power matrix](../../../../src/dv/springtrail/POWER.md) plus #303/#305 block/entity cases, persistence and player/platform interactions |
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

The physical VGA and release gate remains open in
[#28](https://github.com/amichai-bd/nand2mario/issues/28). It gates its own
claims, not independent software, DV or UART work. Physical controls are out
of scope under the [remote working scope](../../../preflight-gaps.md#remote-working-scope). This contract does not claim
hardware acceptance, full SML1 coverage or a complete physical release.

[bank0]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/bank0.asm
[enemies]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/enemies.asm
