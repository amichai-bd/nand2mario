# Interactive block and collectible acceptance

The [owning block contract](../../../wiki/src/sw/springtrail/BLOCKS.md)
separates source-confirmed local rules from approved original choices. The pure
`blocks_reference.py` and its literal histories in `test_blocks_reference.py`
were frozen before `blocks.asm` existed. `blocks_cases.py` turns those
histories into 60-byte operand snapshots: the contact/power fixture's 48 bytes
plus the twelve block bytes at C078..C083. The same program builder, checker
and harness as the [power plan](POWER.md) execute them; only the case module
differs.

## Case set and execution bounds

Twenty directed cases cover the item block's release into `PowerUp`, its used
state, a repeated hit on a used block, the release effect's rise and expiry, an
ascent that hits nothing, a small player's inert brick bump, a large player's
break, the ascent that then passes through the broken cells, support gained and
lost on that brick, the coin block's counter and its saturation, the hidden
block passing a walker and revealing itself into `GrantStar`, the revealed
block stopping that same walker and supporting a fall, a shot reversing off a
block, the republication mark a state change raises, pause holding every block
byte and `InitGame` clearing them from a dirty state.

The fixture's 2 KiB operand slot holds at most 34 of these snapshots, so the set
runs as two halves of ten (`python-bka`, `python-bkb`) after the two-case short
harness (`python-bks`: the item hit, then the effect rise, under a 26000-dot
progress bound). Each half keeps the motion fixture's caps: 8000 dots per
simple call, 20000 per `UpdateGame`, 1700 setup per case and the 500000-dot
progress guard. Static ceilings for the new work, counting every branch body:
`CellSolid` 340 per probe outside rows 10 and 11 and 1300 inside them (one
four-entry table scan), `BlockTimers` 260, `ResolveBlockHit` 1500 (one table
scan, one state read, one effect write and one exported call) and
`BlockOverride` 2400 per decoded column (four entries, at most one match). The
composed update adds at most seven `CellSolid` probes, so it stays below the
20000-dot `UpdateGame` cap; the measured per-case durations in each receipt's
`summary.json` are the evidence.

Startup LCD commit moves from 146500 to 167840 dots: 20732 for `InitBlockArt`
(one `LD DE`, three `LD HL`/`LD B`/`CALL` groups, one `LD HL`/`LD B`/`JP`
group, four 128-byte `MotionTileCopy` passes of 1279 machine cycles each, four
returns and the outer `CALL`), 576 for initializing 38 rather than 14 gameplay
bytes, and 32 for the scene's new effect test. Nothing else on the startup path
changed: `PrepareMap` still returns at `GameMode` 0 and `StreamMap` does not
run before the LCD commit. This is an instruction-derived
anchor checked by `python-mgs` and `python-mgu`. The pause fixture's loose
startup window widens from 100000..160000 to 100000..200000 and its progress
watchdog's startup allowance from 160000 to 200000 dots for the same reason,
and the renderer fixture's own startup bound from 160000 to 200000 and its
progress watchdog from 300000 to 320000 dots, because it now loads the block
art too. No game or unit target's bound moves: only the fixtures whose startup
grew.

## Acceptance matrix

| Group | Required result | Execution |
| --- | --- | --- |
| Contract/model | Literal table, solidity per kind and state, appearance agreeing with solidity, one-shot release, coin saturation, brick breakage by power state, hidden reveal, effect rise, pause and restart | `test_blocks_reference`, no DUT-fed expectations |
| Shared CPU | Actual `UpdateGame` and `InitGame` bytes; every expected state byte after each scripted call, completion and settled halt | `python-bks` short, then `python-bka` and `python-bkb` |
| Fault | The item hit's actual `HitColumn` store forced from 38 to 42 after the call marker; the same call's `ResolveBlockHit` consumes the wrong cell, so block 0 stays intact, `PowerUp` is never called and no effect starts, and the unchanged checker rejects the first report's block, power and effect bytes. Each case re-seeds its operands, so only a store consumed inside its own call is a valid witness | `python-bkx`, after the positive short |
| Published background | The decoder writes the block layer's tiles over rows 10 and 11 of the column it is decoding, and leaves every other row and column exactly as `columns.asm` encodes them | `test_blocks_reference` through `blocks_frames.column`. No DUT fixture covers it: every block is beyond column 31, so the thirty-two column ring the game and pause fixtures publish never contains one, and `hud_reference.column` stays terrain-only for those checks |
| Republication mark | `BlockDirty` carries the changed block's column plus one out of the update that set it | `test_blocks_reference`, `python-bks`, `python-bka`, `python-bkb` |
| Assets | Approved terrain pixels reproduced by the ROM table, the startup copies and the loaded VRAM image; each design an unflipped four-tile approved map; the rendered used block equal to its approved pixels | `test_blocks_assets` |
| Affected regression | Contact/power short/halves and fault, motion short/full and fault, game short/full, pause short/full and the motion renderer on the changed ROM, anchor and tile count | `python-pus`, `python-pua`, `python-pub`, `python-pux`, `python-mus`, `python-mut`, `python-mux`, `python-mgs`, `python-mgu`, `python-mr`, `python-pgs`, `python-pgu`, `python-pgx` |
| Delivery | Owning SW/DV links, 32 KiB reproducible mapperless image, host checks, required CI and current-head review | No new art approval or milestone replay |

