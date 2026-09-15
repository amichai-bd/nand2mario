# SDRAM storage and timing

Owner: [`src/rtl/storage`](../../../../src/rtl/storage/n2m_sdram_ctrl.sv) holds the
controller [`n2m_sdram_ctrl`](../../../../src/rtl/storage/n2m_sdram_ctrl.sv), its
package [`n2m_sdram_pkg`](../../../../src/rtl/storage/n2m_sdram_pkg.sv) and the
pin-level simulation model [`n2m_sim_sdram`](../../../../src/rtl/storage/n2m_sim_sdram.sv);
[`src/dv/storage`](../../../../src/dv/storage/README.md) holds the fixtures. The
controller is ported from the source recorded in the
[provenance index](../../../tools/provenance.md#external-inputs); the model is
original. The host reaches the controller through the
[UART endpoint's line commands](../uart/MAS_uart.md#core-and-storage-integration)
and the [`sdram-proof`](../../../../src/fpga/de10_lite/README.md) board image
fits it on the DE10-Lite pins. This page is the contract those implementations
and their tests follow.

## Scope

This page governs the DE10-Lite SDRAM: the device, its pins and clock
relationship, the controller's command timing, refresh and initialization, the
single line request interface the console uses, and the layout of the game
library inside the device. The [loader profile](../cartridge/MAS_loader_profile.md)
owns who issues line requests and what the Game Boy CPU sees. The
[charter](../../project-charter.md#game-library) owns the decision to hold a
library of our own games in SDRAM.

## Terms

| Term | Definition |
|---|---|
| Device | ISSI `IS42S16320D`, 512 Mibit: 4 banks x 8192 rows x 1024 columns x 16 bits, 64 MiB, on the DE10-Lite. |
| `clk_sys` | The 25 MHz system clock from the [clock contract](../../clocks-resets-cdc.md#clock-domains); every controller register uses it. |
| Clock | One `clk_sys` period, 40 ns. Every count on this page is in clocks unless a unit is given. |
| `DRAM_CLK` | The pin clock the device samples on. Its relationship to `clk_sys` is fixed [below](#clock-relationship-and-constraints). |
| Line | 16 consecutive bytes at a 16-byte-aligned device byte address; one 8-beat burst of 16-bit words. |
| Device byte address | 26 bits, `0x0000000` to `0x3FFFFFF`. Bit 0 selects the byte inside a 16-bit word and is always zero on the line interface. |
| Requester | The one client of the controller's line interface, the [storage arbiter](../cartridge/MAS_loader_profile.md#storage-arbiter) in the loader owner. |

## Contract

### Device and pins

The controller drives exactly the DE10-Lite SDRAM pins: `DRAM_ADDR[12:0]`,
`DRAM_BA[1:0]`, `DRAM_DQ[15:0]` (bidirectional), `DRAM_DQML`, `DRAM_DQMH`,
`DRAM_RAS_N`, `DRAM_CAS_N`, `DRAM_WE_N`, `DRAM_CS_N`, `DRAM_CKE` and `DRAM_CLK`.
Pin locations come from the Terasic DE10-Lite pin data recorded in the
[provenance index](../../../tools/provenance.md#external-inputs); the board
build lists them in its `.qsf`. The I/O standard is 3.3 V LVTTL. The current
[board bring-up](../../board-bring-up.md) does not include these pins; the
SDRAM bring-up slice adds them.

Command encoding on `{DRAM_RAS_N, DRAM_CAS_N, DRAM_WE_N}` with `DRAM_CS_N` low:

| Command | RAS, CAS, WE | Address use |
|---|---|---|
| NOP | 1 1 1 | none |
| ACTIVATE | 0 1 1 | `DRAM_BA` = bank, `DRAM_ADDR[12:0]` = row |
| READ | 1 0 1 | `DRAM_BA` = bank, `DRAM_ADDR[9:0]` = column, `DRAM_ADDR[10]` = 0 (no auto-precharge) |
| WRITE | 1 0 0 | same as READ |
| PRECHARGE | 0 1 0 | `DRAM_ADDR[10]` = 1 (all banks) |
| AUTO REFRESH | 0 0 1 | none |
| LOAD MODE | 0 0 0 | `DRAM_BA` = 0, `DRAM_ADDR[12:0]` = mode value |

`DRAM_CKE` is high whenever `reset_sys` is released and low in reset.
`DRAM_CS_N` is high in reset and low otherwise. `DRAM_DQML` and `DRAM_DQMH` are
high until initialization completes and low afterwards; no partial-word write is
issued. `DRAM_DQ` is driven only during the eight write beats and is high
impedance at every other clock.

### Operating point

| Parameter | Value | Derivation |
|---|---|---|
| Clock | 25,000,000 Hz, 40 ns | `clk_sys`; no separate SDRAM PLL output in the initial contract |
| CAS latency | 2 clocks | conservative at 25 MHz for the -7 speed grade |
| Burst length | 8 words, sequential, write burst = read burst | one line per access |
| Mode register value | `13'h023` | `A[2:0]=011` BL8, `A3=0` sequential, `A[6:4]=010` CL2, `A[8:7]=00`, `A9=0` |
| tRCD | 3 clocks, 120 ns | ACTIVATE at clock 1, READ/WRITE at clock 4; datasheet minimum 15 ns |
| tRP | 3 clocks, 120 ns | PRECHARGE at clock N, next command at N+3; datasheet minimum 15 ns |
| tRC (refresh to next command) | 4 clocks, 160 ns | datasheet minimum 60 ns |
| tWR | 2 clocks after the last write beat | datasheet minimum 2 clocks |
| tMRD | 3 clocks | LOAD MODE at clock N, first command at N+3; datasheet minimum 2 clocks |
| Power-up wait | 5000 clocks, 200 us | datasheet minimum 100 us; 200 us keeps the ported value |
| Refresh interval | request at 160 clocks, 6.4 us | see [refresh](#refresh) |
| Refresh deadline | 195 clocks, 7.8 us | 64 ms / 8192 rows = 7.8125 us = 195.3 clocks; floor |

Every wait above is what the ported state machine produces: a `WAIT` phase
loaded with `n-1` spends `n` clocks before the next command. The bring-up
slice may not shorten a wait below the datasheet minimum, and any change to a
value in this table changes the [latency bounds](#access-sequence-and-latency-bounds) and must
update them.

### Address mapping

A 26-bit device byte address `a` maps as:

| Field | Bits | Width | Range |
|---|---|---|---|
| Bank | `a[25:24]` | 2 | 0-3 |
| Row | `a[23:11]` | 13 | 0-8191 |
| Column (16-bit word) | `a[10:1]` | 10 | 0-1023 |
| Byte in word | `a[0]` | 1 | always 0 on the line interface |

A line occupies columns `a[10:4]*8` through `a[10:4]*8+7` of one row; a burst
never crosses a row because `a[3:1]` is zero at the start of every burst. Word
`k` of a line (k = 0..7) holds line byte `2k` in `DRAM_DQ[7:0]` and line byte
`2k+1` in `DRAM_DQ[15:8]`, little-endian like every other
[shared interface](../interfaces/MAS_interfaces.md). Beat `k` of a burst
carries word `k`.

### Initialization

From `reset_sys` release the controller performs, in order:

1. `POWERUP`: 5000 clocks of NOP with `DRAM_CKE` high, `DRAM_DQM*` high.
2. `PRECHARGE` all banks, then wait tRP.
3. Eight `AUTO REFRESH` commands, each followed by the tRC wait.
4. `LOAD MODE` with `13'h023`; `initialized` becomes true and the refresh
   age counter starts at 0 on the edge that registers this command; then
   wait tMRD.
5. `IDLE`; `idle` and `request_ready` become true.

`initialized` is an output. It is false in reset and never returns to false
without `reset_sys`. Core reset does not touch the controller: SDRAM contents
and initialization survive every core reset and every host load. Counting
the first clock after reset release as clock 0: POWERUP occupies clocks
0-4999, PRECHARGE is at 5000, the eight AUTO REFRESH commands at
5003 + 4k for k = 0..7, LOAD MODE at 5035, `initialized` is visible from
clock 5036 and `idle` from clock 5038 (201.5 us). A testbench checks both
clock numbers exactly and that no ACTIVATE, READ or WRITE is issued before
`idle`.

### Line request interface

One requester, ready/valid, one outstanding transaction. All signals are in
`clk_sys`.

| Signal | Direction | Meaning |
|---|---|---|
| `request_valid` | in | The requester holds a request until the edge where `request_ready` is also high; that edge accepts it. |
| `request_write` | in | 1 = write line, 0 = read line. |
| `request_address[25:0]` | in | Device byte address; bits 3:0 must be zero. |
| `request_data[127:0]` | in | Write line; byte `i` of the line in bits `8i+7:8i`. Ignored on reads. |
| `request_ready` | out | High only when `initialized`, the state machine is idle and refresh age is below 160. |
| `response_valid` | out | One clock, for reads only, when the line has been captured and the bank precharged. |
| `response_data[127:0]` | out | Read line, same byte order as `request_data`; stable from `response_valid` until the next accepted read. |
| `idle` | out | State machine in `IDLE`; ready implies idle, not the reverse. |
| `initialized` | out | See [initialization](#initialization). |

A write has no completion pulse. Acceptance is completion for ordering: a later
read of the same line, accepted after the write, returns the written data. The
controller stays not-ready through the write burst, tWR, precharge and tRP, so
no second request can overtake it.

### Access sequence and latency bounds

Clock 0 is the accepting edge. The controller then issues, from the ported
state machine:

| Clock | Read | Write |
|---|---|---|
| 1 | ACTIVATE (bank, row) | ACTIVATE |
| 2-3 | wait tRCD | wait tRCD |
| 4 | READ (column) | WRITE (column), beat 0 driven |
| 5-12 | beat `k` captured at the edge ending clock `5+k` | beats 1-7 driven at clocks 5-11, wait tWR at 12 |
| 13 | bus released by the device | wait tWR |
| 14 | PRECHARGE all | PRECHARGE all |
| 15-16 | wait tRP | wait tRP |
| 17 | `response_valid` | complete, no pulse |
| 18 | `IDLE`, `request_ready` if no refresh due | same |

Read beat `k` is driven by the device as a result of `DRAM_CLK` edge
READ + CL - 1 + `k` (the first edge after the READ edge for beat 0), valid tAC
after that edge and held tOH past edge READ + CL + `k`; the controller captures
it at the `clk_sys` edge ending clock `5+k`, 20 ns after the launching edge.
This is the datasheet's CAS-latency definition ("the DQs will start driving as
a result of the clock edge one cycle earlier, n + m - 1"), not "after edge
n + m": the ported controller and its model both assumed the latter and the
board returned every line shifted by one word (see [references](#references)).
See the [clock relationship](#clock-relationship-and-constraints) for the
margins. Bounds a testbench checks:

- Read: `response_valid` exactly 17 clocks after acceptance.
- Read or write occupancy: `request_ready` returns exactly 18 clocks after
  acceptance when no refresh is due, and at most 18 + 5 = 23 clocks otherwise.
- Acceptance latency for the single requester: at most 5 clocks from
  `request_valid` raised while the controller is in `IDLE`, because the
  only cause of not-ready in `IDLE` is one refresh, which takes 5 clocks
  (see below). A request raised during a transaction waits for that
  transaction first: writes have no completion pulse, so a request issued
  right after a write acceptance waits up to 18 + 5 clocks.
- Worst read latency, request to response: 5 + 17 = 22 clocks, 880 ns.
- Sustained throughput: one line per 18 clocks plus one refresh (5 clocks) per
  refresh interval, at least 1 line per 18.6 clocks on average: 32 KiB (2048
  lines) in at most 38,100 clocks, 1.524 ms, when the requester keeps
  `request_valid` high.

### Refresh

A refresh age counter counts clocks since the last AUTO REFRESH once
`initialized`. When the age reaches 160 in `IDLE`, `request_ready` falls and the
controller issues AUTO REFRESH at the next clock, waits tRC (3 more clocks), and
returns to `IDLE` at the fifth clock with the age reset to 0. Refresh is issued
only from `IDLE`, so a transaction accepted at age 159 returns to `IDLE` at
age 177 and the AUTO REFRESH command issues at age 178. The maximum age
while initialized is therefore 178, 17 clocks inside the 195-clock deadline;
a testbench checks 178, and the controller asserts the deadline. There is no refresh during initialization other than the eight
initial ones, and none in reset (SDRAM contents are lost across `reset_sys`
and after power-up; the [loader profile](../cartridge/MAS_loader_profile.md#boot-source)
owns re-loading them).

A refresh stalls the requester by exactly 5 clocks. It never interrupts an
accepted transaction and never reorders anything.

### Clock relationship and constraints

Initial contract: `DRAM_CLK` is the inversion of `clk_sys` driven straight to
the pin. Commands, address and write data change at a `clk_sys` rising edge;
the device samples them at its own rising edge 20 ns later. Read data launched
by the device at its rising edge is captured at the next `clk_sys` rising edge,
20 ns later. The Quartus constraints are:

```tcl
create_generated_clock -name sdram_clk -source <system PLL 25 MHz output pin> \
    -invert [get_ports {DRAM_CLK}]
set_input_delay  -clock sdram_clk -max 7.0 [get_ports {DRAM_DQ[*]}]
set_input_delay  -clock sdram_clk -min 1.5 [get_ports {DRAM_DQ[*]}]
set_output_delay -clock sdram_clk -max  2.8 [get_ports {DRAM_ADDR[*] DRAM_BA[*] DRAM_CAS_N DRAM_CKE DRAM_CS_N DRAM_DQ[*] DRAM_DQML DRAM_DQMH DRAM_RAS_N DRAM_WE_N}]
set_output_delay -clock sdram_clk -min -1.8 [get_ports {same list}]
```

The four numbers are the device's tAC (6.0 ns at CL2) plus 1 ns board margin,
tOH (2.5 ns) minus 1 ns, tIS (1.8 ns) plus 1 ns and tIH (0.8 ns) plus 1 ns,
from the datasheet revision in the [references](#references). The bring-up
slice must confirm them against that revision and record the confirmation in
its PR. The `-source` names the system PLL's 25 MHz output in the generated
[clocking wrapper](../clocking/MAS_clocking.md); `derive_pll_clocks` and
`derive_clock_uncertainty` from the [timing plan](../../clocks-resets-cdc.md#timing-constraints)
still apply. Nominal margins with this relationship: write setup about 20 ns
minus register-to-pin delay minus 2.8 ns; read setup about 20 ns minus 7.0 ns
minus pin-to-register delay; both must show nonnegative slack in the fit
reports for the nominal and 19.998 ns analyses. The controller's outputs are
registered or one level of logic from registers; the bring-up slice records the
actual register-to-pin delays.

Realized by the [`sdram-proof`](../../../../src/fpga/de10_lite/sdram.sdc) fit
with the inverted clock (Quartus Prime Lite 25.1std, `10M50DAF484C7G`): the
worst output setup slack against `sdram_clk` is 9.03 ns (slow 1200 mV 85C),
9.61 ns (slow 0C) and 13.48 ns (fast 0C), so the register-to-pin delay of the
command, address and write-data paths is at most about 8.2 ns including clock
uncertainty; the output hold slack is at least 18.7 ns; the read-data capture
paths are inside the system clock's worst setup slack of 6.30 ns; no port or
path is unconstrained, and `DRAM_CLK` itself is the generated clock's port
rather than a timed output (its `check_timing` entry is the one the builder
accepts for this image). The fitter reports one jitter warning because the
routed inverted clock does not use a dedicated PLL output pin; the builder
classifies exactly that line for this target.

Board observation (session of 2026-09-15, `sdram-proof` at the fit above):
programming and the endpoint identity passed and the one-slot memory test
returned every line shifted by one 16-bit word with the last word repeated.
The cause was the read-beat alignment above, shared by the controller and the
model, not the clock phase: writes were correct and static timing holds. The
inverted relationship therefore stands; the corrected capture is what the
retest proves.

Fallback if the fit or the board memory test fails with the inverted clock:
add a third output to the system PLL at 25 MHz with a requested phase shift
(start at -90 degrees, then tune) driving `DRAM_CLK` through a dedicated clock
output, and reference the same four I/O delays to that generated clock. The
fallback changes only the clock source and the `create_generated_clock` line;
the command sequence, the capture clock offsets in the table above and the
latency bounds are unchanged. Choosing the fallback is an implementation
decision inside this contract; it needs no owner approval but must be recorded
in the bring-up PR and in the table of this page.

`DRAM_CLK` is a fabric-driven pin clock derived from `clk_sys`, not a new
domain: every controller register is in `clk_sys`, so the
[crossing inventory](../../clocks-resets-cdc.md#crossing-and-ownership-inventory)
records it as a source-synchronous I/O relationship, not as a CDC.

### Address-space layout

| Device byte address | Size | Content |
|---|---|---|
| `0x0000000 + i * 0x8000`, i = 0..15 | 32 KiB each | Game slot `i`: one complete 32 KiB `dmg-direct-v1` image |
| `0x0080000` | 32 KiB | Slot 16: the menu image, a 32 KiB image in the loader profile |
| `0x0088000` | 1 KiB | Catalogue table: 17 entries x 32 bytes at `0x0088000 + 32 * i`, i = 0..16; bytes `0x0088220`-`0x00883FF` zero |
| `0x0088400` - `0x3FFFFFF` | rest | Reserved; the controller accepts requests here, no owner uses them |

Slot `i` byte `b` is at device address `i * 32768 + b`. Slot 16 is the menu
image so that the copy engine has one rule for every image. Catalogue entry
`i` describes slot `i`:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | `valid`: `0x01` valid image, `0x00` empty slot; any other value is invalid |
| 1 | 1 | `profile`: the [profile ID](../interfaces/MAS_interfaces.md) the image runs in; games use `DIRECT_ID`, the menu uses `LOADER_ID` |
| 2-3 | 2 | `length`, little-endian; must equal 32768 for a valid entry |
| 4-7 | 4 | `crc32`, little-endian CRC-32/ISO-HDLC of the 32768 image bytes, the same polynomial and reflection as `LOAD_BEGIN` |
| 8-23 | 16 | `title`: bytes `0x0134`-`0x0143` of the image header, copied verbatim |
| 24-31 | 8 | Reserved, zero |

The host writes the catalogue in phase 1 ([boot source](../cartridge/MAS_loader_profile.md#boot-source))
and the [boot copier](MAS_flash_library.md#boot-copier) writes it from the
flash mirror of this layout at power-up; the CPU-side hardware reads it and
never writes it. The menu reads it through the
banked window as bank 34 (`0x0088000 / 16384`). The copy engine treats a
slot as selectable only when `valid == 0x01`, `length == 32768` and `profile`
is a known ID. Every layout constant is one generated table in
`cfg/interfaces.json` once the slot loader slice adds it; this page is the
owner of the values, the generator is the owner of their encoding.

## Edge cases

In priority order:

1. `reset_sys` at any clock: `DRAM_CKE` low, `DRAM_CS_N` high, `DRAM_DQ`
   released, state machine to `POWERUP`, `initialized` false, `request_ready`
   false, no response pulse. Device contents are undefined afterwards.
2. A request with `request_address[3:0] != 0` or asserted while
   `initialized == 0`: never accepted; `SDRAM_LINE_ALIGNED` or
   `SDRAM_REQUEST_BEFORE_INIT` fails in simulation.
3. Refresh due at the same edge as `request_valid` in `IDLE`: refresh wins,
   the request waits 5 clocks. Age reaching 160 during a transaction: the
   transaction completes first, then the refresh.
4. `request_valid` dropped before `request_ready`: nothing happens; a requester
   may withdraw only before acceptance.
5. `request_write` or `request_address` changing while `request_valid` is high
   and not yet accepted: forbidden; assertion.
6. Read and write to the same line back to back: the write's not-ready period
   orders them; the read returns the written line.

## Verification

Simulation runs under Verilator on WSL with the original pin-level device model
[`n2m_sim_sdram`](../../../../src/rtl/storage/n2m_sim_sdram.sv), written against
the datasheet in the [references](#references), not against the controller's
constants. It lives beside the controller, like the memory owner's simulation
double, so the Questa compile gate compiles it; no FPGA target lists it. The
model:

- stores 16-bit words in a sparse map keyed by `{bank, row, column}` and
  returns seeded random data for words never written unless a fixture opts in
  to a defined fill;
- samples every command on `DRAM_CLK` rising edges and fails with a named
  fatal on: any ACTIVATE/READ/WRITE before the 200 us wait and the full
  initialization sequence; a mode value other than `13'h023`; READ or WRITE to
  a bank whose row is not open, or to a different row than the open one;
  ACTIVATE to an open bank; PRECHARGE earlier than tRAS (37 ns, checked as 2 clocks)
  after ACTIVATE or earlier than tWR after the last write beat; a command
  earlier than tRCD after ACTIVATE, tRP after PRECHARGE, tRC after AUTO
  REFRESH or tMRD after LOAD MODE; more than 195 `DRAM_CLK` edges between
  refreshes once initialized; a write beat with `DRAM_DQ` unknown or a
  `DRAM_DQM*` high; the controller driving `DRAM_DQ` while the model drives it;
- drives beat `k` tAC after device edge READ + CL - 1 + `k` for exactly 8
  beats (a `READ_LAUNCH_EDGES` parameter, default CL - 1, lets a fixture move
  that edge to reproduce a misaligned controller) and releases
  `DRAM_DQ` afterwards;
- counts refreshes, reads and writes for the fixture.

Required fixtures, each within the [wall budget](../../../tools/n2m/SPEC.md#test-wall-budget)
and implemented by [`tb_sdram_ctrl`](../../../../src/dv/storage/tb_sdram_ctrl.sv)
under the `storage` label ([test plan](../../../../src/dv/storage/README.md)):

| Fixture | Checks |
|---|---|
| `sdram-init` | `initialized` exactly at clock 5036 and `idle` exactly at clock 5038 after reset release; command order and waits above; DQM behavior; model counts 8 refreshes |
| `sdram-line` | Write then read a boundary set of lines (first and last line of slots 0, 15 and 16, both catalogue lines, the first and last line of a row, one line in each bank); exact 17/18/22-clock bounds; byte order; `response_data` stable until the next read |
| `sdram-refresh` | 40,000 clocks of back-to-back requests; age never exceeds 178; every refresh costs exactly 5 clocks; the throughput bound above holds |
| `sdram-fault` | Deliberate misaligned request, request before `initialized`, and a mutated refresh deadline of 196 each fail with the named diagnostic; three registry targets (`sdram-fault-misaligned`, `sdram-fault-before-init`, `sdram-fault-deadline`) because each fault ends its run, the last through the controller's `REFRESH_INTERVAL` parameter set to 178 |
| `sdram-fault-read-early`, `sdram-fault-read-late` | The `line` fixture against a model launching read data one edge early (`MODEL_READ_LAUNCH_EDGES=0`, the board's relative misalignment) or one edge late (`=2`, the assumption the port arrived with); each fails `SDRAM_TB_READBACK` naming the one-word shift (`+1`, `-1`) |
| `uart-sdram` | The host line commands over the real UART wire into the controller and model: `BAD_VALUE` before `initialized`, boundary lines and a fifteen-line run written and read back byte for byte, misaligned, out-of-device, zero or sixteen-line and wrong-length refusals; `uart-sdram-fault` corrupts one expected byte |

Assertions the controller carries (names are the contract; a testbench may
reference them):

| Assertion | Rule |
|---|---|
| `SDRAM_LINE_ALIGNED` | acceptance implies `request_address[3:0] == 0` |
| `SDRAM_REQUEST_BEFORE_INIT` | `request_valid` implies `initialized` |
| `SDRAM_REQUEST_STABLE` | `request_valid` without `request_ready`, followed by `request_valid` still high at the next clock, implies write flag, address and data are unchanged at that clock; withdrawal is allowed |
| `SDRAM_REFRESH_DEADLINE` | `initialized` implies `refresh_age <= 195` |
| `SDRAM_REFRESH_IDLE_ONLY` | AUTO REFRESH command implies the previous phase was `IDLE` or initialization |
| `SDRAM_READ_LATENCY` | acceptance of a read implies `response_valid` exactly 17 clocks later |
| `SDRAM_READY_RETURNS` | acceptance implies `idle` exactly 18 clocks later |
| `SDRAM_DQ_EXCLUSIVE` | the controller drives `DRAM_DQ` only during write phases |
| `SDRAM_NO_ROW_CROSS` | ACTIVATE row equals `request_address[23:11]` and READ/WRITE column equals `request_address[10:1]` with bits 3:1 zero |
| `SDRAM_KNOWN_PAYLOAD` | accepted payload has no unknown bits (Questa compile gate only; Verilator has no X) |

Questa compiles the controller and model under the compile-only gate the
[charter workflow](../../project-charter.md#game-library) requires; the fit
retains PLL, pin, I/O timing and both-frequency slack reports as in the
[required verification](../../clocks-resets-cdc.md#required-verification).
A board memory test, driven over UART through the host line commands in the
[loader profile](../cartridge/MAS_loader_profile.md#host-interaction) by
[`host sdram-test`](../../../tools/n2m/host/SPEC.md#commands), writes a seeded
address-dependent line pattern over a range (one slot by default, the whole
device with `--full`) or over the boundary set above (`--boundary`) and reads
it back with every mismatch listed by address; it is authorized per session and
does not replace the simulation bounds.
Simulation results, including the reproduction fixtures above, are
preliminary evidence only: the storage contract counts as met on the board
only when the corrected volatile bitstream has run on the DE10-Lite and the
one-slot plus boundary-line UART tests have passed, with the fit,
programming, host-status and test records retained and linked.

## References

- ISSI `IS42S16320D` datasheet Rev. 00B, 2011-06-09, pages 19-20 (AC
  characteristics) and the command truth table, distributed as
  `Datasheet/SDRAM/IS42S16320D.pdf` in the Terasic DE10-Lite System CD v2.2.0;
  see the [provenance index](../../../tools/provenance.md#external-inputs).
- ISSI combined `IS42/45S86400D/16320D/32160D` datasheet Rev. B, 2015-05-12:
  page 28 defines the CAS latency ("the DQs will start driving as a result of
  the clock edge one cycle earlier (n + m - 1) ... valid by clock edge
  n + m"). The ported controller and the device model agreed on the other
  reading until the board returned shifted lines; a model that shares the
  controller's assumption is not evidence for it, which is why the model's
  launch edge is now written from this sentence and the reproduction fixtures
  exist. Page 19 is the revision the bring-up slice confirmed the four I/O
  numbers against: for the -7 grade it lists tAC 5.4 ns at CL2, tOH 2.7 ns, tDS/tCMS
  1.5 ns and tDH/tCMH 0.8 ns, so the constraints above (derived from the
  2011 revision and equal to this revision's -5 column) stay on the
  conservative side; tRCD/tRP 15 ns, tRC 60 ns, tRAS 37 ns, tDPL 14 ns and
  tMRD 14 ns are unchanged.
- Terasic DE10-Lite pin data (System CD v2.2.0), the source of the SDRAM pin
  assignments.
- Ported controller and device model: `bui-bui` `src/rtl/mafia/sdram/` and
  `src/dv/mafia/mafia_sdram_device_model.sv`, MIT, adapted from FPGA-MAFIA
  revision `0939fe7586f472942f64003c26048e1bf37e5c85`; recorded in
  [provenance](../../../tools/provenance.md#external-inputs).
- [Clock, reset and CDC contract](../../clocks-resets-cdc.md), [clocking owner](../clocking/MAS_clocking.md),
  [loader profile](../cartridge/MAS_loader_profile.md), [memory owner](../memory/MAS_memory.md).
