# Contact and power acceptance

The [owning power contract](../../../wiki/src/sw/springtrail/POWER.md)
separates source-confirmed local rules from approved original choices. The pure
`power_reference.py` and its literal histories in `test_power_reference.py`
were frozen before `power.asm` existed. `power_cases.py` turns those histories
into 48-byte operand snapshots: the motion fixture's 34 bytes plus the fourteen
contact/power bytes at C06A..C077. The same program builder, checker and
harness as the [movement plan](MOVEMENT.md) execute them; only the case module
and call kinds differ.

## Case set and execution bounds

Forty-six directed cases cover stomp and bounce, deep and walking hits for
small, large and thrower, HURT/SAFE suppression and expiry, the fatal hit after
the window, star grant/contact/decay, the power-up chain and growth, power-up
during SAFE, crouch on large/small/airborne players with release and jump,
shot spawn/move/bounce/rise, blocked spawns (large, crouching, second shot),
expiry, leftward and world-edge shots, shot kill/wall/ceiling, the 2-pixel
contact box against an item, the goal while large, fall death while large, a
dead enemy, `InitGame` from a dirty state and pause holding every timer.

The fixture's 2 KiB operand slot holds at most 41 snapshots, so the set runs
as two halves of 23 (`python-pua`, `python-pub`) after the two-case short
harness (`python-pus`: crouch, then stomp, under a 20000-dot progress bound). Each half keeps the motion fixture's caps: 8000 dots
per simple call, 20000 per `UpdateGame`, 1700 setup per case and the 500000-dot
progress guard. Static ceilings for the new work, counting every branch body:
`PowerTimers` 200, `PowerInput` 420, `StepShot` 2300 (two axis scans of at
most two cells each, bounds, one overlap test), `EnemyContact` 260,
`ContactTop` 90 per overlap call and `SelectPowerPose` 220. The composed
update therefore stays below the 20000-dot `UpdateGame` cap; the measured
per-case durations in each receipt's `summary.json` are the evidence.

Current startup LCD commit is 146500 dots: the accepted motion anchor 139388
plus 6584 for the fourteen-tile core copy replacing the four-tile copy, 368 for
initializing fourteen power bytes (the loop's `INC A` replaces the old
`LD A,1`), 28 for the title pose selector call, 112 for the hidden-flag helper,
20 for the enemy-alive hide test and 32 for the shot test, minus 32 because the
count-driven large adjust drops the two pose-range compares. This is an
instruction-derived anchor checked by `python-mgs` and `python-mgu`; a first
derivation of 146544 omitted the last two terms and was corrected from the
instruction listing, not adopted from the DUT.

## Acceptance matrix

| Group | Required result | Execution |
| --- | --- | --- |
| Contract/model | Literal stomp/hit/suppression/expiry, star, power-up chain, crouch masking, shot path/bounce/kill/limits, pose precedence, blink parity, contact box, pause/restart | `test_power_reference`, no DUT-fed expectations |
| Shared CPU | Actual `UpdateGame`, `PowerUp`, `GrantStar` and `InitGame` bytes; every expected state byte after each scripted call, completion and settled halt | `python-pus` short, then `python-pua` and `python-pub` |
| Fault | The crouch update's actual masked Buttons store forced from 8 to 9 after the call marker; the same call's motion consumes the unmasked Right, and the unchanged checker rejects the first report's counter, speed and button bytes. Each case re-seeds its operands, so only a store consumed inside its own call is a valid witness | `python-pux`, after the positive short |
| Rendered states | Large WALK2 with a live shot, dead-enemy hiding and a second-stage large-hurt facing left; every pixel, all 108 tiles, both DMA transfers | `python-pr` fixed renderer |
| Affected regression | Motion short/full CPU, fault, game short/full and renderer on the changed ROM, anchor and tile count | `python-mus`, `python-mut`, `python-mux`, `python-mgs`, `python-mgu`, `python-mr` |
| Assets | Approved core pixels reproduced by the ROM tables and copies; composed poses 12..17 equal the approved maps in both facings | `test_power_assets`, `test_motion_assets` |
| Delivery | Owning SW/DV links, 32 KiB reproducible image, host checks, required CI and current-head review | No new art approval or milestone replay |

## Measured durations

Whole-run supervisor walls from each receipt's `wall-budget` record are
recorded here once the targets run; a pending row is not evidence.

| Target | Wall (s) | Limit (s) | Result |
| --- | --- | --- | --- |
| `python-pus` | pending | 300 | pending |
| `python-pux` | pending | 300 | pending |
| `python-pua` | pending | 300 | pending |
| `python-pub` | pending | 300 | pending |
| `python-pr` | pending | 420 declared | pending |
| `python-mus` | pending | 300 | pending |
| `python-mux` | pending | 300 | pending |
| `python-mut` | pending | 300 | pending |
| `python-mgs` | pending | 300 | pending |
| `python-mgu` | pending | 420 declared | pending |
| `python-mr` | pending | 420 declared | pending |
