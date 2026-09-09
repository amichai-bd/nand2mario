# Historical foundation proof

This retains the original [PR266](https://github.com/amichai-bd/nand2mario/pull/266)
definition and evidence boundary. Current `python-springtrail` targets use the
[movement proof](MOVEMENT.md), whose initialization and sprite rendering change
the frame schedule below. These historical numbers are not current target checks.

`python-springtrail` uses the actual composed system, current Intel memories,
25 MHz system clock and existing 25.2 MHz pixel-clock fixture. The existing
preload builds the immutable original image, initializes Intel ROM/presence
models, and runs the real CRC scan and normal Client adoption. It does not claim
a full serial ROM upload. Product RTL and all game expectations are unchanged
between positive and `python-springtrail-x`.

The fixed assembly schedule gives LCD enable commit43512: entry24, setup100,
tile-copy setup36 plus256*52-4, map-copy setup36 plus576*52-4, finalsetup64,
with the bus commit four dots before retirement. Initial title-state write is
dot120. Check every startup pixel (frame0, white), every title pixel (frame1,
113828..179195) and every world pixel (frame2,184052..249419), including order,
coordinates, epoch, flags and exact dot. Canonical bytes are row-major one shade
per pixel; independently specified CRC32 values are 5324bc1f and33421002.
The reference uses literal glyph masks and fixed placements, not ROM bytes,
generated maps or observed frame identity.

Normal UART INPUT128 is accepted in173512..175512. The ROM samples Start at
the following VBlank; all22 title tile clears and state1 must occur in
179400..183959, before the next visible row. No LCD reset/restart is used.
Request normal HALT at249420 and require actual pause by251420, before another
source frame. Require exactly69120 pixels, both state writes, both LCD writes,
the sole input and all22 ordered tile addresses. Full retirement records are
retained and checked for sequence/epoch/increasing dots; this issue claims
literal frame/state checkpoints, not every CPU register against a new model.

The optional wrapper capture is passive and default-off. It records every
public write/input before the system edge and settled retirement/pixel after
the edge, flushes in batches, and closes with an exact line-count trailer after
actual pause. Continuous Python consumes complete lines every50us. Exact pixel,
input and selected-write expectations reject missing, extra or reordered events;
the trailer binds the total transported line count and unknown values fail.
Other writes are retained without an independent value oracle. Retirement
checks cover sequence, epoch and increasing dots, not an exact terminal count
or every register. The fault
forces the actual source-shade output to1 after the first eligible pixel; the
unchanged next white-pixel expectation must reject it.

Before execution: host reference negatives and source/schedule peer review.
Declare positive then fault under the existing300s total/288s worker supervisor
and canonical tool lock. Forecast180–240s positive and40–60s fault is unmeasured;
120s per-test and300s aggregate are targets, not claimed results. Preserve any
timeout/failure and do not extend the cap. No FPGA fit is needed for unchanged
product RTL.
