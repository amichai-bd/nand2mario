# Observing and playing Springtrail from game state

Two ways to see what the board is doing, and what each one proves.

| | Actual-pixel snapshot | State reconstruction |
|---|---|---|
| Command | `python tools/build.py host snapshot` | `python tools/springtrail_player.py observe` |
| Reads | 5760 packed bytes of the completed source frame | selected WRAM ranges, 151 bytes for the current image |
| Proves | what the PPU actually drew | what the game's own records say |
| Shows | the last completed display | the last completed update, drawn by the host renderer |
| Works for | any loaded image | only a qualified Springtrail build |

The snapshot is evidence about the hardware. The reconstruction is evidence
about the software, drawn by the same independent renderers the game checks use.
A reconstruction that disagrees with a snapshot is a finding, not a rounding
error: ask for a real snapshot and compare. They are one frame apart by
construction, so compare the image reconstructed at one boundary against the
snapshot taken at the next.

The [SPEC](SPEC.md#springtrail-state-reconstruction) is normative for the
binding, the boundary and the refusal rules; the
[host commands](../n2m/host/SPEC.md) own the protocol.

## Build the image, then observe

Both commands take an immutable packaged attempt, never a loose ROM.

```text
python tools/build.py sw build springtrail --tag <tag> --json
python tools/springtrail_player.py observe --tag <tag> \
    --package workdir/builds/<tag>/sw/build/springtrail/runs/<attempt>/result.json
```

`observe` pauses at the coherent boundary, reads the bound ranges, writes
`observation-0000.json` and a reconstructed `observation-0000.png` under
`workdir/builds/<tag>/springtrail-player/observe/`, and leaves the core paused.

Add `--snapshot` to fetch the actual frame that matches the observation. It
advances exactly one frame first, because that is where the frame drawn from
the observed state completes, then compares all 23040 shades and reports the
first difference if there is one.

Add `--repeat N` to take N successive observations in one run. Each lands on
the next boundary, and the run writes one `measurements.json` summarising all N,
so building a sample population does not mean collecting result files by hand.
Both flags advance the core, which is how the boundary is reached at all; with
the input released the title and completion states stay put while they do.

The JSON holds the structured state an agent reads:

```text
mode / mode_name         TITLE, PLAYING, RETRY, PAUSED, WON, TIMEUP or OVER
player                   x, y, vx, vy in sixteenths and pixels, grounded, fell,
                         pose, facing, jump state and index, walk counter
camera, published_camera scroll position and the value the STAT split writes
enemy                    x, vx, alive
items                    collected bitmap and score
power                    state, phase, timer, invincibility, throw, crouch
shot                     x, y, vx, vy, ttl
blocks                   per-block state, coins, release effect, dirty column
progress                 stage, packed-BCD lives/countdown, pending request,
                         subdivision and expiry state
hud                      the word and score the HUD shows
buttons                  sampled (in flight), applied, game_previous
timer, frame_pending     update count and the VBlank flag
```

Every record carries the decoder version, the ROM SHA-256, the completed dot,
the reset epoch and the boundary it represents. The image record is labelled
`RECONSTRUCTED`, so a picture pulled out of an artifact directory cannot be
mistaken for a frame the hardware drew.

## Debugging with it

Read the fields, not the picture, when you want to know why something looks
wrong. A player that will not move has `buttons.sampled` to check first: it is
the mask the ROM actually sampled, so it separates a host input problem from a
game rule. A scene that looks stale has `camera` against `published_camera`. A
character that falls through the floor has `grounded`, `jump` and `y`. When the
reconstruction and a real snapshot disagree, the state fields say which side
moved.

## Play it

```text
python tools/springtrail_player.py play --tag <tag> \
    --package workdir/builds/<tag>/sw/build/springtrail/runs/<attempt>/result.json \
    --wall-seconds 240
```

The loop observes, chooses one complete eight-button mask from the observation,
advances whole frames and observes again, from the title to WON. It declares its
budget before it starts, reports a failed attempt instead of retrying past it,
writes no game memory, and on ordinary completion releases the input and leaves
the core paused. Every observation is retained as JSON; images are written at
`--image-stride` (60 by default). `actions.json` holds the mask, the reason, the
completed dot and the observed position of every step, so a run can be reviewed
or replayed by eye afterwards.

A language model does not need a tool call per frame: the loop is ordinary
Python, and the retained observations and action records are what an agent reads
to supervise it or to take over.

## Compare the two views

```text
python tools/springtrail_player.py compare --tag <tag> \
    --package workdir/builds/<tag>/sw/build/springtrail/runs/<attempt>/result.json
```

`compare` plays the level and, at the title and start, a jump, the camera
scrolling, a dynamic object or power change, and completion, captures the
aligned actual frame and compares every shade against the reconstruction. It
writes `comparisons.json`, both images per checkpoint, and `measurements.json`.
A disagreement, or a checkpoint the run never reached, fails the run and names
the first differing pixel.

The measured figures are listed in the
[SPEC](SPEC.md#comparing-against-actual-pixels-and-measuring). `compare` gives
a large sample of the state path and the action loop and one sample per
checkpoint of the actual-pixel path; `observe --repeat N --snapshot` is the way
to build a comparable sample of the actual-pixel path on its own.

## Limits

Physical execution needs the repository's hardware authorization, the verified
setup and serialized board access. Until that runs, no latency figure for this
path has been measured on hardware: the numbers a run prints are what that run
measured, and the payload-only arithmetic in the host SPEC is arithmetic, not a
result. The decoder is bound to the exact qualified image: a different build is
refused rather than guessed at. The current profile decodes all three stages,
including TIMEUP, OVER and stage-relative terrain and limits. Its second HUD
row reconstructs the observed lives, countdown and stage. The play command
still stops at a stage win; this is not qualification of an autonomous full
campaign. Physical current-image proof remains tracked in [#485](https://github.com/amichai-bd/nand2mario/issues/485).

The camera check the decoder applies is a secondary one. It is blind wherever
the camera clamp is active, which includes the title and the completion states;
the paused boundary is what keeps a record from being read half-written.

### Delayed start and verified exit

For a changed-start rehearsal, add `--start-delay-frames 37` to `play` or
`compare`. The default is zero. The delay starts after RESET and the first
coherent TITLE observation, with neutral input; each frame is retained as a
`start-delay` action within the existing budgets. Observe rejects this option
when nonzero.

Observe first selects neutral UART input and pauses through ordinary controls.
All three modes verify PAUSED and effective input zero on a certain exit.
Cleanup rejection or mismatched readback makes the result FAIL; an earlier
failure remains beside the cleanup finding. An uncertain session sends no
further commands and cannot claim successful cleanup.
