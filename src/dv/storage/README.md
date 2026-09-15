# SDRAM controller test plan

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
| Host line commands | Over the real UART endpoint: a write before initialization is `BAD_VALUE`; boundary lines and a fifteen-line run are written one line per `SDRAM_WRITE` and read back by `SDRAM_READ` with the bytes compared; misaligned, out-of-device, zero or sixteen-line and wrong-length requests are refused before the controller sees them |
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
| `uart-sdram` | [`tb_uart_sdram`](tb_uart_sdram.sv): `SDRAM_WRITE`/`SDRAM_READ` packets over the UART wire into the controller and model | `PASS UART SDRAM wire writes=20 lines_read=23 rejected=11` |
| `uart-sdram-fault` | same with `+payload_fault` | nonzero exit, `UART_SDRAM_PAYLOAD cmd=18 index=0` |

Run one with `python3 tools/build.py sim test <target> --tag <tag>` on WSL, or
all of them with `python3 tools/build.py tests run --label storage --tag <tag>`.
Verilator needs the `lz4.h` header and library the
[installation notes](../../../wiki/tools/n2m/SPEC.md#installation) name.
Each fixture finishes in a few seconds; the builder retains the command, raw
exit, seed, log and FST wave.