## Measured durations

Whole-run supervisor walls from each receipt's `wall-budget` record, all at
this head on Questa Altera Starter FPGA Edition 2025.2 with Python 3.12.14 and
cocotb 2.0.1 from `workdir/builds/python-dv-env/.venv`.

| Target | Wall (s) | Limit (s) | Result |
| --- | --- | --- | --- |
| `python-bks` | 47.9 | 300 | PASS, item hit then effect rise |
| `python-bkx` | 32.5 | 300 | intended fault: `BLOCKS_HIT_MUTATION expected=38 actual=42 dot=5991`, `MOTION_STATE item-hit` rejected, receipt retained |
| `python-bka` | 113.2 | 300 | PASS, 10 cases |
| `python-bkb` | 111.4 | 300 | PASS, 10 cases |
| `python-mus` | 28.3 | 300 | PASS |
| `python-pus` | 38.8 | 300 | PASS |
| `python-mux` | 25.2 | 300 | intended fault, `MOTION_STATE first-right` |
| `python-pux` | 29.2 | 300 | intended fault, `MOTION_STATE crouch` |
| `python-mgs` | 190.5 | 300 | PASS, LCD enable at dot 167840 |
| `python-pgs` | 192.0 | 300 | PASS |
| `python-pua` | 173.7 | 300 | PASS, 23 cases |
| `python-pub` | 209.8 | 300 | PASS, 23 cases |
| `python-mut` | 217.1 | 300 | PASS |
| `python-mgu` | 359.5 | 420 declared | PASS |
| `python-mr` | 335.6 | 420 declared | PASS |
| `python-pgu` | 645.7 | 880 declared | PASS |
| `python-pgx` | 478.2 | 880 declared | intended fault, `PAUSE_MODE_MUTATION expected=3 actual=1 dot=378363`, `PAUSE_HUD_CACHE` rejected |

The aggregate is 3228 seconds across seventeen targets, each inside its own
selected wall. No new allowance is declared: every block target finishes well
inside the 300-second default, and the three declared walls are the existing
ones those targets already carried. Licence refusals while another QuestaSim
instance held the nodelocked seat were retried, never counted.

`python-pr` is not in that set. Its declared inputs still name
`src/dv/springtrail/composition_game_check.py`, which #385 deleted, so the
target fails validation before it builds anything and already failed that way
on `main`. `python-mr` exercises the same renderer path on the same changed
ROM; restoring `python-pr` belongs to its own issue.

## Coverage limit

The CPU fixtures call `UpdateGame`, `InitGame`, `PowerUp` and `GrantStar`; they
never call `PrepareMap` or `StreamMap`. So the republication mark `BlockDirty`
is proven by actual CPU stores, but two things are not proven on the DUT: the
streamer branch that consumes that mark, and the decoder's column override.
Every block sits beyond column 31, so the thirty-two column ring the game,
pause and renderer fixtures publish never contains one, and their scripted
inputs never bring the camera near a block. Both rest on the model, on the
unchanged publisher they reuse, and on the ring-slot argument in the contract:
a block can only change state while the player touches it, so its columns are
always inside the published window. A fixture that drives the player onto a
block would close this; it needs its own scripted input and is not in scope
here.
