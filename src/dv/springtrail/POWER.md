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

This issue's startup LCD commit was 146500 dots; the
[block plan](BLOCKS.md#case-set-and-execution-bounds) owns the current anchor.
The 146500 derivation was the accepted motion anchor 139388
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

## Current renderer proof

`python-pr` is the current renderer proof for the power poses. It shares
`python-mr`'s harness (`hud_game_check.run` with `renderer`, `motion` and
`power` set), fixture builder (`motion_render_program.build` in its `power`
variant) and 300000-dot bound, but its fixed operands are a large thrower in
WALK2 with a live shot, a hidden dead enemy and a second composer stage writing
large-hurt facing left at `0xc150`; `python-mr` seeds only the motion WALK2
and skid poses. The two targets therefore prove different composed frames on
the same renderer, and both stay.

The target's `python.inputs` list the transitive local imports of
`test_power_render` and of the fixture builder, including
`blocks_reference.py`, which `power_reference`, `motion_frames` and
`hud_reference` import since the block layer; `hud_render_reference.py` is
named by `hud_game_check` only on the branch this target never takes and is
not listed. A declared input that is not a file fails validation before any
build, so the list must follow the modules.

## Measured durations

Whole-run supervisor walls from each receipt's `wall-budget` record, all at
this head on Questa Altera Starter FPGA Edition 2025.2 with Python 3.12.14 and
cocotb 2.0.1 from `workdir/builds/python-dv-env/.venv`:

| Target | Wall (s) | Limit (s) | Result |
| --- | --- | --- | --- |
| `python-pus` | 55.2 | 300 | PASS, crouch then stomp, `UpdateGame` 7168 and 7324 dots |
| `python-pux` | 37.3 | 300 | intended fault: `POWER_CROUCH_MUTATION expected=8 actual=9 dot=2847`, `MOTION_STATE crouch` rejected, receipt retained |
| `python-pua` | 235.7 | 300 | PASS, 23 cases, longest call 8348 dots |
| `python-pub` | 263.1 | 300 | PASS, 23 cases, longest call 8980 dots |
| `python-pr` | 293.3 | 420 declared | PASS, thrower/shot/hurt fixture, all 108 tiles |
| `python-mus` | 43.5 | 300 | PASS |
| `python-mux` | 45.0 | 300 | intended fault, `MOTION_STATE first-right` X 0180 versus 0190 |
| `python-mut` | 207.5 | 300 | PASS |
| `python-mgs` | 244.3 | 300 | PASS, LCD enable at dot 146500 |
| `python-mgu` | 311.9 | 420 declared | PASS |
| `python-mr` | 378.3 | 420 declared | PASS |

The declared aggregate is 2115 seconds across the eleven targets, each inside
its own selected wall. `python-pr` declares 420 seconds: under host contention
it exhausted the 300 default at 288 seconds with the trace at dot 213088 of
its 300000-dot bound, and on a quiet host it needed 293 seconds, above the
288-second execution limit that the default leaves after cleanup. A first
contended pass also exhausted the default for `python-mgs` and `python-mut`
(561 dots per second against about 900 unloaded) while another tool consumed
the host; the quiet reruns above are the evidence, and no other allowance was
declared. Licence refusals while another QuestaSim instance held the
nodelocked seat were retried, never counted.
