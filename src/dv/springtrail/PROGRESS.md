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

The generated driver now calls `InitGame` before seeding each case, so every
suite starts from the contract's reset and the lives and the stage hold their
reset values wherever a suite does not seed them. A new `lives` kind calls the
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

Startup LCD commit moves from 146500 to 156160 dots: 9660 added dots counted
from the instruction listing, not adopted from the DUT. `InitGame` adds 396
(the lives, stage and pending stores, the stage enemy word through
`StageWordHL`, and `ResetStageTimer`); `InitProgressArt` adds 6880 (nine
sixteen-byte copies with their loop overhead plus the two static icon pairs);
`PrepareScene` adds 1280 (four `StageItemBox` calls and one `StageGoalBox`
replacing inline coordinate stores); `PrepareProgress` adds 664 and
`PublishProgress` adds 440. `python-mgs` confirms the derived anchor.

## Acceptance matrix

| Group | Required result | Execution |
| --- | --- | --- |
| Contract/model | Literal subdivision, unit, grade thresholds, zero and its consumption, the floor, the frozen timer outside play, BCD award/carry/saturation/spend, game over at zero, the four transitions, held-press and waiting behavior, per-stage goal/bound/patrol/item, and precedence over the goal | `test_progress_reference`, no DUT-fed expectations |
| Stage data | The independent terrain rules equal all 4608 committed world cells, the three stages fill one 256-column page, and every stage goal stands on solid ground | `test_progress_reference`, `tools/n2m/tests/test_columns` |
| Shared CPU | Actual `UpdateGame` and `UpdateLives` bytes; every expected state byte after each scripted call, completion and settled halt | `python-gps` short, then `python-gpa` and `python-gpb` |
| Fault | The retry update's actual pending life request store forced from 255 to 1 after the call marker; the same call's `UpdateLives` takes the award path and the unchanged checker rejects exactly one byte, the life count, as 3 instead of 1. Each case re-seeds its operands, so only a store consumed inside its own call is a valid witness | `python-gpx`, after the positive short |
| Rendered states | HUD row 1 icons and values, all 117 tiles and the unchanged playfield on the changed ROM | `python-pr`, `python-mr` |
| Affected regression | Motion short/full CPU, fault, game short/full and renderer on the changed ROM and the new anchor; power short, both halves, fault and renderer | `python-mus`, `python-mut`, `python-mux`, `python-mgs`, `python-mgu`, `python-mr`, `python-pus`, `python-pua`, `python-pub`, `python-pux`, `python-pr` |
| Assets | Approved core pixels reproduced by the ROM tables and copies at VRAM 108..116, the new mode words using loaded glyphs only, row 1 pixels equal to the approved maps, every other row 1 cell blank, and the committed previews reproduced from the same sources | `test_progress_assets` |
| Delivery | Owning SW/DV links, 32 KiB reproducible image, builder checks, wiki check, required CI and current-head review | No new art approval or milestone replay |

## Measured durations

Whole-run supervisor walls at this head on Questa Altera Starter FPGA Edition
2025.2 with Python 3.12.14 and cocotb 2.0.1 from
`workdir/builds/python-dv-env/.venv`:

| Target | Wall (s) | Limit (s) | Result |
| --- | --- | --- | --- |
| `python-gps` | 48 | 300 | PASS, the retry spend then one timer unit |
| `python-gpx` | 37 | 300 | intended fault: `PROGRESS_REQUEST_MUTATION expected=255 actual=1 dot=4839`, `MOTION_STATE retry-spend` rejected on the life count alone, receipt retained |
| `python-gpa` | 149 | 300 | PASS, 20 cases |
| `python-gpb` | 187 | 300 | PASS, 20 cases |
| `python-mgs` | 216 | 300 | FAIL, `MOTION_STARTUP_BOUND`: the derivation below is not yet correct |

The startup derivation is open. The hand count above predicts 156160 and the
actual first `LCDC` commit is 156152, so exactly one term is 8 dots too high.
Find and correct that term in the instruction listing; do not adopt 156152 as
the expectation. Every other affected target is unrun.

Licence refusals while the other nodelocked QuestaSim session held the seat
were retried, never counted and never killed.
