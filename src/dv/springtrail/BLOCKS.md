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
watchdog's startup allowance from 160000 to 200000 dots for the same reason.

## Acceptance matrix

| Group | Required result | Execution |
| --- | --- | --- |
| Contract/model | Literal table, solidity per kind and state, appearance agreeing with solidity, one-shot release, coin saturation, brick breakage by power state, hidden reveal, effect rise, pause and restart | `test_blocks_reference`, no DUT-fed expectations |
| Shared CPU | Actual `UpdateGame` and `InitGame` bytes; every expected state byte after each scripted call, completion and settled halt | `python-bks` short, then `python-bka` and `python-bkb` |
| Fault | The item hit's actual `HitColumn` store forced from 8 to 12 after the call marker; the same call's `ResolveBlockHit` consumes the wrong cell, so block 0 stays intact, `PowerUp` is never called and no effect starts, and the unchanged checker rejects the first report's block, power and effect bytes. Each case re-seeds its operands, so only a store consumed inside its own call is a valid witness | `python-bkx`, after the positive short |
| Published background | The restored and streamed column caches carry the block layer's tiles, not the bare terrain value | `python-mgs`, `python-mgu`, `python-pgs`, `python-pgu` through the block-aware `hud_reference.column` |
| Republication mark | `BlockDirty` carries the changed block's column plus one out of the update that set it | `test_blocks_reference`, `python-bks`, `python-bka`, `python-bkb` |
| Assets | Approved terrain pixels reproduced by the ROM table, the startup copies and the loaded VRAM image; each design an unflipped four-tile approved map; the rendered used block equal to its approved pixels | `test_blocks_assets` |
| Affected regression | Contact/power short/halves and fault, motion short/full and fault, game short/full, pause short/full and the motion renderer on the changed ROM, anchor and tile count | `python-pus`, `python-pua`, `python-pub`, `python-pux`, `python-mus`, `python-mut`, `python-mux`, `python-mgs`, `python-mgu`, `python-mr`, `python-pgs`, `python-pgu` |
| Delivery | Owning SW/DV links, 32 KiB reproducible mapperless image, host checks, required CI and current-head review | No new art approval or milestone replay |

## Measured durations

Whole-run supervisor walls from each receipt's `wall-budget` record, all at
this head on Questa Altera Starter FPGA Edition 2025.2 with Python 3.12.14 and
cocotb 2.0.1 from `workdir/builds/python-dv-env/.venv`.

| Target | Wall (s) | Limit (s) | Result |
| --- | --- | --- | --- |
| `python-bks` | 59.4 | 300 | PASS, item hit then effect rise, `UpdateGame` 8428 dots |
| `python-bkx` | 32.9 | 300 | intended fault: `BLOCKS_HIT_MUTATION expected=8 actual=12 dot=5963`, `MOTION_STATE item-hit` rejected, receipt retained |
| `python-bka` | 111.4 | 300 | PASS, 10 cases |
| `python-bkb` | 112.2 | 300 | PASS, 10 cases |

No new wall allowance is declared: every block target finishes well inside the
300-second default.

`python-pr` is not in that set. Its declared inputs still name
`src/dv/springtrail/composition_game_check.py`, which #385 deleted, so the
target fails validation before it builds anything and already failed that way
on `main`. `python-mr` exercises the same renderer path on the same changed
ROM; restoring `python-pr` belongs to its own issue.

## Coverage limit

The CPU fixtures call `UpdateGame`, `InitGame`, `PowerUp` and `GrantStar`; they
never call `PrepareMap` or `StreamMap`. So the republication mark `BlockDirty`
is proven by actual CPU stores, but the streamer branch that consumes it is
covered only by the existing game and pause fixtures' unchanged column checks,
whose scripted inputs never hit a block. That branch's correctness rests on the
unchanged publisher it reuses and on the ring-slot argument in the contract: a
block can only change state while the player touches it, so its columns are
always inside the published window.
