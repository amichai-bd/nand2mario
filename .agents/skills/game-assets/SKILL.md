---
name: game-assets
description: Create, revise, preview and integrate original Springtrail pixel assets, linking editable sources, user-approved images and wiki specifications. Use for sprite, tile, font and screen artwork; not RTL behavior.
---

# Game assets

Read the owning feature issue and [core art reference](../../../wiki/src/sw/springtrail/CORE_ART.md)
first. Follow [agent-flow](../agent-flow/SKILL.md) for the worktree and delivery.
The existing [courier bank](../../../src/sw/springtrail/assets/courier/unique-tiles.json)
and [core banks/maps](../../../wiki/src/sw/springtrail/CORE_ART.md#editable-sources)
own approved pixels and placement. Artwork publication and running-game integration
are separate deliverables; do only the authorized one.

## Edit and render

Edit authoritative shade JSON and named placement maps under `src/sw/springtrail/assets/`.
Do not edit generated PNG/SVG or exported shade snapshots as the lasting source.
Use original integer shade grids, not image generation, for exact pixel editing.
Inspect all poses using a tile before changing it; copy a shared tile and redirect
only the intended pieces when other poses must remain unchanged.

Run from the author worktree root with fresh tags:

```text
python -m tools.sw.core_art --tag core-review
python -m tools.sw.preview workdir/builds/core-review/core-art/core/small-skid.json --tag skid-review --frame-width 16 --frame-height 16 --scale 8 --mirror --labels SKID
```

The first command reconstructs the approved pack, exports per-asset shade JSON
and 2bpp, and renders its fixed review layouts using `tools.sw.preview`. The
second is the general atlas renderer; point it at any strict shade JSON. Use
`--frame-width 8 --frame-height 8` for individual tiles (at most 64 frames per
sheet). See the [tool contract](../../../wiki/tools/sw/SPEC.md#sprite-review-sheets)
for limits, output paths and labels. Inspect PNGs at nearest-neighbor scale and
send them for review; a delegated agent routes them through root. Use actual
composed views as well as 8x8 pieces when tile reuse or seams matter.

Shade data is 2bpp: each 8x8 tile is 16 bytes, low/high plane per row, leftmost
pixel in bit 7. Shade 0 is OBJ-transparent but a visible BG/window palette index;
the preview checkerboard is not game data. Core atlas tile IDs are local review
indices, not VRAM addresses. Whole-character horizontal mirroring must move each
piece to `width - 8 - x` and toggle its X-flip, as well as respecting the gameplay
anchor; flipping each tile in place alone is insufficient.

## Approval and publication

Carry forward approval for unchanged source pixels. New or visually changed art
must be approved by the user before publishing it as approved or integrating it;
a delegated agent routes the preview and the answer through root. Do not ask
again for a revision already approved for this change.
Record the approved revision and scope on the owning wiki page. Copy generated
SVG review views into that page's image folder and link authoritative source/maps,
and the reproduction command. Link an existing open feature issue only for an
explicit remaining integration or verification gap; remove it when the gap
closes, following [wiki writing](../wiki-spec-writer/SKILL.md). Keep PNGs, encoded
bytes and temporary exports in the worktree's `workdir/`. Update existing issues
with source/spec links and remaining integration criteria; do not create extra
issues unless the user requests them. Preserve other assets while approval waits.

## Integrate when authorized

Inspect current [game source](../../../src/sw/springtrail/main.asm),
[ROM layout](../../../src/sw/springtrail/layout.json) and
[scene code](../../../src/sw/springtrail/scene.asm) before selecting the integration.
Register selected shade JSON in the game target's `assets` mapping in
[src/sw/targets.json](../../../src/sw/targets.json), including its author/provenance.
Assembly uses `ASSET "Name"` (currently `ASSET "Tiles"`); the build converts that
registered shade JSON to 2bpp. Arrange tiles in the required ROM/VRAM order and
reference those actual IDs from game tables.
Update allocated sections, loading, BG/window maps or metasprite/OAM tables and
animation selection under the owning feature contract. Define anchors, mirroring,
palettes and object budgets there; approved artwork does not establish mechanics,
physics constants or simultaneous memory residency. Never bake gameplay into RTL.

Use the [verification tiers](../../../wiki/src/dv/integration/SPEC.md#verification-tiers):
for publication, run `python -m unittest tools.n2m.tests.test_core_art tools.n2m.tests.test_sprite_preview`
and wiki checks. For runtime changes, also build the ROM and run the affected short
preloaded rendering/state tests, including tile-ID, clipping and object-limit checks
where relevant. Update the gameplay spec to describe actual integration, leaving
unfinished feature criteria open. Exact review views prove artwork reproduction,
not running-game behavior or FPGA display success.
