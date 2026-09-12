# Lives, timer and progression acceptance

The [owning progression contract](../../../wiki/src/sw/springtrail/PROGRESS.md)
separates source-confirmed local rules from approved original choices. The pure
`progress_reference.py` and its literal expectations in
`test_progress_reference.py` were frozen before `progress.asm` existed.
`progress_cases.py` turns them into 55-byte operand snapshots: the power
fixture's 48 bytes plus the seven progression bytes at C090..C096. The same
program builder, checker and harness as the [power plan](POWER.md) execute
them; only the case module and one new call kind differ.

## Case set and execution bounds

Forty directed cases cover the subdivision-only update, one full time unit, the
grade thresholds at 100 and 50, zero and its consumption on the following
update, the floor at 000, the frozen timer in paused, retry and title, the life
request encoding with no request, an award, a BCD carry, saturation at 99, a
spend and a spend at zero, the retry spend with its held-press and idle
variants, retry without a life, a retry that keeps its stage, the time-up
spend, the game-over reset and its idle variant, the two stage advances, the
final clear, the paused Select reset, the title start, each stage's goal, a
player short of a goal, a stage item, a stage right bound, both stage 2 patrol
bounds, a stage 2 gap fall, the unchanged stage 0 contact and `InitGame` from a
dirty world.

The generated driver now stores the seven progression reset bytes before
seeding each case, so the lives, the stage and the countdown hold the
contract's reset values wherever a suite does not seed them, at about 100
dots per case; a full `InitGame` would also clear the block layer and break the
short harness's 20000-dot bound. A new `lives` kind calls the
shared `UpdateLives` directly, because nothing in this release awards a life
through gameplay. The set runs as two halves of 20 (`python-gpa`,
`python-gpb`) after the two-case short harness (`python-gps`: the retry spend,
then one timer unit, under a 20000-dot progress bound). Each half keeps the
motion fixture's caps: 8000 dots per simple call, 20000 per `UpdateGame`, 1700
setup per case and the 500000-dot progress guard. Static ceilings for the new
work, counting every branch body: `TickTimer` 330, `CheckTimeUp` 90,
`UpdateLives` 220, `ResetStageTimer` 200, `StageWordHL` 90 and `StageByteHL`
70 per lookup, `StageItemBox` 350 and `StageGoalBox` 250. The composed update
therefore stays below the 20000-dot `UpdateGame` cap; the measured per-case
durations in each receipt's `summary.json` are the evidence.

The startup anchor is derived from the built image by
`startup_anchor.derive`, the independent SM83 timing model under the CPU
contract, and frozen as `motion_game_reference.LCD`: 177492 dots for this
image. The progression terms of that derivation are `InitProgressArt` 6880,
`PrepareProgress` 664 and `PublishProgress` 432, with `InitGame` and
`PrepareScene` grown by the stage tables. The author's earlier hand count of
the same listing gave 6880, 664 and 440: the 8-dot `PublishProgress` error is
why the parked image's `python-mgs` failed at a hand-frozen 156160 against
the actual 156152, and the model now reproduces that image's 156152 exactly.
`test_startup_anchor` pins the two hand terms the model agrees with;
`python-mgs` proves the RTL commits at the derived dot.

## VBlank publication budget

Every composed checker requires each VBlank's display writes and the OAM DMA
to end by VBlank+4480 dots. A map-restoration frame already publishes two
columns and the row 0 cache before the DMA; with the row 1 cells published to
both maps the pause fixture's second frame triggered its DMA at VBlank+3952,
past the 3916-dot trigger bound. The cells therefore go to the one map the
display shows after that VBlank, which halves their cost to 248 dots of
startup and about 216 dots per frame; the measured trigger after the change
is recorded with the walls below.

## Acceptance matrix

| Group | Required result | Execution |
| --- | --- | --- |
| Contract/model | Literal subdivision, unit, grade thresholds, zero and its consumption, the floor, the frozen timer outside play, BCD award/carry/saturation/spend, game over at zero, the four transitions, held-press and waiting behavior, per-stage goal/bound/patrol/item, and precedence over the goal | `test_progress_reference`, no DUT-fed expectations |
| Stage data | The independent terrain rules equal all 4608 committed world cells, the three stages fill one 256-column page, and every stage goal stands on solid ground | `test_progress_reference`, `tools/n2m/tests/test_columns` |
| Shared CPU | Actual `UpdateGame` and `UpdateLives` bytes; every expected state byte after each scripted call, completion and settled halt | `python-gps` short, then `python-gpa` and `python-gpb` |
| Fault | The retry update's actual pending life request store forced from 255 to 1 after the call marker; the same call's `UpdateLives` takes the award path and the unchanged checker rejects exactly one byte, the life count, as 3 instead of 1. Each case re-seeds its operands, so only a store consumed inside its own call is a valid witness | `python-gpx`, after the positive short |
| Rendered states | HUD row 1 icons and values, all 117 tiles and the unchanged playfield on the changed ROM | `python-pr`, `python-mr` |
| Affected regression | Motion short/full CPU, fault, game short/full and renderer on the changed ROM and the derived anchor; power short, both halves, fault and renderer; the block short, halves and fault; the pause game short, full and fault; the composition and DMA fixtures whose input lists gained `progress.asm` | `python-mus`, `python-mut`, `python-mux`, `python-mgs`, `python-mgu`, `python-mr`, `python-pus`, `python-pua`, `python-pub`, `python-pux`, `python-pr`, `python-bks`, `python-bka`, `python-bkb`, `python-bkx`, `python-pgs`, `python-pgu`, `python-pgx`, `python-courier-short`, `python-courier-unit`, `python-os`, `python-ou`, `python-ox` |
| Assets | Approved core pixels reproduced by the ROM tables and copies at VRAM 140..148, the new mode words using loaded glyphs only, row 1 pixels equal to the approved maps, every other row 1 cell blank, and the committed previews reproduced from the same sources | `test_progress_assets` |
| Delivery | Owning SW/DV links, 32 KiB reproducible image, builder checks, wiki check, required CI and current-head review | No new art approval or milestone replay |

## Measured durations

Whole-run supervisor walls at this head on Questa Altera Starter FPGA Edition
2025.2 with Python 3.12.14 and cocotb 2.0.1 from
`workdir/builds/python-dv-env/.venv`:

| Target | Wall (s) | Limit (s) | Result |
| --- | --- | --- | --- |
| `python-gps` | pending | 300 | pending |
| `python-gpx` | pending | 300 | pending |
| `python-gpa` | pending | 300 | pending |
| `python-gpb` | pending | 300 | pending |
| `python-mgs` | pending | 300 | pending |

Licence refusals while the other nodelocked QuestaSim session held the seat
were retried, never counted and never killed.
