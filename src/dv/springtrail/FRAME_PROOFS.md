# Retained scrolling, win and death/retry frame fixture

## Current gameplay qualification gap

The retained protocol/checkpoint fixture still uses the pre-progression power
and block model. Its synthetic tests do not qualify current lives/countdown
frames or a current continuous route. [#511](https://github.com/amichai-bd/nand2mario/issues/511)
owns current model and frame expectations together with the endurance script.
The launcher still requires the actual source-built image, and checkpoint times
follow its independently derived LCD anchor. No physical result is implied.


The intended bounded physical proof follows the
[image binding](../../../wiki/src/dv/springtrail/SPEC.md#image-binding) and
the [milestone reuse policy](../../../wiki/src/dv/integration/SPEC.md#milestone-acceptance).
`frame_proofs.py` is the launcher and driver; `test_frame_proofs.py` holds
the host checks. The fixture observes UART on a reviewed board build;
no monitor or physical control is claimed, and no simulation target
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

Retained expected frames come from these independent models: `motion_reference`
for the player, `power_reference` over that player for modes, enemy, items,
goal and the block and power layers the image carries, and
`blocks_frames.image`, which draws the block layer in the state the script
leaves it under the current poses on `hud_reference.image`, for pixels. The
route touches no block, so every expected frame shows the four blocks intact;
`test_frame_proofs` proves the block-aware image differs from the terrain-only
`motion_frames.image` in the block cells in view and nowhere else, and that
`scroll-wrap` is the only capture with a block in view: the 256 pixels of
the item block at world column 38..39, rows 10..11. LCD commit 167840
and period 70224 are the source-derived anchors of the current image
([startup anchor](#startup-anchor)); `motion_game_reference` proves the RTL
commits at that dot in `python-mgs`, `test_startup_anchor` fails at level 0
when the built image derives any other dot, and the launcher's `build_rom`
refuses such an image before any traffic. No value is taken from the DUT.

## Startup anchor

The anchor is the dot of the image's first LCDC 0x91 write. `startup_anchor.py`
derives it from the built image with an independent SM83 timing model under
the [CPU contract](../../../wiki/src/rtl/cpu/MAS_cpu.md#time-bus-and-retirement):
one initial opcode fetch, each instruction's manual M-cycle count with the
final fetch overlapping the next instruction, conditional costs by outcome,
and a write committing at T4 of its M-cycle, so the dot is four times the
M-cycles completed through the write. IME stays clear until after the
write, so the path is straight-line code with data-dependent loops. Dots
are attributed to the nearest preceding label at call depth zero and to the
callee inside a `CALL`, so a loop's setup loads belong to the label before
it. The
model reads nothing from a run; `python-mgs` is where the RTL is held to it.

Image `35aae757bde0ec9a15d6d6c84f14b45b451c341d2d4775f43ed8a9a762625192`,
41960 M-cycles over 21373 instructions, by routine in execution order
(`python src/dv/springtrail/startup_anchor.py` prints this table):

| Term | Dots | Covers |
|---|---|---|
| reset fetch | 4 | the initial opcode fetch at 0100 |
| header | 20 | `NOP` and `JP Start`, written by the packager |
| `Start` | 220 | the inline register and WRAM stores and the tile copy's setup loads |
| `InitSceneDMA` | 428 | the HRAM DMA routine copy |
| `InitGame` | 2156 | game, power and block state, including the 38-byte reset loop |
| `ClearObjects` | 3872 | 160 OAM bytes |
| `CopyTiles` | 61600 | 1184 tile bytes to VRAM and the map copy's setup loads |
| `CopyMap` | 30108 | 576 title map bytes, the palettes and the closing register stores through the LCDC write |
| `InitHUD` | 17120 | the 20 font tiles and the second map's cleared HUD rows |
| `InitMotionArt` | 9212 | the courier poses |
| `InitBlockArt` | 20732 | four 128-byte block tile copies |
| `PrepareScene` | 20304 | the first shadow scene, including the effect test |
| `PrepareHUD` | 412 | the HUD cache |
| `PrepareMap` | 84 | the prepared-column reset; returns at title |
| `PublishHUD` | 664 | both map rows |
| `PublishScene` | 904 | the first HRAM DMA and its wait loop |
| **LCD** | **167840** | `LDH [$FF40],A` commits in its second M-cycle |

The same model reproduces the previous anchors from their images: 146500
before the block layer and 156152 for the parked progression branch, each
matching the retirement trace of its `python-mgs` run instruction for
instruction; the block layer's +20732, +576 and +32 terms are the ones its
review counted by hand. Two hand counts of the table above are frozen in
`test_startup_anchor` beside the model's.

A board never reads the anchor directly. A snapshot's completion dot is
`LCD + seq*PERIOD + 143*456 + x` for the last pixel's offset x inside row
143, which the row check bounds to 0..455; it is not `LCD + seq*PERIOD +
143*456`. The 2026-09-12 board session that found the drift read frame
completions 233299 and 303523 on this image: both are 167840 plus 143*456
plus 251, the same offset the previous image's title frame showed at 275071
(139388 + 70224 + 65208 + 251), so the board corroborates the derivation.

## Frozen script

The board is paused at every checkpoint `C(n) = 167840 + n*70224 + 4096`,
reached with exact `RUN_DOTS` counts of at most one period; `RUN`, `HALT`
and `STEP` are not used. A mask applied at C(n) is sampled in VBlank n,
computed in visible frame n+1, published in VBlank n+1 and displayed in
source frame n+2. `SNAPSHOT` at C(n) returns source frame n-1, which must
carry the load's epoch, sequence n-1 and a completion dot inside row 143.

Sampled masks per VBlank, from VBlank 2 (VBlank 0 and 1 sample 0):

| Masks (mask, VBlanks) | Purpose |
|---|---|
| (161,1) (33,96) (49,12) (33,40) (49,12) (33,64) (49,1) (33,127) (49,12) (33,106) | Success: Start+B+Right, then B+Right with held A over the first gap and the enemy patrol, a one-VBlank A tap over the second gap, and held A over the third gap; WON after update 471, score 0 |
| (128,1) (0,20) | Start restart from WON, then neutral while the ring restores its 16 column pairs |
| (33,110) | Death: B+Right from spawn into the first gap; RETRY after 130 updates |
| (128,1) (0,20) | Start restart from RETRY, then the same neutral settle; the final mask is 0 |

The success and death/retry routes in `interaction_routes.py` were frozen for
the fixed-physics player: over the current motion model the success route
meets the enemy at update 153, so this proof freezes its own routes over
`motion_reference`. Both are ordinary inputs through the UART INPUT path.
The second-gap jump is a one-VBlank tap because the brick at world column
52..53 stands two columns after that gap (columns 46..49) in rows 10..11: no
jump's arc can pass above it, and from the frozen takeoff at VBlank 227 a
held jump lands against its side at update 260, x 408, and the route then
never reaches the goal. The tap is airborne over updates 228..252, lands at
x 399 and walks under the brick; the run after it is eleven VBlanks longer
so the third-gap jump, every later input and every capture index stay where
they were. A held jump started earlier, at VBlank 206..218, also lands
before the brick and meets every literal; the tap is the passing variant
with the longest unchanged input prefix. `test_frame_proofs` holds the
stall and the tap's landing.

Captures, with the game index k (frame k+1, snapshot at C(k+2)) and the
literal expected state `(mode, x, y, camera, score, timer, enemy_x, enemy_vx)`
in sixteenths of a pixel; each literal also carries the block states
`(INTACT, INTACT, INTACT, INTACT)` and power `SMALL`, and the host test fails
when the model disagrees:

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
run measures the rate before the `full` run. Each extra `--showcase` snapshot
costs about 1.5 s (a 5760-byte readback and the 23040-pixel comparison), so
`full --showcase` with its 40 extra snapshots forecasts about 110 s; the
first such run was forecast at 80 s from an assumed 0.8 s per snapshot and
measured 106.8 s.

Run, with the reviewed wire build ID and the board's UART port:

```powershell
python src/dv/springtrail/frame_proofs.py short --uart-port COM3 --expected-build-id <build-id> --tag frames384
python src/dv/springtrail/frame_proofs.py full --uart-port COM3 --expected-build-id <build-id> --tag frames384
```

Hardware programming and capture need the user's explicit authorization and
the serialized machine lock; the launcher does not program the board.

`full --showcase` adds one paused `SNAPSHOT` at each checkpoint in the frozen
`SHOWCASE` list, the frames `wiki/showcase/springtrail-board.svg` is built
from. Sampling changes no input, no checkpoint and no capture: the host test
holds the sampled and unsampled `full` runs to the same inputs, checkpoints,
final dot and capture CRC32s. Each sample is checked against all 23040 pixels
of the same expected image before it is retained, and a listed checkpoint
that is also a capture re-lists the frame already read rather than reading
again. Samples are recorded under `samples` in `result.json` with their
game index, model state, mask, CRC32 and packed file; they are wiki
material, not proof evidence.

## Measured result on the current image

All ten captures are proven on the current image by the runs below, against
the block-aware models and the retimed script above. No DUT fixture
publishes a block column ([coverage limit](BLOCKS.md#coverage-limit)), so
the block-aware expected image rests on this board evidence alone.

Image `35aae757bde0ec9a15d6d6c84f14b45b451c341d2d4775f43ed8a9a762625192`
built from current sources at each launch, anchor 167840 derived by the
launcher and recorded in `build.json`, wire build
`87d5f0280a2afad8be6b85dc601141cc` on COM3, Python 3.14.5, pyserial 3.5,
2026-09-12. Doctor: JTAG PASS (`10M50DA`, idcode `031050DD`), Quartus PASS,
UART enumerated COM3; Questa refused its nodelocked licence to a second
seat, and no simulation is part of this proof. Both runs used
`python src/dv/springtrail/frame_proofs.py <plan> --uart-port COM3 --expected-build-id 87d5f0280a2afad8be6b85dc601141cc --tag frames453`,
serialized under the machine mutex, each after the endpoint's build identity
and paused/neutral preflight and before any input.

| Plan | Whole (s) | Worker (s) | Checkpoints | Captures | Checked pixels | Epoch | Final dot | Result |
|---|---|---|---|---|---|---|---|---|
| `short` | 22.3 (cap 300) | 22.0 | 101 | 4 | 92,160 | 8 | 7,264,560 | PASS |
| `full` | 47.8 (cap 300) | 47.6 | 627 | 10 | 230,400 | 10 | 44,202,384 | PASS |
| `full --showcase` (tag `sc440`) | 108.7 (cap 300) | 106.8 | 627 | 10 (+40 samples) | 230,400 (+921,600) | 12 | 44,202,384 | PASS |

The `full --showcase` row is the same day's session that built
`wiki/showcase/springtrail-board.svg`: the same ten captures with the same
sequences, completion dots and CRC32s as the `full` row, plus 48 samples (40
extra snapshots, 8 re-listed captures) each matching all 23040 pixels; its
59 s over the plain run is the 40 snapshots at about 1.5 s each.

Every capture carried the load's epoch, its planned sequence and a
completion dot 251 to 254 dots into row 143 of its frame (`title` at
303523, `scroll-wrap` at 14769667, `won` at 33519475, `retry` at 42718822,
`retry-restart` at 44193523), and matched all 23040 pixels. Applied inputs,
in VBlank order: 161 at 2, 33 at 3, 49 at 99/151/355 with 33 twelve VBlanks
after each, 49 at 227 with 33 at 228, 128 at 473, 0 at 474, 33 at 494, 128
at 604, 0 at 605; every reply dot equalled its checkpoint. Frame CRC32s:
`title` 9b162de2, `spawn` 2a877964, `first-camera` 18129d7a,
`entering-column` a3f88cd6, `scroll-wrap` 1ac1a983, `camera-clamp` 47fd650a,
`won` fdaaedff, `retry` 60258ecc, both restarts e1736456. Every value but
`scroll-wrap` equals the one the previous image gave: those frames show no
block, and `scroll-wrap` now carries the item block at world column 38..39
that its old value 278fed6e drew as blank terrain. Both runs ended PAUSED,
UART source, input 0, effective 0, with the durable session certain
(sequence 232014 after `full`). Retained per run under
`workdir/builds/frames453/frames/`: `build.json`, `session.json`,
`budget.json`, `journal.json`, `result.json`, every packed frame and its PNG.
Captures verify pre-VGA source frames, not monitor output.

### The run that found the block layer

The session below preceded the block-aware models and used tag `frames437`:
its expected frames came from `motion_frames.image` over the frozen flow of
`interactions_reference`, and its script held A for twelve VBlanks at the
second gap. It is kept because its failure is the oracle the host test holds
the block-aware image to.

| Plan | Whole (s) | Worker (s) | Checkpoints | Captures | Checked pixels | Epoch | Final dot | Result |
|---|---|---|---|---|---|---|---|---|
| `short` | 24.0 (cap 300) | 23.7 | 101 | 4 | 92,160 | 4 | 7,264,560 | PASS |
| `full` | 27.3 (cap 300) | 27.1 | 208 reached | 4 of 10 | 92,160 | 4 | — | FAIL `FRAME_PIXELS scroll-wrap pixel=12848` |

`short` passed every check: `title` completing at 303523, `spawn` at 514195,
`first-camera` at 2831588 and `entering-column` at 7255699, each the load's
epoch, its planned sequence and 251 or 252 dots into row 143 of its frame,
matching all 23040 pixels with CRC32s `9b162de2`, `2a877964`, `18129d7a`,
`a3f88cd6`, the same values the previous image gave. Applied inputs 161 at
VBlank 2, 33 at 3, 49 at 99, 0 at 101; every reply dot equalled its
checkpoint. The board ended PAUSED, UART source, input 0, effective 0,
certain session.

`full` matched the same four captures, then failed at `scroll-wrap` (source
frame 207, camera 256): the 256 mismatching pixels are exactly the 16x16 cell
x 48..63, y 80..95, world column 38..39 rows 10..11, the first intact item
block. The board draws the block art the image has carried since the block
layer; `motion_frames.image` draws blank terrain there, and the frozen flow
behind `games()` carries no block or power state. The captured state matched
`EXPECTED['scroll-wrap']`, so the anchor and the route held through that
capture and the pixel model was behind the image. The run kept its dot,
journal and packed frames; cleanup sent HALT and INPUT 0 and the board ended
PAUSED at input 0. Those 256 pixels are the oracle
`test_block_layer_is_the_only_difference_from_the_terrain_model` holds the
block-aware image to. The board did not reach the second-gap jump, so the
held jump's stall against the brick, which the block-aware model predicts at
update 260, was not observed; the retimed script above is the model's route.

## Measured result on image 616de11b...

This evidence belongs to image
`616de11b49e0807539837358824a570776459b9bf13a4b9424dbf42adfe5c983`, whose
anchor was 139388 (`C(n) = 139388 + n*70224 + 4096`, title at C2=283932).
The block layer and the power states lengthened startup after it, so it is
not evidence for the image the repository builds today.

Producing commit `55827b65` (the declaration), Python 3.14.5, pyserial 3.5,
wire build `bb02588d127b72ce6458a07ff1145c57` on COM3, that image built from
the sources of the time at each launch. The board was not reprogrammed. Doctor: JTAG
and Quartus PASS, UART enumerated COM3; Questa refused a second nodelocked
licence, and no simulation is part of this proof. Both runs used
`python src/dv/springtrail/frame_proofs.py <plan> --uart-port COM3 --expected-build-id bb02588d127b72ce6458a07ff1145c57 --tag frames384`,
serialized under the machine mutex, each after the endpoint's build identity
and paused/neutral preflight and before any input.

| Plan | Whole (s) | Worker (s) | Checkpoints | Captures | Checked pixels | Epoch | Final dot | Result |
|---|---|---|---|---|---|---|---|---|
| `short` | 23.3 (cap 300) | 23.0 | 101 | 4 | 92,160 | 33 | 7,236,108 | PASS |
| `full` | 49.2 (cap 300) | 49.0 | 627 | 10 | 230,400 | 35 | 44,173,932 | PASS |

The `short` run measured 0.064 s per checkpoint over the 96 checkpoints
between `spawn` and `entering-column`, giving a `full` forecast of about
60 s before it ran. Every capture carried the load's epoch, its planned
sequence and a completion dot in row 143 of its frame (`title` at 275071,
`won` at 33491023, `retry` at 42690370, `retry-restart` at 44165071), and
matched all 23040 pixels. Applied inputs, in VBlank order: 161 at 2, 33 at 3,
49 at 99/151/227/355 with 33 twelve VBlanks after each, 128 at 473, 0 at
474, 33 at 494, 128 at 604, 0 at 605; every reply dot equalled its
checkpoint. Frame CRC32s: `title` 9b162de2, `spawn` 2a877964, `first-camera`
18129d7a, `entering-column` a3f88cd6, `scroll-wrap` 278fed6e, `camera-clamp`
47fd650a, `won` fdaaedff, `retry` 60258ecc, both restarts e1736456, the same
value the pause proof records for its Select-restart frame. Both runs ended
PAUSED, UART source, input 0, effective 0, with the durable session certain
(sequence 223470 after `full`). Retained per run: `build.json`,
`session.json`, `budget.json`, `journal.json`, `result.json`, every packed
frame and its PNG. Captures verify pre-VGA source frames, not monitor output.
