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

`assets/design/` holds the original 8x8 art of the proposed
[design directions](../../../wiki/src/sw/menu/DESIGN.md). Those tiles are not
linked into the image; render them with
`python -m tools.sw.menu_art --tag <fresh-tag>`.
