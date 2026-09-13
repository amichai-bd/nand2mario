# Stackdrop execution proof

The [game contract](../../../wiki/src/sw/stackdrop/SPEC.md) owns behavior.
The independent `reference.py` and `cases.py` select all expectations before
execution. The original CPU unit performs73 updates: all28 rotations with
release/held history, horizontal/gravity/drop boundaries, one/four cleared rows,
score saturation and spawn failure/restart. Complete state, decimal score and
all96 board cells are reconstructed from public committed writes at every
checkpoint. Fifteen group ends prepare all118 image bytes for comparison.
The four-row clear additionally copies the full image to VRAM and checks all118
ordered address/data writes. No expected-result data is stored in the ROM.

The game and unit place rules/render/tables at identical addresses; verify their
complete linked section bytes. A separate entry in the same original unit ROM
stops normally after its first three updates. Its short target exercises the
same load, terminal marker, HALT, END and artifact path before the full run.

## Bounds fixed before runtime

Instruction-count upper bounds, rounded upward: Shape116 dots, Address220,
Valid1800 (four cells), Prepare6500 (96 board cells, four active cells,16 preview
clears, four preview cells and six HUD cells), ClearRows12600 (12 eight-cell
scans/copies, at most96 top clears and four score increments), Lock17000 including
spawn. One hard drop performs at most13 Valid calls, followed by Lock; including
update dispatch,42000 bounds any selected update. Combined with Prepare6500,
ReadButtons/Render4472 and loop/wake overhead below256, this is below53204,
leaving over17000 of70224 dots. These are conservative source bounds, not
measured timing claims.

For the fixed73 calls, at most40 ordinary collision checks plus13 hard-drop
checks, five locks, two board resets,15 prepared images and15 operand loads,
with1800 per extra spawn check and all call/marker overhead, fit under500000
dots. This explicit bound includes initialization and the one VRAM copy. The
short entry has only three updates and one preparation. Actual durations and
frontiers must be recorded; no unchanged timeout retry is authorized by a bound.

The local Render bracket must measure4496 dots:4472 for the two calls plus24
for loading/storing the end marker. The composed game must separately check
actual VBlank start to last VRAM write, including HALT wake/dispatch, and that
Update/Prepare finishes before the following VBlank. A local bracket alone does
not establish that whole-frame schedule.

Each simulation targets120 seconds and retains the300-second whole-process cap.
Run the short complete target first, then the full unit and its one intended
fault. The fault changes one actual WRAM store after the first update marker;
subsequent CPU reads preparing the image must fail the unchanged image oracle.
No product RTL behavior or positive stimulus changes for the fault.


## Whole-game timing

The instruction-derived LCD enable commit is141000 dots. The prefix is128 dots
through setting the768-byte clear count,36852 for that clear,36 setup+40764
for784 tile bytes,36 setup+53244 for1024 map bytes,5564 for the initial title
Prepare call,4312 for Render, then64 for palette/IE/LCDC setup. The checker
rejects a different LCD commit immediately; the observed value never selects
its oracle.

Drive one real UART Start128 at171000..173000, safely before the first VBlank.
Check all69120 pixels of startup white, title and the first playing image.
The first VBlank copies the prepared title and computes NewGame; the second
copies that prepared playing image. For each complete copy check all118 ordered
VRAM writes within the real4560-dot window, and the final WRAM preparation byte
before the following VBlank. Check per-line pixel time, epoch, shade and every
retirement's sequence/time. Normal HALT after the third checked image may leave
an exact prefix of the next VBlank copy; this is explicit and does not claim that
third update complete. The first two update/copy windows are complete proofs.

`python-stackdrop-game` is this short composed proof, with existing300-second
whole cap. The static host fixture exercises its complete pixel/VRAM/input/end
checks and rejects a bad pixel, input window, VRAM deadline and prepare deadline.
Its source/state selection is independent of DUT outputs. The game package and
pixel decoder are also reused for root's separate manual FPGA development play;
that early session does not replace the full remaining simulation criteria.

## Board boot-and-play session

**This is boot-and-play evidence, not a correctness proof.** The rules, score
and board contents are proved above against the independent reference model;
nothing in this section re-checks them, and no result here may be cited as a
correctness claim. What it shows is that the built image loads, boots, renders
and answers scripted input on the DE10-Lite, and that the ordinary host
commands drive it.

[board_play.py](board_play.py) opens one ordinary host session (device lock,
durable sequence journal, machine mutex, verified wire build, paused valid image
with neutral UART input) and runs a frozen script. It reuses `screen.decode` on
each captured frame, so every observation comes from the rendered image and no
gameplay WRAM is read. Frames, PNGs, decoded states and `result.json` stay in
the ignored `workdir/stackdrop-play/`; the transaction journal stays under the
build tag. No frame bytes or decoded images are committed.

```text
python tools/build.py sw build stackdrop --tag <tag> --json
python tools/build.py host load --package workdir/builds/<tag>/sw/build/stackdrop/runs/<attempt>/result.json --tag <tag> --json --uart-port <verified-port> --uart-vid <vid> --uart-pid <pid> --uart-identity <verified-identity>
python src/dv/stackdrop/board_play.py --uart-port <verified-port> --uart-vid <vid> --uart-pid <pid> --uart-identity <verified-identity> --expected-build-id <reviewed-wire-id> --tag <tag>
```

The loaded image is ordinary session state. Loading Stackdrop replaces whatever
was resident; Springtrail reloads the same way, and no Springtrail result may be
claimed from a session where Stackdrop was loaded.

### Modes

