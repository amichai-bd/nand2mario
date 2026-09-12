# Approved core game artwork

Status: the user approved every displayed core review sheet on 2026-09-09.
This page extends the [courier reference](CHARACTER_ART.md). All designs are
original project shade grids. The images are scripted review compositions,
not game screenshots or evidence of implemented mechanics.

## Editable sources

The asset owner is [src/sw/springtrail/assets/core](../../../../src/sw/springtrail/assets/core/core-maps.json).
Each group has a one-row 8x8 tile atlas and a named placement map:

| Group | Tile pixels | Asset dimensions and placement |
|---|---|---|
| Actions, effects, font, UI | [core-tiles.json](../../../../src/sw/springtrail/assets/core/core-tiles.json) | [core-maps.json](../../../../src/sw/springtrail/assets/core/core-maps.json) |
| Terrain, blocks, items, scenery | [terrain-tiles.json](../../../../src/sw/springtrail/assets/core/terrain-tiles.json) | [terrain-maps.json](../../../../src/sw/springtrail/assets/core/terrain-maps.json) |
| Enemies and platforms | [enemies-tiles.json](../../../../src/sw/springtrail/assets/core/enemies-tiles.json) | [enemies-maps.json](../../../../src/sw/springtrail/assets/core/enemies-maps.json) |

Pixels are integer shade indices 0..3. Each tile occupies 16 encoded bytes.
Map `width` and `height` describe the full image; each `pieces` entry has an
8-aligned `x,y` placement and a zero-based `tile` index in that group's atlas.
Absent flip flags mean false; explicit `x_flip,y_flip` apply within a tile.
Every image includes a placement for each 8x8 cell, including blank cells.
The twelve original courier poses are reconstructed from their existing owner.
These review bank IDs are not allocated ROM sections or VRAM tile IDs. Banks
remain independent; their union need not be resident simultaneously.

## Approved views and integration owners

### Player actions

![Additional player actions](core-art/player-actions.svg)

Small and large skid, throw, hurt and crouch designs supplement the original
poses. [Composition](COMPOSITION.md) owns character assembly;
[movement and animation](MOVEMENT.md) integrates the approved small skid
from core tiles16..19 as runtime tiles94..97 and composer pose12; the
[power contract](POWER.md#visible-poses) integrates large skid, hurt, crouch,
throw and the shot tile from core tiles21..26, 43..45 and54 as runtime tiles
98..107 and composer poses13..17. Small crouch and small throw remain approved
artwork without an owning mechanic. Visual approval does not choose collision anchors,
state transitions, frame cadence or optional mechanics.

### Terrain, blocks, items and scenery

![Terrain, blocks and items](core-art/terrain-items-review.svg)

The current [HUD/column renderer](HUD_COLUMNS.md) preserves the existing terrain
bank and selects approved core glyphs; it does not replace terrain with this
entire review sheet. The [block contract](BLOCKS.md) integrates the sealed,
used, crack, reveal, shards, coin, leaf and gem designs from terrain tiles
10..33 and 38..45 as runtime tiles 108..139. The scene below also shows the
cloud, bush and arch sources. Water/spike and the remaining pickup designs do
not authorize additional mechanics.

### Enemies and platforms

![Enemies and platforms](core-art/enemies-platforms-review.svg)

The historical DRAFT caption is preserved to match the exact approved image;
this page records its approval. The [entity contract](ENTITIES.md) selects25
tiles from atlas indices0..10 and19..32 as runtime tiles149..173 for patrol,
CURL and moving/falling platforms. It owns state selection, spawning and contacts. Tile gutters
and labels are review overlays, not game pixels.

### Effects, icons and text

![Effects and interface icons](core-art/effects-icons.svg)

![Original font](core-art/font-tiles.svg)

These supply dust, sparkle, projectile, life/heart/clock and uppercase letter,
digit and dash designs. The core map also includes the full HUD composition.
The current [stationary HUD](HUD_COLUMNS.md#reference-previews) integrates twenty
unchanged uppercase/digit glyphs for mode and score. That page owns exact VRAM
allocation and assembled reference previews; the larger approved HUD composition
and remaining icons do not imply life, timer or power mechanics are implemented.
Shade zero is transparent for objects but is a visible palette index for
background/window tiles. The review tool's checkerboard is only an inspection
convention; UI screens and the assembled scene show background zero as white.

### Progression screens

![Progression screen designs](core-art/progression-screens.svg)

The [progression contract](PROGRESS.md) owns progression-state integration. It
takes the wording of these designs into the existing HUD word and adds the
life and clock icons with digits5..9 to the HUD's second row; the full-screen
compositions remain approved artwork. The title and
pause designs are also available to existing UI owners; this approval does not
require a title redesign. Wording and appearance
are approved; displayed values do not define timers, rewards or progression.
Screen pixel maps are compositions for tilemap integration, not large objects.

### Assembled illustration

![Assembled core game illustration](core-art/scene-preview.svg)

The scene combines exact approved sources at illustrative coordinates. It
establishes visual compatibility, not a playable level, OAM capacity proof or
VRAM allocation. Its placement recipe lives in the reproduction helper.
The [later stage inventory](sml1-later-stages.md) records boss, vehicle and
bonus asset needs; those assets are not covered by this pack.
Gameplay contracts may identify additional frames requiring their own review.

## Reproduce and edit

From an author worktree root, run:

```text
python -m tools.sw.core_art --tag core-review
```

The [narrow composition helper](../../../../tools/sw/core_art/__init__.py) reconstructs
all sources and uses [tools.sw.preview](../../../tools/sw/SPEC.md#sprite-review-sheets)
for the approved PNG/SVG layouts. It writes the seven views and per-asset shade
JSON/2bpp files under `workdir/builds/core-review/core-art/`. Use a fresh tag.
No source, wiki or game file is overwritten. The helper's checked-in map inputs
own the pixels; its scene placements and sheet layout own review composition.

For example, inspect the exported small skid pose using the ordinary renderer:

```text
python -m tools.sw.preview workdir/builds/core-review/core-art/core/small-skid.json --tag skid-review --frame-width 16 --frame-height 16 --scale 8 --mirror --labels SKID
```

Follow [game-assets](../../../../.agents/skills/game-assets/SKILL.md) to edit
source, review changed art, integrate selected assets and update specifications.
The focused test checks map bounds, tile flips, 2bpp decode and exact committed
SVG reproduction. Publication does not modify the running game; integration
remains in the named feature issues and the [alignment contract](sml1-alignment.md).
