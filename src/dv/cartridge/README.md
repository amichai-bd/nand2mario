# Loader profile test plan

Contract: [loader profile](../../../wiki/src/rtl/cartridge/MAS_loader_profile.md).
DUT: [`n2m_loader`](../../rtl/cartridge/n2m_loader.sv) with
[`n2m_loader_engine`](../../rtl/cartridge/n2m_loader_engine.sv),
[`n2m_rom_port_arbiter`](../../rtl/cartridge/n2m_rom_port_arbiter.sv),
[`n2m_storage_arbiter`](../../rtl/cartridge/n2m_storage_arbiter.sv) and
[`n2m_loader_key1`](../../rtl/cartridge/n2m_loader_key1.sv). Both testbenches
compose the real [memory owner](../../rtl/memory/n2m_memory_stores.sv),
[core control owner](../../rtl/uart/n2m_uart_core_control.sv),
[SDRAM controller](../../rtl/storage/n2m_sdram_ctrl.sv) and
[device model](../../rtl/storage/n2m_sim_sdram.sv). The device model is
preloaded through its `preload_word` task with a library the fixture builds
itself: seventeen images, their CRC-32 values and the catalogue, with slot 3
empty, slot 5 the wrong length, slot 7 an unknown profile and slot 9 a wrong
CRC. Expectations come from the contract and that library, never from DUT state.

[`tb_loader`](tb_loader.sv) drives the memory owner's CPU port with a bus
driver in place of the CPU and models the command owner's `image_valid` and
`PROFILE` rules; one fixture per run, `+fixture=<name>`.
[`tb_loader_system`](tb_loader_system.sv) runs the real `n2m_v05_system` with
the real CPU executing a menu program from slot 16 and drives the UART wire at
3.125 MBaud; the joypad reaches the menu through the physical producer.

| Requirement | Independent check |
|---|---|
| Address map | Every one of the 65,536 addresses read in `LOADER_ID` after a menu swap and a bank 33 fill: ROM low half, window, `$A000`-`$A003`, `$FF` above them, the owner byte elsewhere; writes outside the two registers change nothing; both ends of each register range act; select 17 ignored; in `DIRECT_ID` the registers are absent and `$A000`-`$BFFF` reads `$FF` |
| Window fill | Banks 0, 1, 33, 34 and 63: `$FF` window reads and status `$A0` while busy, a second commit ignored, `window_ready`, `$A001`, the upper half equal to the SDRAM bank byte for byte, every fill inside 40,000 edges; one host line read served during a fill |
| Swap | Selects 0, 15 and 16 and the host return: no ROM write before `paused`, `image_valid` low during every engine write, `PROFILE` from the catalogue, epoch + 1, result `OK` and index, running again without a host `RUN`, every swap inside 80,000 edges, the ROM store equal to the image byte for byte; a host `HALT` held across a swap keeps the console paused |
| Swap faults | Empty, wrong length and unknown profile: `INVALID_SLOT`, index recorded, no engine write; CRC mismatch: paused, `image_valid` 0, `PROFILE` 0, `CRC_MISMATCH`, the return recovers; bank and select commits before the SDRAM is initialized: `NOT_READY`, bank unchanged |
| KEY1 timing | Real thresholds: a 4 ms glitch changes nothing, a 0.49 s press does not return, a 0.51 s press returns once at exactly debounce plus hold edges, holding on raises nothing more, release clears the counter |
| KEY1 ordering | Shortened thresholds: a press whose threshold lands inside a swap sets `key1_pending` and the menu swap follows the game swap; a press in a host session is dropped; release and re-press returns again |
| Host rules | `LOAD_BEGIN` during a fill waits for it and opens the session; during a swap it is `BAD_STATE`; `SDRAM_WRITE`/`SDRAM_READ` round trips through the arbiter while the menu fills; `LIBRARY_STATUS`, `LIBRARY_KEY1`; `WRITE_HOST(LIBRARY_CONTROL)` returns from power-up and from a running game and is `BAD_VALUE` for value 2 and `BAD_STATE` after a CRC mismatch; a direct host load of a game after a swap behaves as today; KEY1 recovers from the mismatch |
| Menu | The menu selects slots 1, 2, 3 and 15 from the pressed action nibble; each game boots (`DIRECT_ID`, epoch + 1, running, dots advancing) and KEY1 returns to the menu every time |

## Targets

| Target | Fixture | Expected result |
|---|---|---|
| `loader-map` | `tb_loader` `map` | `PASS loader-map checks=20 swaps=1 fills=0 engine_writes=114688` |
| `loader-window` | `tb_loader` `window` | `PASS loader-window checks=44 swaps=0 fills=5 engine_writes=81920` |
| `loader-swap` | `tb_loader` `swap` | `PASS loader-swap checks=21 swaps=5 fills=0 engine_writes=196608` |
| `loader-swap-fault` | `tb_loader` `swap-fault` | `PASS loader-swap-fault checks=26 swaps=1 fills=0 engine_writes=65536` |
| `loader-key1` | `tb_loader` `key1`, real thresholds, no VCD | `PASS loader-key1 checks=4 swaps=0 fills=0 engine_writes=32768` |
| `loader-key1-queue` | `tb_loader` `key1-queue` with `-gKEY1_DEBOUNCE_EDGES=5000 -gKEY1_HOLD_EDGES=50000` | `PASS loader-key1-queue checks=6 swaps=0 fills=0 engine_writes=98304` |
| `loader-host` | `tb_loader_system` `host` | `PASS loader-system-host` |
| `loader-menu` | `tb_loader_system` `menu` | `PASS loader-system-menu` |

The named assertions of the contract live in the RTL: `LOADER_PORT_EXCLUSIVE`
and `LOADER_FILL_HOST_PORT` in the port arbiter, `LOADER_SWAP_PAUSED`,
`LOADER_FILL_UPPER_ONLY`, `LOADER_IMAGE_INVALID_BEFORE_WRITE` and
`LOADER_VALID_IMPLIES_CRC` in the engine, `LOADER_REGS_ONLY_IN_PROFILE`,
`LOADER_SWAP_BOUND` and `LOADER_FILL_BOUND` in the loader,
`LOADER_KEY1_THRESHOLD` in the KEY1 detector and `LOADER_ONE_CORE_CLIENT` in
the core control owner. Every fixture runs with them armed.

Run one with `python3 tools/build.py sim test <target> --tag <tag>` on WSL, or
all of them with `python3 tools/build.py tests run --label cartridge --tag <tag>`.
