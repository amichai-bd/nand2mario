# Storage test plan

## SDRAM controller

Contract: [SDRAM storage and timing](../../../wiki/src/rtl/storage/MAS_sdram.md).
DUT: [`n2m_sdram_ctrl`](../../rtl/storage/n2m_sdram_ctrl.sv) with
[`n2m_sdram_pkg`](../../rtl/storage/n2m_sdram_pkg.sv). Device:
[`n2m_sim_sdram`](../../rtl/storage/n2m_sim_sdram.sv), the original pin-level
model written against the datasheet edge counts. One testbench,
[`tb_sdram_ctrl`](tb_sdram_ctrl.sv), selects a fixture with `+fixture=<name>`.

One clock is 40 ns. Clock 0 is the first clock after reset release. The
monitor samples mid-clock, at the device's edge, so every "at clock c" check
is what the device sees during clock c. Expectations come from the contract
and the fixture's own request record captured at acceptance, never from DUT
state; the device model keeps its own storage and timing history.

| Requirement | Independent check |
|---|---|
| Initialization schedule | PRECHARGE at clock 5000, AUTO REFRESH at 5003 + 4k for k = 0..7, LOAD MODE at 5035; `initialized` first seen at 5036 and `idle` at 5038; the model counts 8 refreshes and accepts the mode value |
| No early access | Any ACTIVATE, READ or WRITE before the first `idle` is fatal; `DRAM_DQM*` equal `!initialized` on every clock |
| Address mapping | ACTIVATE carries bank `a[25:24]` and row `a[23:11]` at clock 1; READ/WRITE carries column `a[10:1]` with A10 low at clock 4 |
| Byte order | Every write beat on `DRAM_DQ` equals line bytes `2k, 2k+1` of the accepted request; reads return the line the fixture recorded at the last write of that address |
| Read beat alignment | Beat `k` is captured at the edge ending clock `5+k`, one edge after the device starts driving it (datasheet CAS latency, edge READ+CL-1+k); the model's launch edge is a parameter so the two reproduction targets show the one-word shift either way |
| Latency bounds | `response_valid` exactly 17 clocks after acceptance, `idle` low at clocks 1-17 and high at 18, acceptance within 5 clocks of a request raised in `IDLE`; `response_data` unchanged from `response_valid` until the next accepted read |
| Boundary lines | First and last line of slots 0, 15 and 16, first and last catalogue line, first and last line of a row, one line in each bank including the last line of the device, each written then read, then all read again in reverse |
| Ordering | Write then read of one line back to back returns the written line; a request raised right after a write acceptance waits for it |
| Refresh | Age measured from the observed AUTO REFRESH commands never exceeds 178 and reaches 178 three times through requests accepted at age 159; `request_ready` is low for exactly the five clocks around each refresh from `IDLE` |
| Throughput | With `request_valid` held high, at least 2048 lines are accepted in 38,100 clocks |
| Host line commands | Over the real UART endpoint: a write before initialization is `BAD_VALUE`; boundary lines are written singly and fifteen-, seven- and two-line runs in one `SDRAM_WRITE` each, all read back by `SDRAM_READ` with the bytes compared; misaligned, out-of-device, range-crossing, zero-line, partial-line and wrong-length requests are refused by status before the controller sees them, and a sixteen-line write frame is discarded as oversize |
| Library load | The host tool's own `library.load_library`/`read_catalogue` over the peer bridge: slots 0, 1 and the menu at index 16 hold the `sw build` images byte for byte and by CRC32, the catalogue at `0x88000` holds their entries, and the status readback equals the catalogue written; the model must have seen writes and reads |
| Faults | A misaligned address fails `SDRAM_LINE_ALIGNED`; a request before `initialized` fails `SDRAM_REQUEST_BEFORE_INIT`; a controller built with `REFRESH_INTERVAL=178` reaches age 196 and the model fails `SDRAM_MODEL_REFRESH_DEADLINE` |

The device model measures refresh gaps in device edges between AUTO REFRESH
commands; a gap is the controller's age plus one, so the contract's worst
age 178 is a gap of 179 against the model's 195-edge limit, and the model's
continuous check fires on the first edge past that limit.

## Targets

