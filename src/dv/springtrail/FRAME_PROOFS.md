# Scrolling, stage and retry frame proofs

[frame_proofs.py](frame_proofs.py) checks paused UART snapshots against complete
current entity/progression expectations. Host tests and source execution qualify
the fixture, not a new board result. Physical use follows the
[image binding](../../../wiki/src/dv/springtrail/SPEC.md#image-binding) and
[milestone acceptance](../../../wiki/src/dv/integration/SPEC.md#milestone-acceptance)
contracts, with explicit authorization and serialized access. No VGA or physical
control proof is implied.

<a id="startup-anchor"></a>

## Image, timing and independent expectations

The launcher builds Springtrail from current sources, verifies the complete
32,768-byte image against that build's hash before traffic, and checks the
expected wire identity separately. The run retains source/image identity,
commands, input prefixes, snapshots and result metadata. Unsupported image bytes
fail closed; there is no permanent accepted-ROM hash.

The LCD anchor `L` is derived from the built ROM and symbols by
[startup_anchor.py](startup_anchor.py) and checked against the runner's current
frozen anchor. It is not chosen from observed pixels. With `P = 70,224`, paused
checkpoints are `C(n) = L + n*P + 4,096`. The input sampled in VBlank k is computed
in the following visible interval, published in VBlank k+1 and displayed in source
frame k+2. A capture of game state `games()[k]` therefore uses C(k+2).

[entities_reference.py](entities_reference.py) supplies movement, entities,
interactions and progression; [entities_frames.py](entities_frames.py) supplies
the independent approved-art image. The literal `EXPECTED` anchors in the driver
freeze mode, Q4 position, camera, score, animation/enemy state, blocks, power,
stage, lives and countdown. Every capture compares all 23,040 pixels with its
complete expected frame; the first mismatch fails. No exclusion mask, per-pixel
candidate union or DUT-derived expected output is permitted.

## Frozen route and captures

The route retains 625 updates and ten proof captures. Its input sequence in
`SCRIPT` includes a single A tap at update 197 to clear CURL, alongside the
existing gap jumps. It touches no item or block, so the courier remains small,
score remains zero and block states remain intact. Start after WON enters stage
1; this is a stage transition, not a stage-0 reset. The later fall and retry use
stage-1 geometry and countdown. Retry spends a life. The separate endurance
lifecycle contract covers OVER and a new-game reset.

| Capture name | Game index | Required observation |
| --- | ---: | --- |
| title | 0 | Title, stage 0, two lives, countdown 400 |
| spawn | 3 | Initial play frame and progression HUD |
| first-camera | 36 | First camera movement |
| entering-column | 99 | Scrolling column publication |
| scroll-wrap | 206 | Ring wrap with current courier/entity pixels |
| camera-clamp | 441 | Stage-0 camera clamp at 608 |
| won | 473 | WON, stage 0, countdown 389 |
| won-restart | 493 | Stage 1, two lives, countdown 300 |
| retry | 604 | Stage-1 RETRY, two lives, countdown 298 |
| retry-restart | 625 | Stage 1 resumed, one life, countdown 300 |

The historical capture names remain stable. They do not assert that stage-entry
and retry images are identical: stage, lives and HUD differ. A scrolled restart
restores two ring columns per publication; the route allows at least 16
publications before comparing the complete restored world.

The short is the unchanged prefix through `entering-column`: 101 checkpoints,
four captures. The full uses 627 checkpoints and ten captures. Every paused
checkpoint uses ordinary UART controls; image, epoch, frame sequence/completion,
input and progress checks remain mandatory. End with input zero and a certain
paused endpoint.

## Optional showcase sampling

`--showcase-samples` adds only the frozen `SHOWCASE` snapshots to the full plan.
The 48 selected indices reuse eight proof captures and add 40 reads. The three
stage-1 fall samples are 574, 578 and 581, replacing the historical 594, 598 and
601 without increasing captures or changing the input route. The ten proof
indices above are unchanged.

Each sample is checked across all 23,040 pixels before storage. Records include
game index, independent state, input mask, CRC and packed bytes. Reused proof
captures cause no additional read. These samples support illustrations; they do
not add acceptance criteria or change duration/capture policy.

## Budgets and safety

Both plans retain a 300-second whole-process cap, including build, upload,
checking and cleanup. A complete short precedes a full physical run; use its
measured throughput to confirm the remaining plan fits. The worker refuses work
at cap minus 24 seconds and the supervisor terminates its own tree by cap minus
12 seconds. There is no automatic budget extension or unchanged retry.

Use verified hardware/wiring/voltage and the shared machine/session lock. The
launcher does not program the FPGA. On failure, retain the original error and
any cleanup error; HALT/input release are permitted only while transport is
certain. No further traffic follows an uncertain reply. Final state must be
PAUSED with UART input and effective input zero and a certain session.

[test_frame_proofs.py](test_frame_proofs.py) retains literal model anchors,
route/capture counts, full-frame corruption checks, image/epoch/input/sequence
refusal and completion/cleanup negatives. Actual source execution checks the
current route against game state; neither it nor a synthetic endpoint is RTL
or board execution. Physical results require exact commands, versions, source
and image identities, raw measurements and final-state evidence.

## Historical physical evidence

The following measurements belong only to image
`35aae757bde0ec9a15d6d6c84f14b45b451c341d2d4775f43ed8a9a762625192`,
whose LCD anchor was 167,840. They used the earlier route/model and do not qualify
the current entity/progression pixels or stage-aware route.

| Plan | Whole seconds | Checkpoints | Proof captures | Proof pixels | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Short | 22.3 | 101 | 4 | 92,160 | PASS on historical image |
| Full | 47.8 | 627 | 10 | 230,400 | PASS on historical image |
| Full with showcase | 108.7 | 627 | 10 | 230,400 | PASS on historical image |

The historical showcase added 40 checked frames (921,600 pixels). Earlier
measurements on `616de11b...` are also historical. Their anchors, CRCs and route
positions are not current expected values. Current host/source qualification
must remain distinct from any separately authorized new physical run.
