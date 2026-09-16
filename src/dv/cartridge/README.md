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
[`tb_mbc1`](tb_mbc1.sv) is the [MBC1 profile](../../../wiki/src/rtl/cartridge/MAS_mbc1_profile.md#verification)
fixture: [`n2m_mbc1`](../../rtl/cartridge/n2m_mbc1.sv) with the real memory
owner and CPU port, the same bus driver, and the fixture driving the ROM host
port with its own 64 KiB signature image (each bank XORs an address pattern
with a bank constant); one fixture per run, `+fixture=<name>`.
[`tb_loader_system`](tb_loader_system.sv) runs the real `n2m_v05_system` with
the real CPU executing a menu program from slot 16 and drives the UART wire at
3.125 MBaud; the joypad reaches the menu through the physical producer.

| Requirement | Independent check |
|---|---|
| Address map | Every one of the 65,536 addresses read in `LOADER_ID` after a menu swap and a bank 33 fill: ROM low half, window, `$A000`-`$A003`, `$FF` above them, the owner byte elsewhere; writes outside the two registers change nothing; both ends of each register range act; select 17 ignored; in `DIRECT_ID` the bank and select registers are absent and `$A000`-`$BFFF` reads `$FF` |
| Window fill | Banks 0, 1, 33, 34 and 63: `$FF` window reads and status `$A0` while busy, a second commit ignored, `window_ready`, `$A001`, the upper half equal to the SDRAM bank byte for byte, every fill inside 40,000 edges; one host line read served during a fill |
| Swap | Selects 0, 15 and 16 and the host return: no ROM write before `paused`, `image_valid` low during every engine write, `PROFILE` from the catalogue, epoch + 1, result `OK` and index, running again without a host `RUN`, every swap inside 80,000 edges, the ROM store equal to the image byte for byte; a host `HALT` held across a swap keeps the console paused |
| Swap with a stepping host command | `RUN_DOTS` at its maximum budget, then a select: the command completes on the engine's pause with reason `STOPPED`, the swap runs, the console stays paused until `RUN`; `STEP` at its maximum budget, then the return: `STEP_LIMIT`, the swap, paused until `RUN` |
| Swap faults | After a bank 1 fill, empty, wrong length, unknown profile, a direct-profile entry claiming 65536 bytes and a 64 KiB entry in slot 15: `INVALID_SLOT`, index recorded, no engine write, `window_ready` still set and the window intact; CRC mismatch: `window_ready` held through the catalogue check and cleared once the core is paused, then paused, `image_valid` 0, `PROFILE` 0, `CRC_MISMATCH`, the return recovers; bank, select and game exit commits before the SDRAM is initialized: `NOT_READY`, bank unchanged, nothing queued, `$A003` untouched |
| Game exit register | From a running direct-profile game: writes of `$11`, `$00`, `$01`, `$FF` and `$90` into `$6000`-`$7FFF` and of `$10` into `$0000`, `$2000`, `$5FFF` and `$A000` change nothing in the loader, the status or the ROM store; the `$10` write into `$6ABC` is busy at once, writes no ROM byte before the pause, swaps the menu image in (`PROFILE` `LOADER_ID`, epoch + 1, result `OK`, `$A003` still 0), runs without a host `RUN`; the same write in the loader profile restarts the menu; a host return followed by the exit write before the core pauses sets `key1_pending`, the loader stays busy through the first menu swap and a second one follows (epoch + 2, nothing pending) |
| KEY1 timing | Real thresholds: a 4 ms glitch changes nothing, a 0.49 s press does not return, a 0.51 s press returns once at exactly debounce plus hold edges, holding on raises nothing more, release clears the counter |
| KEY1 ordering | Shortened thresholds: a press whose threshold lands inside a swap sets `key1_pending` and the menu swap follows the game swap; a press in a host session is dropped; release and re-press returns again; a return on the engine's done edge starts the menu swap at once with nothing left pending |
| Host rules | `LOAD_BEGIN` during a fill waits for it and opens the session; during a swap it is `BAD_STATE`; `SDRAM_WRITE`/`SDRAM_READ` round trips through the arbiter while the menu fills; `LIBRARY_STATUS`, `LIBRARY_KEY1`; `WRITE_HOST(LIBRARY_CONTROL)` returns from power-up and from a running game and is `BAD_VALUE` for value 2 and `BAD_STATE` after a CRC mismatch; `LOAD_WRITE` and `LOAD_END` are `BAD_STATE` during a swap (no open session); a direct host load of a game after a swap behaves as today; KEY1 recovers from the mismatch |
| Menu | The menu selects slots 1, 2, 3 and 15 from the pressed action nibble; each game boots (`DIRECT_ID`, epoch + 1, running, dots advancing) and KEY1 returns to the menu every time; slot 4's game writes `$10` into `$6000` by itself and the menu is back running (epoch + 2, result `OK`, index 4) with no KEY1 and no host command; the 64 KiB MBC1 game in slots 11-12 boots in `MBC1_ID` (epoch + 1), selects ROM bank 2 and returns from that banked half through the exit register (epoch + 2, result `OK`, index 11) |
| MBC1 map | Both windows after reset byte for byte (bank 0, bank 1), `$FF` at `$A000`-`$BFFF` before and after RAMG and cartridge RAM writes, a WRAM round trip, the identity mapping and inert BANK1 writes in `DIRECT_ID` and `LOADER_ID`, the windows unchanged back in `MBC1_ID` |
| MBC1 bank | BANK1 0-63 through both ends of `$2000`-`$3FFF` and `$E3`, each followed by a 129-byte sample of both windows against `(BANK1 == 0 ? 1 : BANK1) & 3`; BANK2 0-3, MODE 1/0, the exit value and RAMG change nothing; every bank whole; the read on the edge after a commit sees the new bank |
| MBC1 reset | Bank 3, BANK2 and MODE set, then a core reset: bank 1 at the first read and the store retained; a second image through the host port and a reset: every byte replaced, bank 3 selectable |
| MBC1 fault | The reference names the next bank: the first switched-window sample fails with expected/actual bytes and a nonzero exit |
| MBC1 library entry and exit | `tb_loader` `exit-mbc1`: an `MBC1_ID` entry with a 32 KiB length is `INVALID_SLOT`; the select of the 64 KiB entry in slots 11-12 pauses, copies 65536 bytes within 120,000 edges (the low half checked through the CPU port, all of the store through the host port readback), publishes `MBC1_ID` with epoch + 1 and result `OK` index 11; in `MBC1_ID` the exit value at `$7FFF` returns to the menu exactly as in `DIRECT_ID` (`$A003` still 11); `$00`/`$01`/`$11` and the exit value at other addresses change nothing |

## Targets

| Target | Fixture | Expected result |
|---|---|---|
| `loader-map` | `tb_loader` `map` | `PASS loader-map checks=20 swaps=1 fills=0 engine_writes=114688` |
| `loader-window` | `tb_loader` `window` | `PASS loader-window checks=44 swaps=0 fills=5 engine_writes=81920` |
| `loader-swap` | `tb_loader` `swap` | `PASS loader-swap checks=21 swaps=5 fills=0 engine_writes=196608` |
| `loader-swap-host` | `tb_loader` `swap-host` | `PASS loader-swap-host checks=5 swaps=2 fills=0 engine_writes=65536` |
| `loader-swap-fault` | `tb_loader` `swap-fault` | `PASS loader-swap-fault checks=39 swaps=1 fills=1 engine_writes=81920` |
| `loader-exit` | `tb_loader` `exit` | `PASS loader-exit checks=20 swaps=6 fills=0 engine_writes=196608` |
| `loader-key1` | `tb_loader` `key1`, real thresholds, no VCD | `PASS loader-key1 checks=4 swaps=0 fills=0 engine_writes=32768` |
| `loader-key1-queue` | `tb_loader` `key1-queue` with `-gKEY1_DEBOUNCE_EDGES=5000 -gKEY1_HOLD_EDGES=50000` | `PASS loader-key1-queue checks=8 swaps=0 fills=0 engine_writes=163840` |
| `loader-host` | `tb_loader_system` `host` | `PASS loader-system-host checks=39 swaps=0 returns=2 commands=170` |
| `loader-menu` | `tb_loader_system` `menu` | `PASS loader-system-menu checks=27 swaps=6 returns=6 commands=24` |
| `mbc1-map` | `tb_mbc1` `map` | `PASS mbc1-map checks=7 reads=147457` |
| `mbc1-bank` | `tb_mbc1` `bank` | `PASS mbc1-bank checks=78 reads=140491` |
| `mbc1-reset` | `tb_mbc1` `reset` | `PASS mbc1-reset checks=5 reads=98562` |
| `mbc1-fault` | `tb_mbc1` `fault` | nonzero exit, `MBC1_TB_READ BANK1 sweep` |
| `loader-exit-mbc1` | `tb_loader` `exit-mbc1` | `PASS loader-exit-mbc1 checks=15 swaps=2 fills=0 engine_writes=98304` |

`tb_loader_system` also hosts the boot copier fixtures `flash-copy`,
`flash-blank` and `flash-precedence`; the
[storage test plan](../storage/README.md#boot-copier) owns them. The `host`
and `menu` fixtures run with the flash double erased, so the copier checks
entry 16 and skips to `DONE` in clock 5070; `sdram_ready` rises then instead
of at `initialized`.

The named assertions of the contract live in the RTL: `LOADER_PORT_EXCLUSIVE`
and `LOADER_FILL_HOST_PORT` in the port arbiter, `LOADER_SWAP_PAUSED`,
`LOADER_FILL_UPPER_ONLY`, `LOADER_IMAGE_INVALID_BEFORE_WRITE` and
`LOADER_VALID_IMPLIES_CRC` in the engine, `LOADER_REGS_ONLY_IN_PROFILE`,
`LOADER_EXIT_ONLY_IN_GAME_PROFILE`, `LOADER_SWAP_BOUND` and `LOADER_FILL_BOUND` in the loader,
`LOADER_KEY1_THRESHOLD` in the KEY1 detector and `LOADER_ONE_CORE_CLIENT` in
the core control owner. Every fixture runs with them armed.

Run one with `python3 tools/build.py sim test <target> --tag <tag>` on WSL, or
all of them with `python3 tools/build.py tests run --label cartridge --tag <tag>`.
The MBC1 fixtures carry the `mbc1` label instead, so the `cartridge` aggregate
stays inside the ordinary 300-second budget:
`python3 tools/build.py tests run --label mbc1 --tag <tag>`.
