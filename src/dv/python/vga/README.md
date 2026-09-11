# Source-to-VGA preservation

The [VGA MAS](../../../../wiki/src/rtl/vga/MAS_vga.md) owns geometry, scaling,
shade mapping and the frame boundary. This focused proof uses the existing
continuous Python builder and three real Intel memory banks. It changes no
product RTL and does not establish physical monitor acceptance.

## Frozen expectations

The original Python pattern uses source x/y and fixed frame number 0 or 1.
Canonical data is exactly 23040 row-major bytes, one DMG shade 0..3 per byte.
CRC-32 uses Python stdlib `zlib.crc32`, anchored by ASCII `123456789` ->
`cbf43926`. Frame 0 is `357ab3d9`; frame 1 is `388b975e`. Both contain all four
shades and differ asymmetrically across rows and columns.

The fixture drives 25 MHz system and nominal 25.2 MHz pixel clocks, the latter
rounded to 1 ps. Each reset releases on its own falling edge after 1 us.
This is a component clock boundary, not a new PLL or reset-controller proof.
Source frames start on the first system falling edge after 2 us and 20 ms.
Each has 23040 consecutive accepted rising-edge pixels, completing in 0.9216 ms.
Both clocks continue. Frame 0 is offered long before the first y=480 boundary;
frame 1 is offered long before the second. The independent schedule therefore
expects black in raster 0, frame 0 in raster 1 and frame 1 in raster 2.

The checker counts reset-relative pixel edges, including the specified two-edge
output pipeline. It checks RGB and sync at every sample through three complete
rasters. It does not read DUT coordinates, bank, display-valid or frame identity
to choose expected data. The image is x=80..559, y=24..455; every one of its
207360 output pixels per frame must match the expected shade and all RGB channels.
Only the top-left pixel of each verified 3x3 replica contributes one normalized
shade byte. Each reconstructed frame must have exactly 23040 bytes and match
both the applied-source bytes and its literal CRC. Empty or partial output fails.
Black borders, blanking and exact sync intervals are checked independently.

## Runs and evidence

`python-vga-crc` observes about 50 ms and completes by 52 ms simulated time, with a 55 ms HDL
watchdog. `python-vga-crc-corrupt` forces the actual bridge red output to zero
at fixed time 17 ms, before the first image. The unchanged checker must reject
the first image pixel at raster 1, x=80, y=24. The fault is not an expected-data
mutation. Raw simulator status is retained separately from failing Python XML
and the required nonzero builder command result.

The passive fixture captures every settled public RGB/sync/reset sample 1 ns
after the pixel rising edge. Its trace has contiguous indices and exact 1 ps
timestamps. There are 26 reset samples followed by 1260001 pipeline/raster
samples, then an explicit end marker and file close. Every 2048 records are
flushed; continuous Python reads at 2 ms intervals and applies the unchanged
raster checker to every record. Missing, duplicate, unknown, mistimed, extra
or truncated records fail. This reduces transfer callbacks, not observations.
The fault's first failing sample time is retained separately from the later
Python batch-check time.

Both targets use the existing 300-second whole-command cap, including setup and
cleanup. The per-test target is 120 seconds and selected pair aggregate target
is 300 seconds. [Delivery evidence](https://github.com/amichai-bd/nand2mario/pull/258)
records measured outcomes and failed attempts. No historical 600-second VGA run is
relabelled. Positive runs before the fault. Current-head independent review of
this schedule, fixture and budgets precedes execution.

Artifacts retain applied and reconstructed frame bytes, per-frame CRC/counts,
source/output completion times, progress, exact mismatch context, simulator
waves, XML and the normal builder input/artifact hashes. The broader legacy
ownership/reset scenarios remain separate; this proof does not close GAP-012
or #417 and does not show pixels on a physical monitor.
