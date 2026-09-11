# JOYP row settling

[#281](https://github.com/amichai-bd/nand2mario/issues/281) corrects software input
sampling without changing the game rules, Core, RTL or displayed-frame delay.
The pinned DMG_B reference delays a direction-to-action row transition by24
DMG dots (48 internal ticks). Immediate reads12 dots after the select write can
turn Right into A: the original ROM stored91 for requested81 and11 for01 at C019.
The retained #263 diagnostic records both actual FF00 reads and C019 writes.

Six NOPs after each row-select write add24 dots per row. ReadButtons including
CALL costs208 instead of160; the longest source-counted publication bound becomes
3968 instead of3920, including64 wake margin, below the4560-dot VBlank interval.
Initialization and the76964-dot LCD commit are unchanged. No expectation is
selected from observed pixels or CRC.

The finite acceptance map is:

- Two clean MISS builds must produce identical32768-byte ROMs. The corrected
  identity is separately frozen in the native contract; #277's original remains.
- Run the complete four-normal-frame native harness before twelve frames, with
  unchanged input requests129 at137000 and1 at207224. Require actual sampled C019
  values and every pixel against the independent game model. Retain both initial
  callbacks, normal blank, title and the fixed sequence of prepared world states.
- Replay the original native output against the same independent pixel checker;
  it must reject the first world frame. This is the real software regression
  witness, not a DUT output mutation. Existing native transport faults remain
  qualified only for unchanged boundaries.
- Run the affected existing three-frame composed Intel-model target `python-gu`
  (since [retired](MILESTONE.md#retired-targets)),
  checking all69120 pixels, state/publication writes and normal pause/END. Its
  existing short lifecycle and actual output-mutation evidence remain historical;
  qualify reuse explicitly against unchanged harness/checker/fixture behavior.

Native short/full forecast12 seconds together; composed forecast180 seconds.
Each invocation retains the300-second total supervisor and12-second cleanup;
ordinary aggregate target300 seconds. No hardware execution is part of this fix.
At41ed3d4, native short/full passed in6.542/5.480 seconds: all6/14 callback
images and sampled masks matched. The original retained native output failed
the unchanged independent pixel comparison at callback4/index17148.
The composed run passed in183.116 seconds with69120 pixels, all publications,
normal pause286976 and END. Its last publication write was3876 dots after
VBlank began, below3968. Aggregate195.137 seconds met300; the composed run
missed the120-second target but met its hard limit. No failed attempt is relabeled.
Exact commands, clean-build qualification and historical unchanged-harness
evidence reuse are retained in [PR282](https://github.com/amichai-bd/nand2mario/pull/282).
#263's full reference/DUT milestone and #264's physical release remain open
with their existing criteria.
