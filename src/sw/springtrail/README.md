# Springtrail foundation

Original SM83 code, hand-drawn monochrome lettering, courier, seed and terrain.
No external game, font, sprite, level or sound source is used. The silent image
uses the existing 32 KiB mapperless direct-entry profile and standard JOYP.
`tiles.json` is the original 16-tile shade atlas; `map.asm` is the literal initial
32-column by 18-row background. Tile IDs 0..10 are blank/lettering, 11 terrain,
12..13 courier, 14 seed and 15 the zero counter. Palette E4 maps shades directly.

The title overlays the initial world. Start clears its two text rows during
VBlank and changes ordinary WRAM C000 from title=0 to playing=1. The initial
courier is drawn in background tiles at (24,112); movement, sprites, interactions
and pause behavior belong to later issues. This foundation does not claim those
mechanics are implemented. The numeric world and mechanics contract belongs to
the [game spec](../../../wiki/src/sw/springtrail/SPEC.md).

Build: `python tools/build.py sw build springtrail --tag <fresh-tag> --json`.
