# Every-frame milestone schedule

[#263](https://github.com/amichai-bd/nand2mario/issues/263) preserves boot within600
frame intervals followed by3600 scripted intervals. Host-paused full-frame
acquisition is approved; [#283](https://github.com/amichai-bd/nand2mario/issues/283)
delivered its reusable driver in PR284. [PR288](https://github.com/amichai-bd/nand2mario/pull/288)
records the complete paused DUT execution of the matrix below.
[#286](https://github.com/amichai-bd/nand2mario/issues/286) owns delivery of the
complete native schedule/ledger prerequisite; it does not close #263.

Freeze the corrected32768-byte ROM SHA256
`b551c56252761d953bcf3b64270d819e3342b710299c3bff6866d4dcae8ba667`, untouched
SameBoy Core213a12ce93d66b105a113debd9396306066a7cfc and direct DMG_B profile.
PR282's two clean builds and refreshed same-byte build qualify image provenance.
The old PR279 image/reference remains historical.

Use source-defined LCD commit76964, period70224 and checkpoint
`C(n) = 76964 + n*70224 + 4096`. Indices below are zero-based source sequences:

| Event | Exact fixed identity |
|---|---|
| Capture at C(n), n>=1 | Source sequence n-1; native callback n+1; all23040 pixels |
| Boot | C1 captures blank sequence0; C2 captures title sequence1, within600 |
| Input i, 0<=i<3600 | Apply while paused at C(2+i), sample in VBlank of frame2+i |
| Consequence of input i | Compute in visible frame3+i, publish in VBlank3+i, display frame4+i |
| Last scripted input | C3601; compute frame3602; display frame3603 |
| Drain | Neutral inputs at C3602/C3603; capture every interval through C3604 |
| Total retained images | Source sequences0..3603 plus both native initialization callbacks |

Inputs never depend on observed pixels, CRC or frame metadata. Native key calls
occur at the first instruction boundary at/after the same checkpoint, at most24
dots late; that visible-phase allowance cannot intersect the VBlank JOYP sample.
The native runner continues to the final checkpoint after its last full callback.
Neutral drain execution remains in the reference interval; it is not a reset or
an omitted interval. Display lag means its newly computed state is not required
to appear in a frame that was already complete.

`milestone.py` freezes the script: the existing original success route, ordinary
Start restart, existing death/retry route, pause/resume and Select restart, then
success/restart routes repeated to3600 updates. Fixed checkpoints include WON360,
death RETRY548, Start retry549, pause551/resume553, pause555/Select restart557,
and pause558/resume560. Later wins occur920/1281/1642/2003/2364/2725/3086/3447.
The final scripted state is PLAYING, score1, camera256; no expected state comes
from a DUT. Repeated contact/once-only score and exact restoration component
proofs from PR276 remain qualified separately from this full frame sequence. Its first
new route holds Start from the restart, preserving edge semantics. The short
complete lifecycle uses four updates129/1/1/1 and two neutral drains, eight source
frames, allowing two four-frame acquisition batches. PR287 qualified the full
route/model and native execution before the full DUT matrix.

Every batch must finish within300 seconds including identity checks, run, full
readback, comparison, pause and cleanup. Measure the short lifecycle before
choosing full batch size and declaring aggregate wall time. Preserve exact ROM,
build, epoch, sequence, paused dot, input history and native ledger across batches;
no reset, replay or skipped frame may recover an incomplete batch. Image/pixel/
input/progress fault coverage and current-head review remain required. #264's
continuous physical milestone and #417/#156 remain separate.

## Native completion

The existing probe's explicit `springtrail-milestone-short` case executes eight
normal callbacks and continues to checkpoint642852; the full
`springtrail-milestone` executes3604 normal callbacks and continues to253168356.
Retain the two initialization callbacks, schedule.json, every row-major image,
actual key applications and terminal record. End may be at most24 dots after the
fixed checkpoint because the native public API advances an instruction. No
additional normal callback is allowed. Normal callback spacing must be70224.

The checker compares every pixel with the independent original model, and checks
sampled C019/mode using fixed indices. At native callback j, displayed model state
is update max(0,j-5); sampled input is zero for j<5 and script input j-5 otherwise;
logical mode is update max(0,j-4). Initial callbacks and first normal frame are
blank. No callback, mask or offset is selected from DUT observations.

The native pre-run forecast was10 seconds short and60-180 seconds full, including
model image comparison; measured results follow below. Each invocation keeps
the existing300-total/288-worker/12-cleanup supervisor and canonical mutex.
The input fault changes actual key API masks. The milestone progress fault stops
after the final required callback but before the terminal checkpoint, requiring
END_TIME rejection despite complete frame/input counts. Legacy progress faults
retain their original100000-dot stop. This is actual truncated execution;
frame fault remains explicitly a serialized-image mutation. Native execution
is complete as recorded below. The full acquisition aggregate was declared after
short native/acquisition measurements, before the full hardware matrix.

| Fault boundary | Scoped evidence and remaining witness |
|---|---|
| Immutable image | PR282 rejects old image identity before native tools; PR284 validates full upload/readback and rejects changed expected image/hash before acquisition. Repeat full corrected-ROM load/readback only at the full-run origin. |
| Actual DUT pixel | PR276's real source-shade mutation and unchanged checker rejection, qualified in PR282; native serialization/host readback mutations only test their own new infrastructure. |
| Input | PR287 actual zero-key fault fails INPUT_MASK on the new schedule. PR284 checks exact applied mask/dot and rejects mismatched transport/plan input; full execution retains every checkpoint. |
| Progress | PR287 actual exit after all callbacks before the fixed checkpoint fails END_TIME. PR284 rejects partial RUN_DOTS, missing/duplicate frames and unbound continuation. |

These proofs complement every-frame positive execution; they do not claim a
host-file mutation is an actual DUT defect or remove any required interval.

## Native result

The complete short at c736d40 retained10 callbacks/eight normal frames/six inputs,
ending642856 in6.047 seconds. Its unchanged executable behavior is qualified
across the child-worktree move; the producing artifacts remain in263.
Full b44ad16 passed in27.741 seconds:3606 complete images,3604 normal frames,
3602 inputs and exact end253168356. Measured qualification0.071s, build4.720s,
link0.428s, native execution3.667s and image checking17.978s are component timings,
not an exhaustive disjoint wall total.

At f91c8dd, serialized-image/input/late-progress faults failed their intended
BLANK_FRAME/INPUT_MASK/END_TIME checks in5.928/5.562/5.343 seconds. The progress
case retained all callbacks/inputs but ended634196 before642852. Every raw tool
and native command exited0; intended checker failures returned outer1. Aggregate
50.621 seconds met300; each invocation met120 target and300 hard limit. The fault
branch changes no positive behavior. [PR287](https://github.com/amichai-bd/nand2mario/pull/287)
owns exact commands, identities and review. No DUT/full milestone acceptance is
inferred from this reference result; #263 retains the full DUT comparison.

## Full paused acquisition budget

The reviewed short lifecycle in [PR284](https://github.com/amichai-bd/nand2mario/pull/284)
captured four frames after full ROM load/readback in18.089420 seconds and four
more in a separate continuation in8.336349 seconds. All eight frames matched
the native reference. These measurements preceded selection of80-frame batches.

The full run uses46 batches:45 batches of80 frames and a final batch of4.
Scaling the continuation measurement gives166.727 seconds per80; adding the
measured9.753-second first-load difference gives176.480 seconds for the first80.
Allow200 seconds per80 for full83,082,240-byte reference validation, cumulative
checkpoint/artifact verification and other overhead. Forecast about2h35 total
physical wall time including coordination; the completed native50.621-second
matrix is recorded separately. These are forecasts, not guaranteed runtimes.
Individual80-frame batches are expected to miss120-second targets. Every batch
still has a300-second total hard limit, including setup, comparison and cleanup.

The first80 is the beginning of the one full execution history, not a disposable
timing run. Before advancing, verify its actual successful outer supervisor,
all80 complete frames/pixels, input frontier and durable checkpoint, then review
the measured remaining forecast. Never reset/replay the first batch to improve
its timing. Every continuation binds the preceding successful outer result,
checkpoint and artifact hashes, same ROM/build/epoch, paused dot, input history
and complete native ledger. Cumulative validation stays inside each300-second cap.
Any timeout or incomplete checkpoint stops further advancement for concrete
failure review; missing intervals cannot be repaired by silent replay or reset.

The first invocation verifies fresh device/setup and the reviewed programmed
build, then performs the corrected-ROM full upload/readback and binds its actual
new epoch. Later invocations do not reload/reset. Serialized machine/session
access, exact RUN_DOTS completion, immutable full snapshot readback, final
PAUSED/UART/neutral/certain state and failure evidence remain mandatory.
Capture every source sequence0..3603 and input0..3601, including boot and both
neutral drain intervals. Retain/account both native initialization callbacks;
none are substituted for source frames. No physical buttons/camera or continuous
#264 release result is claimed by this paused verification.

## Full acquisition result

At producing commit204cefbb, all46 batches passed:3604 complete source frames,
83,036,160 compared pixels and3602 exact input checkpoints in one epoch6 history.
The initial corrected-ROM upload/readback verified all32768 bytes. The final
frontier was PAUSED at253168356 dots,6028674 retired instructions, UART input0
and a certain session. No reset, reload, replay or frame omission occurred after
the initial load. Captures verify pre-VGA source images, not monitor output.

Measured batch aggregate was5318.1169044 seconds (88m38s). First80 took127.3057574
seconds and exceeded the120-second target; every other batch met that target,
and all46 met300 seconds total. The final four-frame batch took12.9698733 seconds.
PR288 retains exact commands, immutable reference/setup/launcher identities,
all batch receipts and independent review. Later documentation changes do not
change the producing hardware, software, capture driver or reference inputs.

## Current-ROM re-qualification

[#351](https://github.com/amichai-bd/nand2mario/issues/351) owns this section.
Everything above describes the frozen `204cefbb` image and does not describe the
image the repository builds today.

### Image identity

`python tools/build.py sw build springtrail --tag issue351-rom --json` produces a
32768-byte image with SHA256
`adbef6b04b5ca7c3896beace71b1735b6dd49115feda0c6ebe20f11ae109f369`. The frozen
milestone image is `b551c562...8ba667`. They are different images. Five merged
changes to `src/sw/springtrail/` separate them: #310 and #314 core art, #316 the
shadow OAM DMA publisher, #318 courier composition and #321 the fixed HUD with
prepared columns. #316, #318 and #321 change what is drawn every frame, so the
every-frame acquisition and the frozen SameBoy reference profile in
`src/dv/sameboy/springtrail.json` remain bound to `b551c562...8ba667` only.

#301 has since replaced movement and animation, so the repository no longer
builds `adbef6b0...e109f369`. The HUD game checker pins that hash
(`hud_game_reference.py`, `HISTORICAL_HUD_ROM`) and refuses the current build,
so `python-hgs`, `python-hgu` and `python-hgx` are
[retired](#retired-targets); the rows below are the record of what they
established on that image. The composed proofs on the image the repository
builds today are `python-mgs` and `python-mgu`, whose checker pins no hash; the
[movement plan](MOVEMENT.md#measured-durations) records their results.

### Declared bounded checkpoint script

Declared before execution under the
[milestone reuse policy](../../../wiki/src/dv/integration/SPEC.md#milestone-acceptance),
which permits a selected bounded script over repeating 3600 intervals. The
selection covers the transitions the five changes actually affect; it does not
re-derive unchanged movement, collision or interaction rules, which keep their
own current unit qualification.

1. Short harness first: `python-hgs`. Reset, full UART upload/readback of the
   current image, LCD enable, the first 160 blank-frame pixels, the single
   initialization DMA publication, real HALT, the settled no-progress hold and
   trace END. This exercises the complete path, including final pause,
   completion and watchdog handling, before any longer run.
2. Selected script: `python-hgu`, one continuous history on the current image:
   - Boot: every one of 23040 pixels of source frame 0, blank, against the
     independent model.
   - Title: every one of 23040 pixels of source frame 1, including the fixed HUD
     row and the line-15 HBlank split, against the independent model.
   - First input: Start+Right (129) applied inside the declared window
     `lcd+60000 .. lcd+62000` dots. The applied dot comes from the INPUT reply;
     the public trace input record and the `0xc019` JOYP sample must agree with
     it. No expected value is selected from observed pixels.
   - Prepared-scene publication: both 160-byte shadow scenes at `0xc100`, both
     7-byte HUD tile caches at `0xc220`, the 32-byte prepared column cache at
     `0xc200` and all 480 published DMA bytes, each byte against the independent
     scene, HUD and column models.
   - Publication bounds: `0xff46` triggers in VBlank only, the 4480-dot
     completion ceiling, no interrupt or non-HRAM bus access during DMA, IRQ
     vector order `0x48,0x40,0x48,0x40` and exactly four split writes.
   - End state: paused with no fault, dot and record counts held across the
     settled interval.
3. Sensitivity: `python-hgx`, the accepted fault, so the pass is not vacuous.
4. Host reference and unit checks: `src/dv/springtrail` pytest suite.

Why this selection is representative of the changed path, not of the charter:
the [charter](../../../wiki/src/project-charter.md) names v0.9 as a boot
checkpoint within 600 frame intervals and then 3600 intervals of scripted
start/movement/action. This script covers only the boot, title, first-input and
publication path that the five ROM changes touch, end to end on the current
image, at full pixel resolution, through the changed renderer. It does not reach
the charter's movement/action intervals, and it deliberately does not claim
scrolling, win, death/retry, pause/resume or restart coverage on the current
image; #321's prepared columns also change scrolling frames the script never
reaches. No current target checks those full frames on this ROM, and that gap is
recorded below rather than implied away.

Budget: target 300 seconds per simulation. Measured results follow.

### Measured result

Python 3.12.14, cocotb 2.0.1, Questa Altera Starter FPGA Edition-64 2025.2
(2025.05), Intel memory models from Quartus 25.1, at commit `7d3fd49`, which is
the declaration commit above. Every run used the current image; each attempt's
`preload.json` records `image_sha256` `adbef6b0...e109f369`.

| Command | Whole seconds | Result |
|---|---|---|
| `python tools/build.py sw build springtrail --tag issue351-rom --json` | 1.2 | PASS, 32768 bytes, `adbef6b0...e109f369` |
| `python tools/build.py sw build springtrail --tag issue351-rom2 --rebuild --json` | 1.4 | PASS, same 32768 bytes and hash; two clean builds agree |
| `python tools/build.py sim test python-hgs --tag issue351-hgs --json` | 168.9 | PASS `hud_game_short`, 38.381802 ms simulated |
| `python tools/build.py sim test python-hgu --tag issue351-hgu --json`, attempt 1 (05:13:30Z) | 288 | FAIL, supervisor `TIMEOUT` at the 288-second execution deadline; 37600 of 46080 pixels reached |
| same command, attempt 2 (05:18:37Z) | 0.2 | FAIL, refused: tag `issue351-hgu` still locked by attempt 1; not a simulation |
| same command, attempt 3 (05:18:49Z) | 288 | FAIL, supervisor `TIMEOUT` at the same deadline; trace ends at the same record as attempt 1 |
| same command, attempt 4 (05:24:40Z) | 8.0 | FAIL, Questa refused a second nodelocked-licence instance; not a simulation |
| same command, attempt 5 (05:25:30Z) | 288 | FAIL, supervisor `TIMEOUT` at the same deadline; trace ends at the same record as attempt 1 |
| `python tools/n2m/test_budget.py sim test python-hgu --tag issue351-hgu-long --json`, attempt 6 (05:30:32Z) | 304 | FAIL, the target's own 300-second `vsim` timeout at 71.434068 ms simulated; all 46080 pixels reached, trace END not |
| same command, attempt 7 (05:36:44Z) | 302 (manifest span; no outer wall recorded) | FAIL, the same 300-second `vsim` timeout at 69.746180 ms simulated |
| same command, attempt 8 (05:42:17Z) | 301 | PASS `hud_game_full`, 71.687202 ms simulated; 293.6 seconds of cocotb test time |
| `python tools/build.py sim test python-hgx --tag issue351-hgx --json` | 168.3 | Intended checker FAIL `HUD_SPLIT_WINDOW`, outer exit 1, same first mismatch as PR321 |
| springtrail host fixtures, the `builder.yml` loader over `src/dv/springtrail/test_*.py` | 27.1 | PASS, 103 tests |

The passing full run reports 46080 checked pixels, 21603 retirement records,
LCD at dot 136560, shadow scenes ready at 134316 and 233236, 480 published DMA
bytes, 387 HRAM bus observations during DMA, the input applied at dot 196915
inside the declared 196560..198560 window, IRQ vectors `0x48,0x40,0x48,0x40`,
four line-15 split writes, two JOYP samples and a settled pause at 276826.

The fault target uses the same unchanged checker on the same current image, so
the positive result is not vacuous.

Read the `python-hgu` rows plainly: eight invocations, six of them full-length
simulations, five failures and one pass on the sixth simulation. The pass needs
71.69 ms of simulated time; the two unsupervised timeouts stopped at 71.43 ms
and 69.75 ms, on different sides of the wall, so the overrun is host-load
variance around the 300-second cap, not a fixed cost. The pass is a sixth-attempt
result at the edge of the budget, not a clean run. Receipts are the
`wall-budget` records under the `issue351-hgu` tag and the three attempts under
the `issue351-hgu-long` tag.

The overrun is not a defect in the game, the checker or the image. It is the
[test wall budget](../../../wiki/tools/n2m/SPEC.md#test-wall-budget): 300
seconds total, 288 for worker execution, unless the target declares a
`wall_allowance` up to 900 seconds. `python-hgu` declared none, so the
supervised command kept exactly 300 seconds. The target is retired without an
allowance; `python-pgu` and `python-pgx` declare theirs from this measured rate.
`tools/n2m/test_budget.py` is the worker the supervisor itself launches, so the
passing run used the unchanged builder, preload, checker and simulator command,
with the target's own 300-second simulator timeout still enforced; what it
skipped is the 288-second execution deadline and the `wall-budget` record. Its
measured 301 seconds is reported under the owner's authorization for an
individual test that demonstrably needs more than 300, and is far below the
900-second ceiling.

### What this does and does not establish

Established on `adbef6b0...e109f369`, the pre-#301 image: the blank boot frame, the title frame,
the first scripted input and its complete publication, every pixel of both
frames, and a settled paused end state, all against independent expectations.

Not established on that image by this script: scrolling frames, the win route,
the death/retry route and pause/resume/restart frames. The
[pause and restart proof](#current-image-pause-and-restart-proof) below adds the
first world frame, a neutral frame, the PAUSED frame and the Select-restart frame;
[FRAME_PROOFS.md](FRAME_PROOFS.md) captures scrolling, win and death/retry
frames from the paused board, since no simulation reaches them inside the
wall ceiling. The
46-batch every-frame acquisition and the 90-cycle endurance result above stay
bound to `b551c562...8ba667`; #264 still owns continuous physical endurance.

## Current-image pause and restart proof

### Retired targets

Eleven registered targets built the current image and then refused it, because
their checkers guard retired hashes. None could pass, so none is retained:

| Target | Checker and image | Disposition |
|---|---|---|
| `python-springtrail`, `python-gu` | `flow_reference` three-frame flow game on `97f5d9da...a593b513` | Retired. Boot, title, first input and publication are `python-mgu` on the current image; the first world frame is `python-pgu` below. |
| `python-gs` | `flow_reference` two-frame short harness | Retired; `python-mgs` and `python-pgs` are the current short harnesses. |
| `python-springtrail-x`, `python-gx` | `flow_reference` with the source-shade fault | Retired; `python-pgx` is the current-image fault. |
| `python-cgs`, `python-cgu` | `composition_game_reference` blank/TITLE/publication on `ec8dfb32...0d9e785f` | Retired; the same contract is `python-mgs`/`python-mgu` on the current image. |
| `python-cgx` | `composition_game_reference` with the wrong-piece OAM fault | Retired; `python-pgx` is the current-image fault. |
| `python-hgs`, `python-hgu` | `hud_game_reference` blank/TITLE/publication on `adbef6b0...e109f369` | Retired; the same contract is `python-mgs`/`python-mgu` on the current image, through the same `hud_game_check` driver. |
| `python-hgx` | `hud_game_reference` with the accepted-write fault | Retired; `python-pgx` is the current-image fault. |

The three historical reference modules keep their hash guards and host unit tests
so no consumer can silently apply their expectations to another image; their
cocotb drivers and entry modules are removed with the targets. No fixture of a
retired image exists in the repository, and none is added: a retained historical
proof would need a checked-in binary or a build from an old commit, which the
source policy does not provide.

### Declared script

Declared before execution under the
[milestone reuse policy](../../../wiki/src/dv/integration/SPEC.md#milestone-acceptance).
`pause_game_reference.py` freezes JOYP masks 129, 0, 128, 64 sampled in VBlank
0..3, with 64 held through VBlank 5. Mask n is sampled in VBlank n, computed in
visible frame n+1, published in VBlank n+1 and displayed in frame n+2. The
independent states come from the interaction flow rules over the current
motion model (`motion_reference`, `motion_frames`): title; PLAYING at x 25,
STAND, animation counter 2; PLAYING at x 25, STAND, animation counter 3;
PAUSED; PLAYING restarted at x 24 with the motion state reset, score 0, timer 0
and the enemy at 256; and one restarted update. Source frames 0..5 are
therefore blank, TITLE, the first world frame, the neutral frame, the PAUSED
frame and the Select-restart frame. Their literal CRC32 values are `b15161f6`,
`9b162de2`, `2a877964`, `2a877964`, `a20ef3f5` and `e1736456`. The neutral
frame repeats the first world frame's pixels because STAND holds until the
fourth animation step; its shadow state bytes, including the ten motion bytes
at `0xc060..0xc069`, still differ and are checked.

1. `python-pgs`: the complete short harness, the same driver stopped after the
   first 160 blank pixels, with real HALT, settled hold and trace END.
2. `python-pgu`, one continuous history on the current image:
   - Every one of 138240 pixels of source frames 0..5 against
     `hud_reference.image`, each row inside its 456-dot line.
   - Each scripted input applied through the ordinary UART INPUT path inside
     `lcd + n*70224 + 60000 .. 62000`; the reply dot, the public input record
     and the `0xc019` VBlank sample must agree. The restart's own rewrite of the
     sampled mask in visible time is the only visible-time `0xc019` write allowed.
   - All six 160-byte shadow scenes, six 7-byte HUD caches and the 160 bytes of
     prepared column caches, each against the independent scene, HUD and column
     models. The restoration counter model gives pairs (0,1), (2,3), (4,5) for
     the title start, then (0,1), (2,3) again after the restart.
   - Every display write of VBlank 0..5 in exact source order: the VBlank
     handler's SCX/SCY/LCDC writes, the 22 title clears and map reselect at the
     title exit, the map reselect at the restart, the restored column pair, both
     HUD maps and the DMA trigger. All seven DMA publications, 1120 bytes.
   - Publication bounds: DMA in VBlank only, the 4480-dot completion ceiling,
     no interrupt or non-HRAM bus access during DMA, IRQ vector order
     `0x48,0x40` per frame and twelve split writes.
   - End state: paused with no fault after VBlank 5's DMA, counts held across
     the settled interval.
3. `python-pgx`: the same script with `+pause_mode_fault`, which drops only the
   actual WRAM store of GameMode 3 to 1 while the public write stays 3. The
   next prepared HUD cache must fail the unchanged `PAUSE_HUD_CACHE` check.
4. Host fixtures: `test_pause_game_reference.py` in the springtrail suite.

Budget: `python-pgu` simulates about 140 ms and `python-pgx` about 100 ms. The
measured rate on the current image is 6.0 wall seconds per simulated
millisecond on a free seat (`python-pgu` below), so both exceed 300 seconds and
each declares a 900-second `wall_allowance` in `targets.json` with that measured
basis; `python-pgs` keeps the default 300. The full run leaves 56 seconds of
margin on a free seat and none under contention, so a licence refusal or a
concurrent simulation shows as a supervisor timeout, not a checked result.

Image binding: these targets pin no hash. The `springtrail` preload builds the
image from the current sources, and every expectation comes from the
independent models of the same rules and artwork: the flow rules of
`interactions_reference` over the motion model of `motion_reference`, rendered
by `motion_frames`. The first world state is the same state `python-mgu`
checks. The proof follows each source change only while those models follow
the same source; the run's `preload.json` records which image it checked. A
frozen hash belongs only to a proof whose expectations were fixed for one
retired image, such as the every-frame acquisition and the three historical
references above.

### Why scrolling, win and death/retry do not fit

The player starts at x 24; the camera is `max(0, x-72)`. Under the motion
model the earliest camera movement is update 34 with B and Right held from the
first update (`motion_reference.step`), displayed in source frame 35 at about
640 ms simulated; walking alone reaches it at update 52, frame 53. At the
measured 6.0 wall seconds per simulated millisecond that is about 3800 wall
seconds. The death/retry and success routes lie beyond the first camera
movement, so they are later still. Each exceeds the 900-second ceiling by at
least a factor of four, so no composed simulation target is declared for them.
[FRAME_PROOFS.md](FRAME_PROOFS.md) is the bounded physical script for those
frames.

### Measured result

Python 3.12.14, cocotb 2.0.1, Questa Altera Starter FPGA Edition-64 2025.2
(2025.05), Intel memory models from Quartus 25.1, on the tree rebased onto
`a1983ef` (#301's motion image). Every run used the image the build produced,
`616de11b49e0807539837358824a570776459b9bf13a4b9424dbf42adfe5c983` in each
attempt's `preload.json`. The three runs were serialized on one Questa seat with
no other simulation or fit; a first `python-pgu` attempt was refused a licence
by another QuestaSim instance after 9 seconds and was rerun.

| Command | Whole seconds | Result |
|---|---|---|
| `python tools/build.py sim test python-pgs --tag issue363b-pgs --json` | 227 | PASS `pause_game_short`: 294 pixels, one initialization DMA, HUD cache at 137588, settled pause at 140069, trace END; 219.0 s of cocotb time for 39.08 ms |
| `python tools/build.py sim test python-pgx --tag issue363b-pgx --json` | 723 | Intended checker FAIL `PAUSE_HUD_CACHE` at 94.08 ms, outer exit 1; 714.8 s of cocotb time |
| `python tools/build.py sim test python-pgu --tag issue363b-pgu-2 --json` | 844 | PASS `pause_game_full`, 139.12 ms simulated, 836.2 s of cocotb test time, inside the 900-second allowance with 56 seconds of margin |
| springtrail host fixtures, the `builder.yml` loader over `src/dv/springtrail/test_*.py` | 27 | PASS, 135 tests |

The short harness now uses 227 of its 300 seconds: #301's `InitMotionArt`
moved the LCD origin from 136560 to 139388 and lengthened startup, so its
margin fell from 79 to 73 seconds here and to 40 seconds in the independent
review's measurement on a loaded host.

The passing full run reports 138240 checked pixels, 34873 retirement records,
LCD at dot 139388, shadow scenes ready at 137144, 236260, 306004, 370448,
441744 and 516140, 1120 published DMA bytes, 903 HRAM bus observations during
DMA, inputs applied at 199642, 270003, 340154 and 410305 inside their declared
windows, six VBlank JOYP samples matching the script, the restart's two
visible-time sample rewrites (0, then 64) in frame 4, twelve split writes,
IRQ vectors `0x48,0x40` in every frame, 160 column cache bytes and a settled
pause at 559673 after the seventh DMA.

The fault run's actual store mutation is recorded at dot 349911, phase 70075
of frame 2, in the last 150 dots of VBlank 2. Its first witness is the seventh
HUD cache byte of update 3, in visible frame 3: the ROM prepared `PLAY` where
the unchanged model expects `PAUSED`. Every raw tool and simulator command
exited 0 in all three runs; the fault's Python XML records the failure and the
outer command returned 1. The positive result is therefore not vacuous on the
new frames.

### What this establishes

Established on the built image: the first world frame, the neutral frame, the
PAUSED frame and the Select-restart frame, every pixel; the one-frame display
delay for pause and restart; every publication write of six VBlanks in source
order, including the restart's map reselect and restored columns; and a
settled paused end state. Not established: pause/resume with Start, Start
restart from RETRY or WON, scrolling frames, the win route and the death/retry
route. [FRAME_PROOFS.md](FRAME_PROOFS.md) captures those on hardware.