| Target | Fixture | Expected result |
|---|---|---|
| `sdram-init` | `init` | `PASS sdram-init initialized=5036 idle=5038 precharge=5000 mode=5035 refreshes=8` |
| `sdram-line` | `line` | `PASS sdram-line lines=16 reads=34 writes=19` |
| `sdram-refresh` | `refresh`, 40,000 clocks | `PASS sdram-refresh clocks=40000` with `max_age=178` |
| `sdram-fault-misaligned` | `fault-misaligned` | nonzero exit, `N2M_ASSERT SDRAM_LINE_ALIGNED` |
| `sdram-fault-before-init` | `fault-before-init` | nonzero exit, `N2M_ASSERT SDRAM_REQUEST_BEFORE_INIT` |
| `sdram-fault-deadline` | `refresh` with `-gREFRESH_INTERVAL=178` | nonzero exit, `SDRAM_MODEL_REFRESH_DEADLINE` |
| `sdram-fault-read-early` | `line` with `-gMODEL_READ_LAUNCH_EDGES=0` (device a beat ahead, the board's shape) | nonzero exit, `SDRAM_TB_READBACK shift=+1` |
| `sdram-fault-read-late` | `line` with `-gMODEL_READ_LAUNCH_EDGES=2` (the port's original shared assumption) | nonzero exit, `SDRAM_TB_READBACK shift=-1` |
| `uart-sdram` | [`tb_uart_sdram`](tb_uart_sdram.sv): `SDRAM_WRITE`/`SDRAM_READ` packets over the UART wire into the controller and model | `PASS UART SDRAM wire writes=44 lines_read=48 rejected=14 discarded=1` |
| `uart-sdram-fault` | same with `+payload_fault` | nonzero exit, `UART_SDRAM_PAYLOAD cmd=18 index=0` |
| `library-peer` | [`tb_library_peer`](tb_library_peer.sv) with [`library_driver.py`](library_driver.py) and [`library_peer.py`](library_peer.py): `host library load`/`status`/`return` through the live Client (pinned cocotb interpreter); the endpoint must raise exactly one `library_return` pulse | `PASS library-peer transactions=851 device_writes=6208 device_reads=6272 returns=1` and the peer's `PASS library peer live Client images=3 slots=2 verified=3 status_rows=17 return=PAUSED` |

## Flash reader

Contract: [flash library](../../../wiki/src/rtl/storage/MAS_flash_library.md#on-chip-flash-ip-boundary).
DUT: [`n2m_flash_reader`](../../rtl/storage/n2m_flash_reader.sv) with
[`n2m_flash_pkg`](../../rtl/storage/n2m_flash_pkg.sv), which under
`VERILATOR` instantiates the IP double
[`n2m_sim_onchip_flash`](../../rtl/storage/n2m_sim_onchip_flash.sv). One
testbench, [`tb_flash_reader`](tb_flash_reader.sv), selects a fixture with
`+fixture=<name>`. It writes its own word-addressed hex image
(`flash-fixture.hex` in the run directory, 0-based Avalon words), loads it
into the double and keeps its own copy of every defined word. A line accepted
at the edge ending clock `c` is accepted at edge `A = c+1`; the IP accepts the
Avalon read at edge `V = A+3` when idle, otherwise 17 edges after its previous
acceptance; every cadence check counts from `V`. The counts were simulated
from the pinned vendor data controller before the double was written.

| Requirement | Independent check |
|---|---|
| Word addressing | While the Avalon read is up, `avmm_data_addr` equals the accepted flash word less `0x00800` and `burstcount` is 4 |
| Cadence | The Avalon read is on the bus from clock `A` to `V-1` with `waitrequest` high until `V-2` and low in `V-1`; `readdatavalid` exactly in clocks `V+7..V+10` carrying words 0-3 of the fixture's copy; `line_data_valid` exactly in clock `V+11` with the four words little-endian; `line_ready` low from `A` through `V+11` and high from `V+12` |
| Contents | Every slot's first and last line (slot 5 left undefined), the whole catalogue, the line either side of the UFM0, CFM2 and CFM1 starts, one mid-slot line with a byte-order witness and the last user line, each read once alone and compared word for word |
| Erased reads | The undefined slot's first and last line, the first reserved line and the line before the last user line read `0xFFFFFFFF` in every word |
| Throughput | The 64 catalogue lines with `line_valid` held high: 63 acceptances at the first ready clock (`V+13`), one Avalon read per 17 clocks |
| Hold | `line_data` unchanged from `line_data_valid` until the next acceptance |
| Reset | `reset_sys` six clocks into a read: nothing published, `line_ready` high on release, the next reads correct; the double's read and word counts equal the testbench's |
| Faults | A misaligned word fails `FLASH_LINE_ALIGNED`; a word past `0x2E7FF` fails `FLASH_LINE_RANGE` |

| Target | Fixture | Expected result |
|---|---|---|
| `flash-reader` | `reader` | `PASS flash-reader lines=168 words=672 erased=4 back_to_back=63 image_words=392` |
| `flash-reader-fault-misaligned` | `fault-misaligned` | nonzero exit, `N2M_ASSERT FLASH_LINE_ALIGNED` |
| `flash-reader-fault-range` | `fault-range` | nonzero exit, `N2M_ASSERT FLASH_LINE_RANGE` |

## Boot copier

Contract: [flash library, boot copier](../../../wiki/src/rtl/storage/MAS_flash_library.md#boot-copier).
DUT: [`n2m_boot_copier`](../../rtl/storage/n2m_boot_copier.sv) composed in
`n2m_v05_system` with the real loader, storage arbiter, UART endpoint, core
control owner, SDRAM controller and device model. The fixtures live in
[`tb_loader_system`](../cartridge/tb_loader_system.sv) (`+fixture=<name>`),
which already drives the UART wire and builds the 17-image library the
loader fixtures use. For `flash-copy` and `flash-precedence` it writes that
library as the double's word-addressed hex (`flash-boot.hex`, 0-based Avalon
words, slot 3 omitted so erased words are copied too) and loads it through
`dut.u_copier.u_reader.u_flash.load` before reset release; `flash-blank`
leaves the double erased. Clock 0 is the first clock after reset release; a
mid-clock monitor records the first clock `initialized`, the loader's
`sdram_ready` and `flash_boot` are seen and, while armed, checks every
accepted SDRAM write against the fixture's own flash bytes.

| Requirement | Independent check |
|---|---|
| Order and contents | Every accepted write during the boot is a write, its address the previous plus 16 from 0, its data the flash line; 34,880 lines; afterwards every 16-bit SDRAM word of the library range equals the flash bytes, slot 3 `0xFF` |
| Timing | `initialized` first seen in clock 5036; `sdram_ready` never high before `flash_boot`; `COPY` (clock 5070 to the last acceptance) within 627,840-700,000 clocks; the menu running within 800,000 clocks of `initialized` |
| Menu without a host | Profile `LOADER_ID`, image valid, not paused, epoch 1 and dots advancing before the first host packet; then `STATE == RUNNING`, `LIBRARY_STATUS` with `flash_boot`, `sdram_ready`, result `OK` and `$A003 == $FF`; `HALT` pauses, `RUN` resumes; an `SDRAM_READ` of erased slot 3 returns `0xFF` |
| Erased flash | `sdram_ready` first high in clock 5070 exactly, no SDRAM write, no engine job, `flash_boot` 0, paused with no image; `LIBRARY_STATUS` `0x00FF0020`; an `SDRAM_WRITE`/`SDRAM_READ` round trip; a host load of a game paused until `RUN`, then running with the status unchanged |
| Precedence | During `COPY`: `STATE == LOADING`, `LIBRARY_STATUS` `0x00FF0000`, `LOAD_BEGIN` and `WRITE_HOST(LIBRARY_CONTROL)` `BAD_STATE`, `SDRAM_READ`/`SDRAM_WRITE` `BAD_VALUE`, `flash_boot` still 0 afterwards; after the boot the menu runs, SDRAM equals the flash, `SDRAM_READ` returns library lines, a host load of a game succeeds, `SDRAM_WRITE` overwrites a line and reads back, `LIBRARY_STATUS` `0x21FF0128`, every double word unchanged |

| Target | Fixture | Expected result |
|---|---|---|
| `flash-copy` | `flash-copy` | `PASS loader-system-flash-copy checks=13 swaps=0 returns=0 commands=8` |
| `flash-blank` | `flash-blank` | `PASS loader-system-flash-blank checks=13 swaps=0 returns=0 commands=141` |
| `flash-precedence` | `flash-precedence` | `PASS loader-system-flash-precedence checks=17 swaps=0 returns=0 commands=145` |

The copier's named assertions (`FLASH_COPY_ORDER`, `FLASH_COPY_BOUND`,
`FLASH_COPY_REQUEST_IN_COPY`, `FLASH_COPY_LINE_EXPECTED`,
`FLASH_COPY_HOLD_FREE`, `FLASH_BOOT_AFTER_COPY`) and the loader's
`LOADER_COPIER_EXCLUSIVE` are armed in every run. The three targets carry the
`flash` and `system` labels: each compiles the whole composed system and the
three together take about 180 s, which the 300 s `storage` aggregate (with
`library-peer` at 105 to 145 s) cannot absorb. Run them with
`python3 tools/build.py tests run --label flash --tag <tag>`.

Run one with `python3 tools/build.py sim test <target> --tag <tag>` on WSL, or
all of them with `python3 tools/build.py tests run --label storage --tag <tag>`.
`library-peer` carries the `python-tb` label: run it, and therefore the whole
`storage` label, on the pinned
[cocotb interpreter](../python/README.md) (`workdir/builds/python-dv-env/.venv/bin/python`).
It writes 6,208 lines in 416 fifteen-line `SDRAM_WRITE` transactions and
reads them back in 416 `SDRAM_READ`s through the bridge; it stays out of the
`uart` and `host` labels so their 300 s aggregates keep their headroom.
Verilator needs the `lz4.h` header and library the
[installation notes](../../../wiki/tools/n2m/SPEC.md#installation) name.
Each fixture finishes in a few seconds; the builder retains the command, raw
exit, seed, log and FST wave.
