# Stackdrop

Stackdrop is an original, silent falling-block side quest for the existing
32 KiB direct-entry SM83 profile. The [game source](../../../../src/sw/stackdrop/main.asm)
and pixel-based Python strategy do not replace Springtrail
or the hardware milestone criteria. The following rules are frozen for implementation.

## Board and pieces

The well is eight columns by twelve rows, with no hidden rows. Coordinates start
at the upper left. Empty and occupied cells are binary; pieces cannot overlap
occupied cells or cross any edge. The fixed repeating cycle is I, O, T, L, J,
S, Z. These are mathematical four-cell shapes, with original art and layout.
Each uses a 4-by-4 local grid:

| Piece | Spawn cells (x,y) |
|---|---|
| I | (0,1), (1,1), (2,1), (3,1) |
| O | (1,0), (2,0), (1,1), (2,1) |
| T | (1,0), (0,1), (1,1), (2,1) |
| L | (2,0), (0,1), (1,1), (2,1) |
| J | (0,0), (0,1), (1,1), (2,1) |
| S | (1,0), (2,0), (0,1), (1,1) |
| Z | (0,0), (1,0), (1,1), (2,1) |

A piece spawns at local origin (2,0), rotation zero. For I, clockwise rotation
maps (x,y) to (3-y,x); O remains unchanged. For other shapes rotate within their
3-by-3 region using (x,y) to (2-y,x). There are no wall kicks. Reject a colliding
move or rotation without changing state. No random state, held piece, hidden
preview queue, music or speed level is required. Independent table checks require
four distinct occupied cells in every orientation and return to the spawn shape
after four rotations.
## Inputs and update order

Start on the title starts a fresh game; Start after game over returns directly
to a fresh game. Start during play is ignored. A new game clears the board,
score and gravity counter, and starts the cycle at its first I piece. The initial
screen is a title with an empty well. Spawn overlap ends the game.

Read ordinary JOYP once per VBlank, with both row reads forming one software
sample. Actions occur on released-to-pressed edges. Opposed Left/Right cancel;
otherwise move one cell horizontally. Then A attempts one clockwise rotation.
B hard-drops to the last valid row and locks; otherwise Down attempts one row
and resets the gravity counter, locking if blocked. With neither drop edge,
increment the counter; at 60 updates attempt one row, reset the counter and lock
if blocked. Hard drop takes precedence over Down and gravity. Up and Select
have no effect. Holding an action does not repeat it; release is required.

After locking, remove all full rows simultaneously, preserving the relative
order of surviving rows and inserting empty rows at the top. Award 100 points
per removed row, saturating at 9999. Advance the cycle and spawn immediately,
then prepare the next image. A new piece receives no further actions in the locking update.
The previous input sample persists across spawning and restart, preventing a
held button from becoming a new edge. Gameplay advances only on frame updates;
host HALT is separate and freezes emulated time through the existing interface.

## Visible encoding

Use original background tiles with identity palette E4. The well begins at
pixel (48,24); each cell is one 8-by-8 tile. Empty cells have shade0 interiors,
locked cells shade2 interiors, and active cells shade3 interiors. Borders and
original tile details must not obscure the center 4-by-4 classification region.
The well's fixed rectangle is the public visual coordinate system.

A next-piece preview occupies a 4-by-4 tile box at (120,32), using the same
spawn geometry. Four original decimal digit tiles at (64,128) display the score
with leading zeroes. A fixed status tile at (32,16) visibly distinguishes title,
playing and game over. An original decimal tile at (32,24) shows rotation0..3, including visually equivalent I/O orientations. Document the literal tile atlas beside its source.
Decode board, active cells, next piece, digits and status from these rendered
pixels, rejecting unknown or mixed encodings. No gameplay WRAM reads, sprite
MMIO shortcut or RTL debug port is part of the host interface.

At each VBlank, sample both JOYP rows, copy the previously prepared image to VRAM, then calculate the sampled action and prepare the next image in ordinary WRAM during visible time. The resulting state becomes visible at the following VBlank: this one-frame pipeline delay is intentional. Initialization prepares the title before enabling LCD. Each update must finish before the next VBlank, including the worst lock, multiple-clear and score case; the prepared map copy must fit within4560 dots. Actual CPU timing checks cover both bounds. All map changes complete in VBlank before the next visible image. The game
uses ordinary CPU code, VRAM and JOYP; it does not disable LCD around updates
or replace the existing PPU. Hardware snapshots are complete immutable images,
not every-frame verification. During manual play the agent may HALT, inspect a
snapshot, decide an action, then INPUT/RUN/HALT through normal commands. It must
retain actual applied and paused dots, release edges and frame metadata rather
than assuming host sleeps advance an exact number of frames.

## Finite verification

Independent integer rules and literal images cover every piece rotation,
edge/stack collision, both drops, locking, single and multiple clears, score
saturation, spawn failure and restart. An original CPU unit ROM calls the same
linked game routines and reports through existing passive public write traces;
no expected state is embedded in that ROM. A deliberate changed result must
fail the unchanged checker. A short actual-system test checks startup, input and
rendering through the existing Intel preload and continuous Python facilities,
including normal completion and final pause. Target 120 seconds per simulation;
the existing 300-second whole-process hard cap remains in force.

The manual FPGA proof uses the reviewed board build and verified setup, complete
UART upload/readback, and snapshot-derived action choices. Show legal movement,
rotation, hard drop and a scored line clear from a fresh game, retaining full
images and journals. End PAUSED, UART selected, input/effective mask zero and
session certain. Stop on uncertain transport completion. Automated play uses the
comparative higher-score proof below.

## Pixel player comparison

The pixel player uses the immutable rendered snapshot, including the visible
rotation digit and next-piece preview, to identify the active piece and board.
It rejects ambiguous geometry and stale frame identities. It reads no gameplay
WRAM. Each decision is retained with the actual frame and resulting UART action.

Freeze two runs before physical execution: baseline always hard-drops; strategy
enumerates reachable placements using legal left, right and clockwise rotation
edges, then hard-drops. Score each resulting board as 1000 times cleared rows,
minus50 times holes, minus5 times summed column heights, minus2 times adjacent
height differences. A hole is an empty cell below an occupied cell in its column.
Prefer higher score, then fewer actions, then lexicographic action order
Left, Right, Rotate, Drop. There is no lookahead or parameter tuning between runs.

Both runs load the same original ROM af11fbfae2ddf1607ca3c70f32d47eadb62fd5a1c5b5c3f3ead8ea6f2afa0c74,
start a fresh game, and stop after eight issued B-edge actions or game over.
This is not eight total piece locks: gravity may lock a piece during an action.
Each has the
same64-action ceiling and300-second whole-process deadline, including cleanup.
An action-limit or deadline failure is incomplete evidence, not a selected score.
The strategy must obtain a strictly higher visible score than the baseline;
all outcomes remain recorded without selecting a favorable restart.

Before each edge, advance neutral input across at least two actual frame periods;
hold the chosen edge across at least three. Measure progress through public dots,
not wall-clock sleeps. Decode a new complete image after each action and plan
again from that observation so gravity or pipeline latency is not hidden state.
Execute only the first edge of the selected path, never the entire stored path.
Use the existing verified device/build, immutable package, durable session,
machine lock and packet journals. Warm load derives the new epoch from the
observed old epoch plus two; it does not reset session history. End each certain
session PAUSED with UART input zero; uncertain completion remains blocked.
