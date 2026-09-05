# Original shade fixture

Authored for nand2mario by the project agent; no external image or program source.
The 32 by 16 shade array is an original asymmetric arithmetic pattern. Each tile
uses `(x + 2*y + tile_column) mod 4` at local pixel coordinates. The second tile
row repeats the first. Every local pixel position sees all four shades, and
retained duplicates prove that conversion does not deduplicate or remap tiles.

`assets-basic` declares the JSON source and authorship. Its original assembly
emits NOP followed by ASSET bytes, so the build checks an instruction entry and
asset data separately. It is a tooling fixture, not CPU/PPU acceptance.
