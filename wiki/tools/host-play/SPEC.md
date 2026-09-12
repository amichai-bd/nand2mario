# Original UART play loop

The [host-play driver](../../../tools/n2m/host_play.py) implements this bounded scenario. It uses the existing [host Client](../n2m/host/SPEC.md), [input owner](../../src/rtl/input/MAS_input.md) and [immutable snapshot](../../src/rtl/snapshot/MAS_snapshot.md). It adds no hardware register or commercial-game interpretation.

The original ROM draws one solid 8-by-8 background tile at map column8,row8. All other map entries and tile0 are explicitly cleared by CPU instructions while LCD is off. Tile1 has low bytes FF and high bytes00. SCY is0. BGP E4 maps tile color1 to shade1; EC maps it to shade3. SCX0 places the object at (64,64); SCX F8 places it at (72,64). The ROM selects the direction row at JOYP and polls Right/Left. Right chooses F8, Left chooses0, and neither preserves position. A press selects EC; release selects E4. No DMA, timer or interrupt handler is used.

The host identifies and loads the original image with complete readback, explicitly selects UART input authority, and uses WRITE_HOST on INPUT for every complete mask. It locates the object from decoded snapshot pixels before choosing Right when x=64 and Left when x=72. Releases follow each press. The independently fixed observations are:

| Observation | Mask | Object x,y | Shade |
|---|---|---|---|
| Initial | 0 | 64,64 | 1 |
| Right | 1 | 72,64 | 3 |
| Release | 0 | 72,64 | 1 |
| Left | 2 | 64,64 | 3 |
| Release | 0 | 64,64 | 1 |

Every other pixel must be shade0. The decoder requires exactly5760 packed bytes, earliest pixel in bits1:0, and produces a160-by-144 grayscale image. Recognition requires exactly one solid64-pixel object with the stated8-by-8 bounds, not a position inferred from the input count. Game interpretation remains in host software.

Each change occurs while host-paused, followed by RUN, a bounded observation interval, HALT and SNAPSHOT with all READ_FRAME chunks. Initial execution permits200000 dots including map setup and startup blank frame; later changes permit150000 dots, more than two70224-dot frame periods plus the bounded polling loop. The latest completed snapshot must have sequence at least1, the load epoch2, and strictly increasing sequence and dot after the first observation. No second SNAPSHOT occurs during readback. The exact publication remains immutable while bytes are read. Failure or uncertainty stops the loop without automatic retry or recovery.

The host loop takes an existing Client and a bounded run-wait callback, so the same command/image path can support later authorized physical operation. Simulation waits observe only elapsed public dots; they do not signal game position or alter product state. Physical execution still requires the repository hardware checks and is not part of this simulation evidence.

Verification uses the real UART byte transport, CPU/memory, JOYP/IF, PPU, frame bridge and dedicated Intel snapshot stores. Actual wrong snapshot data, missing frame completion, wrong button and missing release updates must fail the host's independent checks. These faults do not alter the expected image. Portable image/metadata/failure tests and current-head review complement the composed checks; the [v0.5 matrix](../../src/dv/v05/SPEC.md) and [integration contract](../../src/dv/integration/SPEC.md) retain their separate acceptance.

The host-play fixture uses the shared 25 MHz system clock, an eight-system-edge UART bit period (3.125 Mbaud), and a separate 25.2 MHz pixel clock. Its watchdog permits one second of simulation time, preserving the former 25-million-system-edge budget for full ROM load/readback and five snapshot downloads. The original 800000-dot sequence and independent image expectations remain unchanged.

