# Scrolling, win and death/retry frames on the current image

Bounded physical proof under the
[image binding](../../../wiki/src/dv/springtrail/SPEC.md#image-binding) and
the [milestone reuse policy](../../../wiki/src/dv/integration/SPEC.md#milestone-acceptance).
`frame_proofs.py` is the launcher and driver; `test_frame_proofs.py` holds
the host checks. Everything is observed over UART on the reviewed board
build; no monitor or physical control is claimed, and no simulation target
reaches these frames inside the wall ceiling.

## Why hardware

The player starts at x 24 and the camera is `max(0, x-72)`. Under the motion
model the earliest camera movement is update 34 with B and Right held from
the first update, displayed in source frame 37 at about 660 ms of simulated
time. At the measured composed rate of 6.0 wall seconds per simulated
millisecond that is about 4000 wall seconds; the win and death/retry frames
lie beyond it. Each exceeds the 900-second ceiling, so no simulation target
is declared and the frames are taken from the board while it is paused.

## Image binding

The launcher runs `sw build springtrail` from current sources and passes the
build's own image hash to the driver, which refuses any other bytes
(`FRAME_ROM`) before opening a directory or sending a command. No hash
constant is stored; the run's `build.json` and `result.json` record the
image checked. The expected wire build is given on the command line and
checked against the endpoint's build identity before traffic.

Expected frames come from the independent models only: `motion_reference`
for the player, the frozen flow in `interactions_reference` over that player
for modes, enemy, items and goal, and `motion_frames.image`, which composes
the current poses onto `hud_reference.image`, for pixels. LCD commit 139388
and period 70224 are the source-derived anchors `motion_game_reference`
checks in simulation; the title frame completing at dot 275071 confirmed the
anchor on hardware in the endurance proof. No value is taken from the DUT.

## Frozen script

The board is paused at every checkpoint `C(n) = 139388 + n*70224 + 4096`,
reached with exact `RUN_DOTS` counts of at most one period; `RUN`, `HALT`
and `STEP` are not used. A mask applied at C(n) is sampled in VBlank n,
computed in visible frame n+1, published in VBlank n+1 and displayed in
source frame n+2. `SNAPSHOT` at C(n) returns source frame n-1, which must
carry the load's epoch, sequence n-1 and a completion dot inside row 143.

Sampled masks per VBlank, from VBlank 2 (VBlank 0 and 1 sample 0):

| Masks (mask, VBlanks) | Purpose |
|---|---|
| (161,1) (33,96) (49,12) (33,40) (49,12) (33,64) (49,12) (33,116) (49,12) (33,106) | Success: Start+B+Right, then B+Right with held A over the first gap, the enemy patrol, the second and third gaps; WON after update 471, score 0 |
| (128,1) (0,20) | Start restart from WON, then neutral while the ring restores its 16 column pairs |
| (33,110) | Death: B+Right from spawn into the first gap; RETRY after 130 updates |
| (128,1) (0,20) | Start restart from RETRY, then the same neutral settle; the final mask is 0 |

The success and death/retry routes in `interaction_routes.py` were frozen for
the fixed-physics player: over the current motion model the success route
meets the enemy at update 153, so this proof freezes its own routes over
`motion_reference`. Both are ordinary inputs through the UART INPUT path.

Captures, with the game index k (frame k+1, snapshot at C(k+2)) and the
literal expected state `(mode, x, y, camera, score, timer, enemy_x, enemy_vx)`
in sixteenths of a pixel; the host test fails when the model disagrees:

| Capture | k | Expected state | Covers |
|---|---|---|---|
| `title` | 0 | (TITLE, 384, 1792, 0, 0, 0, 4096, 8) | Title frame before any input |
| `spawn` | 3 | (PLAYING, 400, 1792, 0, 0, 1, 4104, 8) | First world frame after Start+B+Right |
| `first-camera` | 36 | (PLAYING, 1168, 1792, 1, 0, 34, 4368, 8) | First camera-moving frame, camera 0 to 1 |
| `entering-column` | 99 | (PLAYING, 2688, 1792, 96, 0, 97, 4600, -8) | Camera 95 to 96: column 32 enters, the first column outside the initial ring |
| `scroll-wrap` | 206 | (PLAYING, 5248, 1792, 256, 0, 204, 3936, 8) | Camera 255 to 256, the 32-column ring wrap |
| `camera-clamp` | 441 | (PLAYING, 10896, 1792, 608, 0, 439, 4024, 8) | Camera reaches the 608 clamp |
| `won` | 473 | (WON, 11664, 1792, 608, 0, 471, 4280, 8) | WON frame at the goal |
| `won-restart` | 493 | (PLAYING, 384, 1792, 0, 0, 19, 4248, 8) | Start restart from WON, 19 updates later, ring restored |
| `retry` | 604 | (RETRY, 2992, 2304, 115, 0, 130, 4336, -8) | RETRY frame after the fall into the first gap |
| `retry-restart` | 625 | (PLAYING, 384, 1792, 0, 0, 20, 4256, 8) | Start restart from RETRY, 20 updates later, ring restored |

Every capture compares all 23040 pixels; the first mismatching pixel fails
the run. The input history before each capture is the prefix of the script
above and is recorded per capture in `result.json`. A restart from a scrolled
camera republishes SCX 0 at once while the ring restores two columns per
VBlank, so the two restart captures wait at least 16 updates; the model
renders the complete world and does not describe the partial ring. The two
restart frames are pixel-identical (spawn, patrol offscreen) and differ in
timer and enemy phase only.

Plans: `short` is the prefix through `entering-column` (101 checkpoints,
four captures) and releases INPUT 0 at its final checkpoint; `full` is the
whole history (627 checkpoints, ten captures). Both keep the existing 300 s
whole-process cap: the worker refuses a further checkpoint after `cap-24` s
and the launcher kills the worker tree at `cap-12` s. Failure keeps the dot,
journal and packed frames; cleanup sends HALT and INPUT 0 only when the
Client is certain. Forecast before execution: about one UART round trip per
checkpoint plus ten frame readbacks, well under 300 s for `full`; the `short`
run measures the rate before the `full` run.

Run, with the reviewed wire build ID and the board's UART port:

```powershell
python src/dv/springtrail/frame_proofs.py short --uart-port COM3 --expected-build-id <build-id> --tag frames384
python src/dv/springtrail/frame_proofs.py full --uart-port COM3 --expected-build-id <build-id> --tag frames384
```

Hardware programming and capture need the user's explicit authorization and
the serialized machine lock; the launcher does not program the board.

## Measured result

Not yet executed on hardware. The pull request that runs the plans records
the commit, image hash, wire build, whole and per-plan wall seconds, checked
pixels and the final paused state here.
