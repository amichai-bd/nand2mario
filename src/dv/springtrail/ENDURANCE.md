# Continuous UART play and lifecycle

Proof for [#264](https://github.com/amichai-bd/nand2mario/issues/264) under
its remote scope and for the retired [#291](https://github.com/amichai-bd/nand2mario/issues/291)
child, under the [physical contract](../../../wiki/src/dv/springtrail/SPEC.md#physical-acceptance).
Everything is observed over UART: no monitor, keyboard or physical button is
claimed. Product ROM/RTL remain unchanged.

## Gameplay qualification gap

The source-built image/anchor checks remain active. The static gameplay frame
oracle predates progression and does not qualify the current 90-cycle route:
it omits retry life spending, OVER and neutral countdown changes.
[The required correction](https://github.com/amichai-bd/nand2mario/issues/511)
owns coherent scheduled expectations. Existing host doubles qualify transport,
duration and cleanup control flow only; they are not current-game FPGA evidence.

## Retained script

Frozen before execution; `endurance.py` is the launcher and driver.

Image binding: the launcher runs `sw build springtrail` from current sources
and passes the build's own image hash to the driver, which refuses any other
bytes (`ENDURANCE_ROM`) before opening a directory or sending a command. No
hash constant is stored. The expected wire build is given on the command line
and checked against the endpoint's build identity before traffic. The board's
paused snapshot supplies the prior reset epoch; each `Client.load` adds two
and each explicit RESET adds one.

Expected frames come from the independent models only: `motion_reference`
for the player, the frozen flow in `interactions_reference` (parametrised by
that player) for modes, enemy, items and goal, and `motion_frames.image` for
pixels. LCD commit 167840 and period 70224 are the source-derived anchors of
the current image ([derivation](FRAME_PROOFS.md#startup-anchor)); `build_rom`
refuses an image that derives any other dot. No value is taken from the DUT.

Setup, paused: load with full 32768-byte upload and byte-exact readback,
INPUT 0, dot 0, advance by RUN_DOTS to C2=312384 and check every pixel of
`title` (source frame 1); Start 128 at C2, C3, release 0, C5=523056 and check
every pixel of `play` (spawn, frame 4). Then RUN; the monotonic origin is
taken after the RUN reply.

Continuous interval, RUNNING throughout, no HALT/RUN_DOTS/RESET/load: `short`
runs 2 fixed 20-second cycles (40 s), `full` runs 90 (1800 s). Cycle i:

1. Apply 33 (Right+B, even i) or 17 (Right+A, odd i); hold 5.5 s. Both
   routes run into the first gap from spawn and end in a settled RETRY:
   33 at x187/camera115 after 110 updates, 17 at x183/camera111 after at
   most 267 (the A-first sample variant). Check `retry-<route>` when the
   frame completes at least 280 periods after the applied dot: 23040
   pixels minus the enemy patrol projection x(240-camera)..(303-camera),
   y120..135 (560 pixels for 33, 496 for 17). The host tests prove every
   JOYP first-sample variant (0, direction row, action row, both) and every
   enemy phase reach the same terminal, that it stays settled while held,
   and that the exclusion is exactly the union of enemy pixels.
2. Release 0, wait 0.1 s, Start 128, wait 0.15 s, check every pixel of
   `play` at least 3 periods after the applied dot; release 0. Only one
   JOYP row changes per transition here, so no variant exists.
3. Cycles 0, 30 and 60 additionally press Start for `paused` and again for
   `play` (resume), each checked the same way.
4. Stay RUNNING until the fixed boundary. A cycle over 20 s fails; the next
   must begin within 1 s of its fixed start.

Every sample checks PAUSED/RUNNING state, valid image, UART source, host and
effective mask equal to the commanded one, 64-bit dot/retirement counters
read without tearing, epoch, frame size, completion inside row 143 of its
numbered frame, freshness within 2 periods, and increasing sequence/dot.
The RETRY sample also requires dot and retirement progress over the previous
cycle. Retained per sample: packed frame, its hash, metadata and both counter
readings; the journal holds every applied input dot. This is sampled
endurance: 2 samples per cycle plus pauses, not every frame.

End: one extra second, check `play` while still RUNNING, require both the
monotonic and the emulated (dot delta at 4194304/s) durations to cover the
planned seconds, HALT, INPUT 0. Then three explicit RESET / full load with
readback / title / Start / `play` cycles with the same checkpoints. Final
state PAUSED, UART, input 0, effective 0, certain session.

Failure: any assertion or transport error ends the run FAIL with the dot,
state and journal retained; cleanup attempts HALT and INPUT 0 only when the
Client is certain, and an uncertain completion sends nothing more. The
worker refuses to start a cycle or a lifecycle after `cap-24` s; the
launcher kills the worker tree at `cap-12` s and records `budget.json`.
Caps: 300 s short, 1980 s full. Forecast: short about 110 s (40 s
continuous, four loads, 15 samples); full about 1870 s (1800 s continuous,
four loads, 195 samples, 4,000,000-plus checked pixels). The short run
exercises both routes, pause/resume, the final sample and all three
lifecycles before the full run. No automatic extension or replay.

### Measured result on the current image (35aae757...)

Image `35aae757bde0ec9a15d6d6c84f14b45b451c341d2d4775f43ed8a9a762625192`
built from current sources at each launch, anchor 167840 (C2=312384,
C5=523056) derived by the launcher and recorded in `build.json`, wire build
`87d5f0280a2afad8be6b85dc601141cc` on COM3, Python 3.14.5, pyserial 3.5,
2026-09-12, producing commit `a8137875`. The board was not reprogrammed.
Before any board traffic the frozen routes were replayed through the
block-aware model (`power_reference.update`, `blocks_frames.image`): every
JOYP first-sample variant and every enemy phase reach the same terminal as
the frozen model, no route touches a block (the nearest, world column 38,
lies past both gap falls), and the five sample images are pixel-identical.
Doctor: JTAG PASS (`10M50DA`, idcode `031050DD`), Quartus PASS, UART
enumerated COM3; Questa refused its nodelocked licence to a second seat,
and no simulation is part of this proof. `host status` read build
`87d5f028...`, ABI 1, PAUSED, valid image, UART, input 0 before traffic.
Both runs used
`python src/dv/springtrail/endurance.py <plan> --uart-port COM3 --expected-build-id 87d5f0280a2afad8be6b85dc601141cc --tag en452`,
serialized under the machine mutex.

| Plan | Whole (s) | Continuous (s) | Dots | Samples | Checked pixels | Loads | Epochs | Result |
|---|---|---|---|---|---|---|---|---|
| `short` | 102.7 (cap 300) | 42.409 | 177,267,435 | 15 | 344,544 | 4 | 14..23 | PASS |
| `full` | 1862.5 (cap 1980) | 1802.419 | 7,559,289,113 | 195 | 4,445,280 | 4 | 25..34 | PASS |

The full run sampled 90 RETRY frames (45 per route), 98 `play`, 3 `paused`
and 4 `title` frames, applied 386 inputs, and kept the core RUNNING from the
origin `play` sample to `continuous-final` at frame 107586, dot
7,555,352,563, 343,571,860 retired instructions; the dot counter crossed its
32-bit boundary inside epoch 25 (first seen at sample `051-retry`) without
a torn read. Every load uploaded and read back all 32768 bytes. Both runs
ended PAUSED at dot 523056, UART, input 0, effective 0, with the durable
session certain (sequence 237515, then 250515). The title frame completing
at dot 303523 = 167840 + 70224 + 143*456 + 251, the last pixel of row 143,
corroborates the derived anchor on hardware. No reset, hang, lost input or
pixel mismatch occurred.

[PR475](https://github.com/amichai-bd/nand2mario/pull/475) records both runs:
the exact commands, the per-run build, budget, session, result and journal
records, every retained packed frame and the transaction journals, with the
independent review that recomputed each number from them.

Sampling limits: two samples per cycle plus pauses; the RETRY samples exclude
the enemy patrol footprint. Nothing here observes the monitor or physical
controls.

### Earlier result on image 616de11b...

This result belongs to image
`616de11b49e0807539837358824a570776459b9bf13a4b9424dbf42adfe5c983`, whose
anchor was 139388 (C2=283932, C5=494604). The block layer and the power
states lengthened startup after it; the current-image result above
supersedes it and this record is kept as history.

Producing commit `e3bdf69` (the freeze; rebased with identical content as
`f36c0b3`, then onto #385 as `bfa9654`: the only driver change is the call
`flow_update(game, buttons, step=step)`, because `interactions_reference`
now derives the restart player from `type(game.player)`; `SPAWN` already
holds the motion player, so behaviour is unchanged and the run was not
repeated), Python 3.14.5, pyserial 3.5, wire
build `bb02588d127b72ce6458a07ff1145c57`, image
`616de11b49e0807539837358824a570776459b9bf13a4b9424dbf42adfe5c983` built from
current sources at each launch (cache hit, same bytes). The board was not
reprogrammed. Doctor: JTAG, Quartus and UART PASS; Questa refused a second
nodelocked licence, and no simulation is part of this proof. Both runs used
`python src/dv/springtrail/endurance.py <plan> --uart-port COM3 --expected-build-id bb02588d127b72ce6458a07ff1145c57 --tag endurance264`.

| Plan | Whole (s) | Continuous (s) | Dots | Samples | Checked pixels | Loads | Epochs | Result |
|---|---|---|---|---|---|---|---|---|
| `short` | 105.3 (cap 300) | 42.483 | 177,550,584 | 15 | 344,544 | 4 | 11..20 | PASS |
| `full` | 1865.9 (cap 1980) | 1802.413 | 7,559,303,931 | 195 | 4,445,280 | 4 | 22..31 | PASS |

The full run sampled 90 RETRY frames (45 per route), 98 `play`, 3 `paused`
and 4 `title` frames, applied 386 inputs, and kept the core RUNNING from the
origin `play` sample to `continuous-final` at frame 107585, dot
7,555,253,887, 335,479,229 retired instructions; the dot counter crossed its
32-bit boundary inside epoch 22 without a torn read. Every load uploaded and
read back all 32768 bytes. Both runs ended PAUSED at dot 494604, UART, input
0, effective 0, with the durable session certain (sequence 208401, then
221401). The title frame completing at dot 275071 = 139388 + 70224 + 143*456
+ 251, the last pixel of row 143, corroborates that image's anchor on
hardware. No reset, hang, lost input or pixel mismatch occurred.

Sampling limits: two samples per cycle plus pauses; the RETRY samples exclude
the enemy patrol footprint. Nothing here observes the monitor or physical
controls.

## Retired-image schedule (b551c562...8ba667)

Use corrected ROM b551c56252761d953bcf3b64270d819e3342b710299c3bff6866d4dcae8ba667
and the reviewed current board image. The caller binds fresh setup, image/source,
fit/SOF, certain durable session and preceding accepted physical frontier before
traffic. `Client.load` performs every byte of upload/readback. Each load advances
the reset epoch twice; each explicit RESET adds one. No snapshot epoch is guessed
from image contents.

Initial load reaches C2=221508 with exact RUN_DOTS and checks full title. Apply
Start128, advance C3=291732, release0, advance C5=432180 and check PLAY0. These
are setup operations before the continuous interval, using the fixed LCD76964,
period70224 and previously verified single-frame preparation delay.

The short executes one20-second cycle; the full executes90 such cycles for1800
seconds. RUN returns before the monotonic start timestamp, conservatively
measuring an already-running system. Each cycle:

1. Apply Right+B+A49 and wait3 seconds. Its first91 logical updates run/jump,
   collect item0, scroll and fall into the first gap. The frozen terminal state
   is RETRY, x200/y146, camera128, collected1/score1. Check its settled image.
2. Apply Start128, wait0.1 seconds and check restored PLAY0/spawn; release0.
3. In cycle0 only, wait0.1, press Start128, wait0.1 and check PAUSED; release0,
   wait0.1, press Start128, wait0.1 and check PLAYING; release0.
4. Stay RUNNING until the fixed cycle boundary. A cycle that overruns20 seconds
   fails; the next cycle must begin within1 second of its fixed start.

Every press retains its value across the snapshot readback, comfortably beyond
one JOYP sample. Only stable post-transition images are selected. Snapshot
completion must follow each relevant application by at least3 frame periods;
the RETRY sample follows49 by at least120 periods. Full bytes are retained.
PLAY/PAUSED/title compare23040 pixels. RETRY compares22656, excluding only the
enemy's possible patrol projection x112..159/y120..127 at camera128. Its phase
depends on prior idle length; all other pixels and score/mode are independent.
The player falls before reaching patrol minimum240, so every legal enemy phase
has the same terminal player/camera/item result. Host tests check this invariant.
At spawn the patrol is completely offscreen, including during game pause.
For a0-to49 change between JOYP row reads, the possible first masks0/1/48/49
converge to that same terminal result while49 remains held. Start changes only
the action row; the settled sample tolerates the earlier or later update.

One extra second after the final boundary accommodates clock phase; then check
the final PLAY image while still RUNNING. Require both monotonic duration and
public dot delta to cover the planned20/1800 seconds at4194304 dots/second.
Only then HALT. No host HALT/RUN_DOTS/RESET/load/source switch occurs inside the
continuous interval. Brief ordinary in-game pause is an input action, not a host
pause. Samples check state/image/UART/effective mask, rollover-safe64-bit counters,
increasing retirement/frame/dot identity, source completion timing and reset epoch.
This is sampled endurance, not observation of every retirement/frame or transient.

Finally perform three explicit RESET/full load-readback/title/Start/PLAY cycles
using the same setup checkpoints. End PAUSED/UART/input0/effective0/certain.
Failure and cleanup exceptions retain FAIL; uncertain transport permits no more
commands. The caller owns released session/lock and whole-process evidence.

## Finite acceptance and budgets

- Host checks: independent terminal/region invariants, complete short fake lifecycle,
  pixel/epoch/stale/input/progress/duration/lifecycle/cleanup failures. These test host
  infrastructure, not FPGA fault injection. Existing qualified actual faults remain
  in PR276/PR282/#263.
- Short physical: one complete cycle plus all three lifecycle cycles and cleanup,
  existing300-total supervisor. Accepted short whole time83.205 seconds includes
  22.425 continuous seconds and all three lifecycle cycles.
- Full physical: the short measured overhead gives1863.205 seconds extrapolated;
  forecast1900 with1980 total hard cap, including initial full load,1800 continuous
  seconds, three complete lifecycle cycles, checking and cleanup. Interrupt the
  worker at1956; outer tree cleanup starts by1968 and every wait uses the remaining
  deadline. This is not a simulation exception or a paused-batch workaround.
  No automatic extension/replay.
- Final source/setup/runner review precedes hardware. Exact commands, raw results,
  input/sample journals, immutable artifacts, measured wall time and final current
  head review are required. No full acceptance is claimed from the short case.

[PR295](https://github.com/amichai-bd/nand2mario/pull/295) records the accepted full
run:1802.403 continuous seconds,90 gameplay cycles,191 sampled images with
4,366,080 checked pixels, all three lifecycle cycles and safe final state.
Whole physical time1863.033 seconds met the declared cap. The PR owns commands,
raw records, failure history, source qualifications and independent review.
This completes only the automated child proof, not the outstanding actual
VGA/keyboard/shared physical-control gates in #264/#417/#156.

## Image scope

The retired-image schedule and its PR295 result apply to image
`b551c56252761d953bcf3b64270d819e3342b710299c3bff6866d4dcae8ba667` only; #310,
#314, #316, #318, #321 and #301 separate it from the current build and change
every displayed frame. That result cannot be read as covering the current
image. The current-image script above is the endurance script for the image
the repository builds; its measured result belongs to that image
(`35aae757...`, anchor 167840), and the earlier `616de11b...` record is
history. The deterministic per-image evidence for the current build is the
[re-qualification section](MILESTONE.md#current-rom-re-qualification).