The target obeys the [300-second total simulation cap](../n2m/SPEC.md#test-wall-budget), including setup, compilation, run and checking. The declared frame-wait callback permits 300 seconds but cannot extend the outer deadline; serial-response progress retains 120 seconds and the Client wire timeout remains in simulated time. These host limits do not change the game, pixel or frame-freshness expectations. Existing longer historical runs do not establish feasibility under the new cap. Physical execution has a separately declared duration and sampling plan.

## Springtrail state reconstruction

The [state reader](../../../tools/n2m/springtrail_state.py), the
[acquisition and player](../../../tools/n2m/springtrail_play.py) and the
[entrypoint](../../../tools/springtrail_player.py) add a second observation mode
beside the pixel loop above. The pixel loop proves what the PPU actually drew.
This mode reads the game's own records over [PEEK](../n2m/host/SPEC.md) and
reconstructs the scene from them. The two answer different questions and are
never substituted for one another. The [how-to](springtrail-state.md) shows the
commands; the [game spec](../../src/sw/springtrail/SPEC.md) owns the rules whose
state is read.

### Image and layout binding

The decoder carries a version and a table of qualified images. Each entry binds
one ROM SHA-256 to the digest of the symbol layout that image was linked with.
Addresses come from the linker's `symbols.json` inside the same immutable
[packaged attempt](../sw/SPEC.md) as the ROM, so no game address is written in
the tool. Binding fails, before any port is opened, when the image is not
qualified, when a required symbol is missing, when the layout digest differs, or
when a symbol falls outside WRAM. A new image is qualified by adding its pair,
not by relaxing the check.

The reader asks for the smallest ranges that cover the bound symbols, merging
neighbours that are closer together than the cost of a second request. For the
current image that is one 132-byte PEEK at the base of WRAM, against 8192 bytes
for the whole store and 5760 for a frame. Each request stays within the
generated payload limit.

### Coherent paused acquisition

Pausing freezes hardware; it does not mean the software finished a game update.
The game runs one update per frame: the VBlank interrupt sets `FramePending`,
the main loop consumes it, samples the buttons and publishes the scene prepared
by the previous update, then waits for the visible interval and runs
`UpdateGame` and the scene preparation. Reads taken during that update return a
record that is partly new and partly old.

The reader therefore requires a paused core at **LY 145 through 152 with
`FramePending` clear**, and advances the core in exact `RUN_DOTS` counts until
it is there. In that window the previous update and its scene preparation have
completed, the next update does not start until LY 0, and this frame's button
sample is already stored, so the observation covers exactly one completed
update. A flag that never clears, an LCD that never enables or a short
`RUN_DOTS` stops the reader instead of returning a partial record.

Three views exist at that boundary and are labelled, never interchanged:

| View | What it is | Relationship |
|---|---|---|
| `logical` | The game records the observation returns. | The state of the last completed update. |
| prepared scene | The OAM published in this same VBlank. | Prepared from the same state; first displayed in the next source frame. |
| last completed display | What `SNAPSHOT` returns at this boundary. | The frame drawn from the previous boundary's state, so one behind the observation. |

Every observation carries the decoder version, ROM identity, completed dot,
reset epoch, LY, the boundary it represents and the request and byte counts.
Each reconstructed image is labelled reconstructed and carries that provenance.
An aligned comparison therefore matches the image reconstructed at one boundary
against the snapshot taken at the next.

### Refusal rules

The decoder returns a complete observation or an error. A missing range, a
short range, a range at an unexpected offset, two replies for the same range,
a value outside the game's contract or an unqualified image are refused. No
field is ever filled from an earlier action, a previous observation or a model
prediction.

The field checks include the camera's relation to the player position. That is
a cheap secondary check, not the protection against a partly written record:
the camera is `clamp(x/16 - 72, 0, 608)`, so wherever the clamp is active — the
first 72 pixels and the right end of the level, which includes the title and
the completion states — the camera does not move with the player and a torn
record passes it unseen. **The paused acquisition boundary above is what
prevents tears.** The check is kept because it costs nothing and catches the
scrolling cases, and its blind case is pinned by a test so it is not mistaken
for a guarantee.

### Autonomous play

The player loop observes, chooses one complete eight-button mask, advances an
exact whole number of frames and observes again. Because the ROM samples the
buttons once per VBlank, a mask written at one boundary is sampled at the next
and first applied by the update after that; the strategy reads the sampled mask
from the observation and plans from the update it is already committed to.

The strategy is a receding horizon over the independent reference models. From
the committed state it rolls out candidate actions under a continuation policy
that presses A when one more walking update would step off the ground, holds it
while the jump is rising and releases it otherwise, and keeps the candidate that
survives and travels furthest. Deliberate jumps are candidates in their own
right, which is how the player passes the enemy. Read-only terrain and the
enemy's patrol band may guide the choice. The models look ahead; they never
supply state.

Each advance is checked against the ROM's own counters: the LY phase must be
unchanged, the completed dot must have advanced by exactly the frames requested,
the reset epoch must be unchanged and the game timer must advance once per frame
while the game is playing. A drift in any of them stops the run.

The loop declares its action, emulated-frame and wall budgets and its retry
policy before it runs, and reports a failed attempt rather than retrying past
them. It stops on bounded lack of progress. It writes no game memory: the only
host writes are the input mask and the input-source selector. On ordinary
completion it releases the input and leaves the core paused; after an uncertain
completion it sends nothing further, and says so rather than claiming cleanup
succeeded.

### Comparing against actual pixels, and measuring

An observation and the frame drawn from it are one boundary apart, so a
comparison has to fetch them that way round. `observe --snapshot` observes,
advances exactly one frame and takes the snapshot there, so the frame it
returns is the actual-pixel counterpart of the observation beside it.
`compare` does the same at each of five checkpoints while the autonomous player
runs: the title and start, a jump, the camera scrolling, a dynamic object or
power change, and completion. Each checkpoint is claimed by the first
observation that is an example of it. All 23040 shades are compared; a
disagreement, or a checkpoint the run never reached, fails the comparison and
is reported with the first differing pixel. No expected pixel is taken from the
dump, and no framebuffer byte is used to build the state image.

Both paths report what they cost. Every mode writes a `measurements.json` with
a median, a range and a sample count per figure, each named for exactly what it
measures:

| Figure | What it covers |
|---|---|
| `boundary_seconds` | reaching the coherent boundary, alone |
| `read_seconds` | the selected PEEK reads |
| `decode_seconds` | turning those bytes into structured state |
| `state_seconds` | boundary, read and decode together |
| `render_seconds` | reconstructing the image from that state |
| `image_seconds` | total image availability: state plus render |
| `snapshot_seconds` | fetching one actual frame, metadata and all chunks |
| `compare_seconds` | comparing 23040 shades |
| `loop_seconds` | one complete observe, decide, advance, observe action |

Transferred bytes and request counts are reported per path beside them, from
the binding and the generated frame ABI. `observe --repeat N` takes N
successive observations and summarises them in one run, so a sample population
needs no aggregation by hand. **Every figure is whatever that run measured on
that endpoint; none is a contract, and figures measured against the host
fixtures are not board latency.**

### Evidence

A fake endpoint serves state from the reference models over the real wire
codecs, so the reader, decoder, renderer, strategy and comparison run without a
simulator or a board. Its fixtures are produced by the model itself, so every
fixture state is one the ROM can hold. The
[state checks](../../../src/dv/springtrail/test_state_reader.py) cover binding,
decoding, refusal, the camera check's blind case and reconstruction; the
[play checks](../../../src/dv/springtrail/test_state_play.py) cover the
boundary, settling advances, the publication delay, the aligned pair, the
checkpoints, a complete WON run, adaptation to a changed start time and to a
changed enemy phase, and the input, no-progress, budget and uncertain-session
rules; the
[entrypoint checks](../../../src/dv/springtrail/test_state_player.py) cover the
retained artifacts, the reported measurements, a full five-checkpoint
comparison and a deliberate disagreement.

Board execution is not part of this evidence and remains open under
[#472](https://github.com/amichai-bd/nand2mario/issues/472). No timing figure
for this path has been measured on hardware; the payload-only arithmetic in the
[host SPEC](../n2m/host/SPEC.md) is not a result for it.
