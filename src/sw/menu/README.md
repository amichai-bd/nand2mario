# Menu sources

Original SM83 code for the on-board game menu, built in the `dmg-loader-v1`
package profile. Build with:

`python tools/build.py sw build menu --tag <fresh-tag> --json`

The [menu contract](../../../wiki/src/sw/menu/SPEC.md) owns behavior, memory
use and the frame layout; the [loader profile](../../../wiki/src/rtl/cartridge/MAS_loader_profile.md)
owns the registers it uses. `main.asm` holds the whole program; `layout.json`
keeps every section in ROM0 because the upper half is the banked window;
`assets/font-tiles.json` is the 39-tile font atlas whose glyphs are the
approved Springtrail core font plus an original blank and cursor arrow.

`assets/design/direction-a-tiles.json` is the chosen design's original art,
the nudged cursor arrow and the two plate caps, linked into the image as
`ASSET "Plate"`; the inverse bank is derived from the font at boot. The other
two files hold the art of the
[design directions](../../../wiki/src/sw/menu/DESIGN.md) the owner did not
choose; those tiles are not linked into the image. Render every direction with
`python -m tools.sw.menu_art --tag <fresh-tag>`.

`assets/design/v2-*.json` holds the art of the
[menu v2 ideas](../../../wiki/src/sw/menu/DESIGN_V2.md), mockups nobody has
chosen; those tiles are not linked into the image either. Render every idea with
`python -m tools.sw.menu_v2 --tag <fresh-tag>`.
