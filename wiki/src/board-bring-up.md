# DE10-Lite board bring-up

This records the proof that the connected DE10-Lite path is safe and
operational, using the existing `v05-board`
[target](../../src/fpga/de10_lite/targets.json) and UART host tooling. It
closes the UART-provable part of
[GAP-005](../preflight-gaps.md#gap-005-board-wiring-and-safe-bring-up): wiring,
voltage, ground, pins, reset polarity, checked programming, heartbeat, frame
content, ping, build ID and CRC rejection.

No agent has a monitor attached to this board. Every result below is a
UART-readable proxy or a static Quartus report. Visual confirmation of the VGA
picture on an actual monitor is not claimed here; it remains the board owner's
open item, tracked with the rest of connected-board display acceptance under
[GAP-006](../preflight-gaps.md#gap-006-clock-reset-and-cdc-plan).

## Wiring, voltage, ground, and reset polarity

The board is an Intel/Terasic DE10-Lite with a `10M50DAF484C7G` MAX 10 device,
driven over its onboard USB-Blaster for JTAG and an external 3.3 V UART
adapter wired to the Arduino header. All signals are single-ended 3.3 V LVTTL;
no level shifting is used or required.

| Function | Connector | FPGA pin | Direction |
|---|---|---|---|
| UART receive (adapter TX to FPGA RX) | Arduino D0 | `PIN_AB5` | input |
| UART transmit (FPGA TX to adapter RX) | Arduino D1 | `PIN_AB6` | output |
| Board reset, active low | KEY0 | `PIN_B8`, 3.3 V Schmitt trigger | input |
| VGA red[3:0] | VGA connector | `PIN_AA1`, `PIN_V1`, `PIN_Y2`, `PIN_Y1` | output |
| VGA green[3:0] | VGA connector | `PIN_W1`, `PIN_T2`, `PIN_R2`, `PIN_R1` | output |
| VGA blue[3:0] | VGA connector | `PIN_P1`, `PIN_T1`, `PIN_P4`, `PIN_N2` | output |
| VGA hsync, active low | VGA connector | `PIN_N3` | output |
| VGA vsync, active low | VGA connector | `PIN_N1` | output |
| Reference clock | onboard 50 MHz oscillator | `PIN_P11` | input |

These pins come from the committed `v05-board` [target definition](../../src/fpga/de10_lite/targets.json)
and match the [DE10-Lite user manual](https://www.terasic.com.tw/cgi-bin/page/archive.pl?Language=English&CategoryNo=205&No=1021)
pinout for KEY0, the VGA connector, and the Arduino header. The UART adapter's
ground is tied to the DE10-Lite ground pin on the Arduino header; both boards
share a common ground through that connection and through USB to the same
host. `board_reset_n` uses the DE10-Lite's onboard Schmitt-trigger KEY0 input,
so no external reset wiring is used and no reset polarity inversion exists
outside the FPGA fabric. UART RX/TX direction was confirmed by the adapter's
own TX/RX labeling and by a successful `PING` round trip (below); a swapped
pair produces silence, not a false pass, because `PING` requires a matching
response sequence and CRC.

Record measured supply, ground continuity, and connector identity in each
physical run's evidence, per the [electrical boundary](fpga-controls.md#electrical-boundary)
precedent for the separate ADC/button header. No unidentified module, 5 V
digital output, or unknown terminal order is connected to this board.

## Programming

Programming always checks the attached JTAG identity before writing a
bitstream. `n2m fpga program` requires `jtagconfig` to report exactly one
selected USB-Blaster chain whose device name matches `10M50DA`, the same check
`doctor.py` already performs read-only in its `environment` profile.
Programming refuses to run if zero or more than one matching chain is present,
and refuses a `.sof` path that is missing, a symlink, or outside the
repository. It does not inspect the bitstream's own target device: a `.sof`
built for a different device is refused by `quartus_pgm` itself, which checks
the file against the device it finds on the chain. `quartus_pgm` is invoked in
JTAG mode with `-o "p;<sof>"`; a nonzero exit, or output without its explicit
success line, fails the run before any host traffic is attempted.

## Heartbeat and VGA test-card proxies

[`board_bringup.py`](../../src/dv/springtrail/board_bringup.py) proves both.
Neither result is verified by eye; both come from the already-loaded
`v05-board` system over UART, under the exclusive
[machine lock](../../tools/ci/storage.py) and durable session
[`endurance.py`](../../src/dv/springtrail/endurance.py) already uses for the
continuous milestone:

- **Heartbeat.** After a fresh `LOAD`, the endpoint sits at dot 0. `RUN_DOTS`
  is issued for bounded, exact counts until the target dot is reached; the
  returned dot count must be greater than zero. This proves the reference
  clock, PLLs, reset release, and CPU/timebase datapath are alive end to end,
  read back over the same UART path used for every other check.
- **VGA test card.** The current build's original springtrail ROM (built
  fresh from source by `build_rom`, not a frozen historical fixture) is
  loaded and run to its title frame. The frame is read back with
  `SNAPSHOT`/`READ_FRAME` and compared, pixel for pixel, against
  `endurance.expected('title')` — the same independent reference the
  continuous milestone (#264) already checks. This is the same deterministic
  image the frame bridge scans out to the physical VGA pins; its CRC and full
  pixel match are the test-card proxy in place of an observed picture. The
  precise per-scanline freshness window `endurance.py` also checks depends on
  a hand-maintained LCD-commit constant this run does not attempt to
  recalibrate; the full pixel match is the actual proof here, and a stale
  constant or wrong captured frame fails it rather than passing silently.
- **Pin-level timing.** The `v05-board` Quartus build already produces
  `design.sta.summary`/`design.sta.rpt` timing closure for the VGA, UART, and
  clock pins listed above, with `output_delay` constraints recorded in
  `targets.json`. That closed-timing report is the pin-level timing evidence;
  it is a static analysis result, not an oscilloscope measurement.

## UART ping, build ID, and CRC rejection

Register `BUILD_ID_0` holds `BUILD_ID[31:0]`, the *least*-significant word of
the 128-bit `N2M_V05_BUILD_ID` Verilog literal
([`n2m_uart_host_registers.sv`](../../src/rtl/uart/n2m_uart_host_registers.sv)).
`identify()` concatenates `BUILD_ID_0..3` little-endian in register order, so
the wire hex string is the full byte-reversal of the `fpga build` record's
`build_id` field (itself the literal's leading 32 hex characters). Compare
against a value obtained from `identify()` — this run's or a previously
recorded one — not against the build record's `build_id` string directly.

`Client.identify()` sends `PING`, reads the ABI register, and reads the four
`BUILD_ID` words, failing if any check disagrees or the identity is all zero.
[`crc_proof.py`](../../tools/n2m/host/crc_proof.py) sends one `PING` with a
flipped CRC byte and requires silence (no response), then proves a following
well-formed `PING` still succeeds and that all public state and counters are
unchanged. Both run under the same session and exclusive lock as the heartbeat
and test-card checks.

## Run record

Each physical run's evidence records the exact bitstream commit and whether
board state changed:

- The commit is the `commit` field of the `fpga build` record that produced the
  programmed `.sof`, alongside that record's `fingerprint`/`build_id`.
- Board state changed exactly when `n2m fpga program` ran. Programming
  reconfigures the device unconditionally — nothing reads the board's current
  identity first, because `program()` never opens the UART — so a run that
  programs has changed board state, and a run that reuses an already-configured
  board has not. The programmer's retained `program.log` is the record of which
  happened.
- After programming, `board_bringup.py` calls `identify()` and fails unless the
  running wire `build_id` equals the expected one. That is a post-programming
  confirmation that the intended build is live, not a decision about whether to
  program.

The evidence closing this gap: `jtagconfig` reported exactly one USB-Blaster
chain with device `10M50DA(.|ES)/10M50DC` before programming;
`n2m fpga build v05-board` built commit `7338daed81370ce7794eae4eae8c292c23ca5610`
(wire build ID `ba1d1956ca07a2c38aae5c801e217f98`, the byte-reversal of the
build record's `987f211e805cae8ac3a207ca56191dba`); `quartus_pgm` reported
"Quartus Prime Programmer was successful. 0 errors, 0 warnings", changing the
board's prior configuration; the board was then programmed fresh a second time
so the physical run's epoch started clean. `board_bringup.py` then passed in
full over COM3: heartbeat dot 283932, test-card pixel match on all 23040
pixels (CRC32 `9b162de2`), UART ping/ABI/build-ID identity confirmed, and CRC
rejection silent then recovered with unchanged public state and counters. Total
wall time was 15.3 s, inside the 120 s budget. See the PR for the retained
run evidence.

## Open items

Visual confirmation that the VGA test card displays correctly on an actual
monitor is deferred to the board owner. No agent operating this board has a
monitor attached, so this page and its retained evidence prove the generator,
UART proxies, and timing closure only; they do not claim the picture was seen.
