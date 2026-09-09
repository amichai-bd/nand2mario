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
- Run the affected existing three-frame composed Intel-model target `python-gu`,
  checking all69120 pixels, state/publication writes and normal pause/END. Its
  existing short lifecycle and actual output-mutation evidence remain historical;
  qualify reuse explicitly against unchanged harness/checker/fixture behavior.

Native short/full forecast12 seconds together; composed forecast180 seconds.
Each invocation retains the300-second total supervisor and12-second cleanup;
ordinary aggregate target300 seconds. No hardware execution is part of this fix.
Runtime acceptance is pending. #263's full reference/DUT milestone and #264's
physical release remain open with their existing criteria.
