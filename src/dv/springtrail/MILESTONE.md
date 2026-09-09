# Every-frame milestone schedule

[#263](https://github.com/amichai-bd/nand2mario/issues/263) preserves boot within600
frame intervals followed by3600 scripted intervals. Host-paused full-frame
acquisition is approved; [#283](https://github.com/amichai-bd/nand2mario/issues/283)
owns its reusable driver. This matrix is planned, not milestone acceptance.

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

`milestone.py` freezes the script: the existing original success route followed
by ordinary Start restart and another route, repeated to3600 updates. Its first
new route holds Start from the restart, preserving edge semantics. The short
complete lifecycle uses four updates129/1/1/1 and two neutral drains, eight source
frames, allowing two four-frame acquisition batches. Full route/model and native
execution remain to be measured before any full DUT matrix.

Every batch must finish within300 seconds including identity checks, run, full
readback, comparison, pause and cleanup. Measure the short lifecycle before
choosing full batch size and declaring aggregate wall time. Preserve exact ROM,
build, epoch, sequence, paused dot, input history and native ledger across batches;
no reset, replay or skipped frame may recover an incomplete batch. Image/pixel/
input/progress fault coverage and current-head review remain required. #264's
continuous physical milestone and #28/#156 remain separate.
