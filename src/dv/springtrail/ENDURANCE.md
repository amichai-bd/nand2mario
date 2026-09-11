# Continuous UART play and lifecycle

Proof for [#291](https://github.com/amichai-bd/nand2mario/issues/291),
under the [physical contract](../../../wiki/src/dv/springtrail/SPEC.md#physical-acceptance).
This does not close #264/#28/#156 or prove monitor/keyboard/physical buttons.
Reuse the accepted #263 deterministic baseline and qualified actual faults;
do not repeat its every-frame acquisition. Product ROM/RTL remain unchanged.

## Frozen schedule

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
VGA/keyboard/shared physical-control gates in #264/#28/#156.

## Image scope

Everything above applies to image
`b551c56252761d953bcf3b64270d819e3342b710299c3bff6866d4dcae8ba667` only. The
repository now builds
`adbef6b04b5ca7c3896beace71b1735b6dd49115feda0c6ebe20f11ae109f369`; #310, #314,
#316, #318 and #321 separate them, and the last three change every displayed
frame. `endurance.py` calls `require_baseline_rom`, so the driver refuses any
other image and the recorded 90-cycle result cannot be read as covering the
current one.

Continuous physical endurance on the current image is therefore unproven. #264
owns it. The deterministic per-image evidence for the current build is the
[re-qualification section](MILESTONE.md#current-rom-re-qualification).
