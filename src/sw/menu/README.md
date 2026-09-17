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

`assets/design/v2-grey-tiles.json` and `assets/design/v2-cursor-tiles.json`
are the shipped art, the six mid-grey plate cells and the two cursor pointer
phases, linked into the image as `ASSET "GreyArt"` and `ASSET "Pointer"`; the
39 grey glyphs are derived from the font at boot. The other `v2-*.json` files
hold the art of the [menu v2 ideas](../../../wiki/src/sw/menu/DESIGN_V2.md)
that later slices deliver; those tiles are not linked into the image yet.
Render every idea with `python -m tools.sw.menu_v2 --tag <fresh-tag>`.

`assets/design/direction-*.json` holds the art of the
[design directions](../../../wiki/src/sw/menu/DESIGN.md) of the first pass;
none of it is linked into the image. Render every direction with
`python -m tools.sw.menu_art --tag <fresh-tag>`.
