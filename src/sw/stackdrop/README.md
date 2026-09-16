# Stackdrop sources

Original SM83 code and original monochrome tile patterns. No external game,
font, code or asset source is used. Build with:

`python tools/build.py sw build stackdrop --tag <fresh-tag> --json`

The [game contract](../../../wiki/src/sw/stackdrop/SPEC.md) owns the rules.
`rules.asm` operates on ordinary WRAM, `render.asm` prepares a tile buffer and
copies it in VBlank, and `tables.asm` contains the literal seven shape tables,
the 103-tile atlas asset and the initial background map holding both the play
page and the [title page](../../../wiki/src/sw/stackdrop/SPEC.md#title-page).
Tiles0/1/2/3 are empty/rule/locked/active;4/5/6 are the status letters T/P/O;
10..19 are decimal digits; 20..23 corners, 24..30 label letters, 31..48 marquee
halves and 49..102 the six tiles of each title letter.

The copy's instruction-derived cost is4288 dots including its RET: well rows
3340, preview736, score/status212. ReadButtons plus its CALL costs160; Render's
CALL adds24, for4472 dots from the first CALL through the Render return. This
leaves88 of4560 VBlank dots before accounting for the bounded HALT wake edge.
`main.asm` decides before HALT, in visible time, whether the title page is still
shown after the game started (32 dots per frame in play, 56 on the title); on
that one frame it writes SCY/SCX0 after Render returns, 28 dots for the two
register writes, so the copy bracket is unchanged and the page changes in the
VBlank that copies the first playing image.
Actual CPU timing and worst lock/multiple-clear execution remain required;
assembly and this arithmetic alone are not runtime evidence.

The visible image has the documented one-frame preparation delay. The independent
rules model in `src/dv/stackdrop` predicts state from input, never from observed
CPU memory. The physical decoder will read only the existing full-frame snapshot.