Two phases, recorded per frame. **Free-run** runs the board continuously and
paces with wall time: it reaches the title, and after the row clear it advances
gravity alone at native rate. **Stepped** executes exact whole frames with
`RUN_DOTS 70224`, so each press lands on its own released-to-pressed edge and
one-row-per-second gravity never runs ahead of a capture.

### Recorded scripted session

This session ran against the **pre-restyle** Stackdrop image, built before the
artwork was redrawn. Its frame CRC32 values therefore belong to that earlier
tile atlas and are not reproducible from the current source. The decode contract
is unchanged across the restyle, so `board_play.py` needs no change to drive the
current image; that has not been rerun on hardware.

Wire build `87d5f0280a2afad8be6b85dc601141cc`, ABI 1. The image is the
`stackdrop` target built from commit `896e4e49`, fingerprint
`c440581dbba0ba4abaf94e931b6bbb06ca0df83695c8947612b659de8672c251`, ROM SHA-256
`af11fbfae2ddf1607ca3c70f32d47eadb62fd5a1c5b5c3f3ead8ea6f2afa0c74`;
`host load --package` transmitted and read back all 32768 bytes and reported a
valid, paused, direct-profile image. The session began and ended PAUSED with
`INPUT` 0, `INPUT_SOURCE` 0, `INPUT_EFFECTIVE` 0 and session certain. `RESET`
opened snapshot epoch 77. Whole-process wall time was 28.9 s.

The script fills the bottom row from the frozen I, O, T, L, J, S, Z cycle: I
left two columns and hard-dropped to columns 0..3, O right one and dropped to
4,5, T left two and parked above them, then L rotated once, moved right three
and dropped into 6,7. Each press is held three whole frames and released for
three. Every frame decoded without a rejected tile.

| # | Frame | Mode | seq | dot | CRC32 | Status | Score | Changed |
|---|---|---|---|---|---|---|---|---|
| 0 | title | free-run | 117 | 8398539 | `d7cb2cbf` | title | 0 | |
| 1 | start | stepped | 123 | 8819883 | `fdd759f8` | playing | 0 | 167 |
| 2 | i-left-1 | stepped | 129 | 9241227 | `6367d833` | playing | 0 | 72 |
| 3 | i-left-2 | stepped | 135 | 9662571 | `d1d6fbb0` | playing | 0 | 72 |
| 4 | i-drop | stepped | 141 | 10083915 | `e99b7503` | playing | 0 | 432 |
| 5 | o-right | stepped | 147 | 10505259 | `a76c1e49` | playing | 0 | 144 |
| 6 | o-drop | stepped | 153 | 10926603 | `7a24f869` | playing | 0 | 432 |
| 7 | t-left-1 | stepped | 159 | 11347947 | `791f5f15` | playing | 0 | 144 |
| 8 | t-left-2 | stepped | 165 | 11769291 | `b2275c9f` | playing | 0 | 144 |
| 9 | t-drop | stepped | 171 | 12190635 | `80141334` | playing | 0 | 432 |
| 10 | l-rotate | stepped | 177 | 12611979 | `14bef34a` | playing | 0 | 226 |
| 11 | l-right-1 | stepped | 183 | 13033323 | `49b631a7` | playing | 0 | 216 |
| 12 | l-right-2 | stepped | 189 | 13454667 | `20d71e38` | playing | 0 | 216 |
| 13 | l-right-3 | stepped | 195 | 13876011 | `10fc41a3` | playing | 0 | 216 |
| 14 | l-drop | stepped | 201 | 14297355 | `daebf3a5` | playing | 100 | 740 |
| 15 | gravity-free-run | free-run | 441 | 31151115 | `8cc4b5bb` | playing | 100 | 288 |

Frame 0 is the title with an empty well, reached by free running from `RESET`.
Frame 14 is the locking hard drop: the bottom row was removed, the surviving
rows shifted down, and the visible score changed from `0000` to `0100`. Frames
0..14 span 201 source frames of emulated time; the free-run tail then ran 240
more source frames in four wall seconds with no input, and the spawned piece
descended four rows, which is the frozen one-row-per-second gravity observed at
native rate.

### Played from the phone viewer

The board owner played Stackdrop from the authenticated phone page over the
Cloudflare tunnel, using the eight tap buttons and both viewer modes. Two images
were played, and they are separate claims:

- the **pre-restyle** image this scripted session loaded, ROM SHA-256
  `af11fbfae2ddf1607ca3c70f32d47eadb62fd5a1c5b5c3f3ead8ea6f2afa0c74`;
- the **current** image, ROM SHA-256
  `f2a9b159743a202541dd17dedaa99ffcc7ebf6d9d7012b28f4701a0ac9aed927`, rebuilt
  from the restyled source and loaded with all 32768 bytes verified on readback.

Nothing about one image's play is evidence about the other. Both sessions show
the same thing and nothing more: the image loads, boots, renders and answers
input from the viewer on real hardware, and the viewer works on an image other
than Springtrail. The [viewer contract](../../../wiki/tools/n2m/host/LIVE_VIEWER.md)
owns the tap, mode, history and release semantics; the viewer never loads, resets
or programs the board.

One viewer run record is retained for the run that served the current image:
`status` PASS, `released` true, `uncertain` false, 216 captures over 436.3 s in
free-run mode, stopped cleanly through its STOP file. It is the operator run that
put the restyled image in front of the owner, not a record of the owner's own
tapping.

The loaded image remains ordinary session state, and none is resident now: the
board was globally reset by KEY0 after these sessions, which clears the loaded
image, frame ownership and transport state. Reload any image with
`host load --package` before the next session.
