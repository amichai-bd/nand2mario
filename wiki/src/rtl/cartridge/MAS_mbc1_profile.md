# MBC1 profile

Owner: [`src/rtl/cartridge`](../../../../src/rtl/cartridge/n2m_mbc1.sv).
[`n2m_mbc1`](../../../../src/rtl/cartridge/n2m_mbc1.sv) holds the registers
and translates store offsets; it observes the same resolved CPU ROM write
commits as the [loader profile](MAS_loader_profile.md), which also serves the
game exit register for this profile. [`n2m_v05_system`](../../../../src/rtl/system/n2m_v05_system.sv)
places it between the CPU port and the [memory owner](../memory/MAS_memory.md)'s
stores; [`src/dv/cartridge`](../../../../src/dv/cartridge/README.md) holds the
fixtures. The generated [interface table](../interfaces/MAS_interfaces.md) owns
`PROFILE_MBC1_ID`, `PROFILE_STORE_BYTES` and every `MBC1_*` constant this page
names. The [software toolchain](../../../tools/sw/SPEC.md#implemented-linker-and-packager)
builds `dmg-mbc1-v1` images; the [host tool](../../../tools/n2m/host/SPEC.md#commands)
loads them as `MBC1_ID` sessions, from a package or from a pinned external image.

## Scope

`dmg-mbc1-v1` is a bounded original profile for 64 KiB games without cartridge
RAM: cartridge type `$01`, ROM size code `$01`, RAM size code `$00`. It fixes
what the CPU sees at `$0000`-`$7FFF` and `$A000`-`$BFFF`, the four MBC1 write
registers at this capacity, reset behavior, the host load and readback rules
and the store that holds the image. It is not a general MBC1: larger ROM sizes,
cartridge RAM, battery saves and multicart wiring are outside it, and no
commercial cartridge compatibility is claimed. The 32 KiB `dmg-direct-v1` and
loader profiles keep their behavior byte for byte.

## Terms

| Term | Definition |
|---|---|
| Profile | The `PROFILE` host register value: `DIRECT_ID` (1) mapperless, `LOADER_ID` (2) the menu, `MBC1_ID` (3) this profile. |
| Image | Exactly `MBC1_ROM_BYTES` (65536) bytes: `MBC1_BANKS` (4) banks of `PROFILE_BANK_BYTES` (16384). Image offset `o` is bank `o / 16384`, bank offset `o % 16384`. |
| ROM store | The memory owner's single ROM store, `PROFILE_STORE_BYTES` (65536) bytes; store offset `o` holds image offset `o` in every profile. A 32 KiB image occupies offsets `$0000`-`$7FFF`; offsets above its length are unspecified and never reached by the CPU in that profile. |
| Fixed window, switched window | CPU addresses `$0000`-`$3FFF` and `$4000`-`$7FFF`. |
| BANK1, BANK2, MODE, RAMG | The four MBC1 registers, written through the alias ranges `MBC1_*_START`-`MBC1_*_END`, which tile `$0000`-`$7FFF` in that order: RAMG `$0000`-`$1FFF`, BANK1 `$2000`-`$3FFF`, BANK2 `$4000`-`$5FFF`, MODE `$6000`-`$7FFF`. |
| Effective bank | The bank the switched window shows: `(BANK1 == 0 ? 1 : BANK1) & MBC1_BANK_MASK`. |
| Commit | A resolved CPU write in the ROM range, as the memory owner presents it to this owner; one per edge at most. |

## Contract

### Address map in the MBC1 profile

| CPU address | Read | Write |
|---|---|---|
| `$0000`-`$3FFF` | Store offset `a[13:0]`: bank 0, always | RAMG or BANK1 register commit per the alias ranges |
| `$4000`-`$7FFF` | Store offset `{effective_bank[1:0], a[13:0]}` | BANK2 or MODE register commit per the alias ranges |
| `$A000`-`$BFFF` | `$FF`, as the [direct profile](../memory/MAS_memory.md#absent-cartridge-ram-in-the-direct-profile) | Ignored; RAMG never enables anything |
| Other | Unchanged direct-profile rules | Unchanged |

The read path is a store address translation and nothing else: no cycle is
stretched, no byte is registered on the CPU read path, and no CPU write ever
reaches the store. In `DIRECT_ID` and `LOADER_ID` the translation is the
identity `a[14:0]`; the MBC1 registers are absent and ROM writes keep their
existing meaning there. Bank 0 at `$0000`-`$3FFF` does not depend on BANK2 or
MODE: with four banks the register bits that MBC1 mode 1 would route to the
fixed window (bits 19:18 of a larger cartridge address) do not exist.

### Registers

| Register | Alias range | Width | Write | Reset | Effect |
|---|---|---|---|---|---|
| RAMG | `MBC1_RAMG_START`-`MBC1_RAMG_END` | none | Accepted, ignored | none | None; there is no cartridge RAM to enable |
| BANK1 | `MBC1_BANK1_START`-`MBC1_BANK1_END` | `MBC1_BANK1_BITS` (5) | `BANK1 = data[4:0]` | `0` | Effective bank `(BANK1 == 0 ? 1 : BANK1) & MBC1_BANK_MASK`, on the next CPU read |
| BANK2 | `MBC1_BANK2_START`-`MBC1_BANK2_END` | `MBC1_BANK2_BITS` (2) | `BANK2 = data[1:0]` | `0` | None on a 64 KiB image; retained so the state is observable in tests |
| MODE | `MBC1_MODE_START`-`MBC1_MODE_END` | 1 | `MODE = data[0]` | `0` | None on a 64 KiB image; retained for the same reason |

The zero test uses the whole five-bit BANK1 value before masking: `$00` and
`$20` both select bank 1, `$04` selects bank 0 (`4 & 3`), `$21` selects bank 1,
`$07` selects bank 3. Every address in an alias range is equivalent; the data
bits above each register width are ignored. Writes in an alias range never load
bytes and never change another register. One commit changes at most one register.

The [game exit register](MAS_loader_profile.md#game-exit-register) is honored
in this profile exactly as in `DIRECT_ID`: a commit of `LIBRARY_GAME_EXIT_VALUE`
(`$10`) anywhere in `MBC1_MODE_START`-`MBC1_MODE_END` is a menu return request
with the `key1_return` rules, decoded by the same select decode. That commit
also updates MODE with `data[0]` (`0` for `$10`), which has no effect here. A
game that toggles MODE with `$00`/`$01` never triggers the return; the value
must be exactly `$10`.

### Reset and image validity

`reset_sys` and every core reset (host `RESET`, `LOAD_END`, a loader swap into
this profile) set BANK1, BANK2 and MODE to zero; the switched window shows
`MBC1_RESET_BANK` (1) at the first instruction. The ROM store is retained
across `RESET` as in the direct profile. `image_valid`, `PROFILE`, epoch and
pause rules are the [shared interface](../interfaces/MAS_interfaces.md#direct-entry-and-reset)
rules with `PROFILE == MBC1_ID`; direct-entry CPU state, RAM fills and
peripheral initialization are identical to `dmg-direct-v1`.

### Host load and readback

`LOAD_BEGIN` with `profile == MBC1_ID` requires `size == MBC1_ROM_BYTES`;
`DIRECT_ID` and `LOADER_ID` keep `size == PROFILE_ROM_BYTES`. A size that does
not match the named profile fails as it does today, before any state changes.
`LOAD_WRITE` offsets and `READ_ROM` ranges are bounded by the length of the
profile named in the current load session, so a 64 KiB image is written and
read back in full and a 32 KiB session still refuses offsets at `$8000` and
above. The presence bitmap covers every byte of the session's image; `LOAD_END`
requires all of them and the whole-image CRC-32 over exactly that length. The
[host package reader](../../../tools/n2m/host/SPEC.md) takes the profile and
length from the built image's manifest or the pinned external record; it never
pads or truncates.

### Store and loader interplay

The store grows to `PROFILE_STORE_BYTES`; port A (host and copy engine writes,
host readback) and port B (CPU and DMA reads) keep their roles from the
[memory owner](../memory/MAS_memory.md#stores-and-ownership) with 16-bit store
offsets. The loader engine and the UART load owner write the offset they are
given; the 32 KiB swap and window fill paths touch offsets `$0000`-`$7FFF`
only, and a 64 KiB swap writes the whole store.

Width dependency: `PROFILE_STORE_BYTES` sizes the store and its host range in
[`n2m_memory_stores`](../../../../src/rtl/memory/n2m_memory_stores.sv) and the
load address and presence bitmap in [`n2m_uart_load`](../../../../src/rtl/uart/n2m_uart_load.sv)
and [`n2m_uart_presence_store`](../../../../src/rtl/uart/n2m_uart_presence_store.sv);
the ROM host port, the UART load owner's address, the
[`n2m_loader_engine`](../../../../src/rtl/cartridge/n2m_loader_engine.sv)
write offset and the [`n2m_rom_port_arbiter`](../../../../src/rtl/cartridge/n2m_rom_port_arbiter.sv)
are 16 bits wide. The CPU-side offset stays 15 bits in
[`n2m_memory_decode`](../../../../src/rtl/memory/n2m_memory_decode.sv). The session checks in
[`n2m_uart_validate`](../../../../src/rtl/uart/n2m_uart_validate.sv) and the
sweeps in the load owner use the loaded profile's image length, supplied by the
[command owner](../uart/MAS_uart.md); `PROFILE_ROM_BYTES` keeps its 32 KiB
meaning for the direct and loader profiles.

The [SDRAM layout](../storage/MAS_sdram.md#address-space-layout) and the
[flash library](../storage/MAS_flash_library.md#flash-layout) carry a 64 KiB
image in two adjacent slots under one catalogue entry whose 24-bit length is
`MBC1_ROM_BYTES`; the [copy engine](MAS_loader_profile.md#select-register)
copies it into the whole store and publishes `MBC1_ID`, so an MBC1 game
starts from the menu like a direct one. The host load session is the other
way into the store.

### Storage and fit

The 64 KiB store and its 65,536-bit presence bitmap are on-chip M9K memory,
through the [shared Intel boundary](../common/MAS_memory_primitives.md). The
composed board image must fit and meet timing with them; if it does not, the
result is reported with the exact resource numbers and this profile pauses,
per the owner decision recorded in #307. External SDRAM is not a fallback for
the switched window: a bank change takes effect on the next CPU read, which a
copy could not meet.

## Edge cases

In priority order:

1. `reset_sys`: registers zero, `PROFILE` 0, no valid image; the store is
   unspecified until a load or swap.
2. A BANK1 commit and a CPU read of the switched window on consecutive edges:
   the read after the commit edge sees the new bank. There is no fill and no
   `$FF` window.
3. BANK1 data with bit 5 or above set: only `data[4:0]` is stored, so `$20`
   behaves as `$00` (bank 1) and `$E3` as `$03` (bank 3).
4. A write to `$A000`-`$BFFF` after any RAMG value: ignored; reads stay `$FF`.
5. Host `LOAD_BEGIN` with `profile == MBC1_ID` and `size == 32768`, or
   `profile == DIRECT_ID` and `size == 65536`: refused before any state change,
   with the existing size-mismatch status.
6. `READ_ROM` at offsets `$8000`-`$FFFF` during a `DIRECT_ID` session: refused
   as today; during an `MBC1_ID` session: served.
7. A loader swap into a catalogue entry naming `MBC1_ID`: refused as an invalid
   slot until #712 defines a 64 KiB entry; the 32 KiB rules stand.

## Verification

Simulation runs under Verilator on WSL. [`tb_mbc1`](../../../../src/dv/cartridge/tb_mbc1.sv)
composes the real memory owner and CPU port with a bus driver in place of the
CPU and drives the ROM host port itself; expectations come from this page and
an original image the fixture builds: every bank XORs an address-dependent
pattern with its own constant, so that a wrong bank is a byte mismatch, never a
silent pass. The load and exit cases run in the owning fixtures of the
[UART load owner](../../../../src/dv/uart/tb_uart_load.sv), the
[validator](../../../../src/dv/uart/tb_uart_validation.sv) and the
[loader](../../../../src/dv/cartridge/tb_loader.sv). Composed execution uses the existing Intel
preload path with an original program that switches banks and reports what it
read. Mooneye `emulator-only/mbc1/rom_512kb` is the pinned external executable
specification for this capacity (type `$01`, four banks, no RAM), run by the
[Mooneye adapter](../../../../src/dv/mooneye/README.md) as `mooneye-rom-512kb`;
its expected table encodes the same zero-translation and masking rules.

| Fixture | Independent check |
|---|---|
| `mbc1-map` | `tb_mbc1` `map`: both windows after reset (bank 0, bank 1) byte for byte, `$A000`-`$BFFF` reads `$FF` before and after RAMG and cartridge RAM writes, a WRAM round trip; in `DIRECT_ID` and `LOADER_ID` the same image bytes at `$0000`-`$7FFF` read as the identity after BANK1 writes; back in `MBC1_ID` the windows are unchanged |
| `mbc1-bank` | `tb_mbc1` `bank`: BANK1 values 0-63 through both ends of the alias range and `$E3`, each followed by a 129-byte sample of both windows against the contract's effective bank; BANK2 0-3, MODE 1/0, the exit value and RAMG `$0A`/`$00` change nothing; every bank whole; the read on the edge after a commit sees the new bank |
| `mbc1-reset` | `tb_mbc1` `reset`: bank 3, BANK2 and MODE set, then a core reset: bank 1 at the first read and the store retained; a second image loaded through the host port and a reset: every byte replaced, bank 3 selectable |
| `mbc1-fault` | `tb_mbc1` `fault`: the reference names the next bank, so the first switched-window sample fails with expected/actual bytes and a nonzero exit |
| `uart-load-mbc1` | `tb_uart_load` with a 65,536-byte session: clear sweep, writes over the whole image, one byte missing above 32 KiB caught by the end sweep and repaired, CRC, full readback; the unchanged `uart-load` run keeps the 32,768-byte session ending at `$7FFF` |
| `uart-validation` | `LOAD_BEGIN` accepts `MBC1_ID` with 65,536 and refuses it with 32,768; `DIRECT_ID` with 65,536 refused; `LOAD_WRITE`/`READ_ROM` ranges up to 65,536 accepted in an `MBC1_ID` session and refused above 32,768 in a `DIRECT_ID` session |
| `loader-exit-mbc1` | `tb_loader` `exit-mbc1`: in `MBC1_ID` the exit value at `$6000`/`$7FFF` returns to the menu exactly as in `DIRECT_ID`; `$00`/`$01`/`$11` and the exit value at other addresses change nothing |

Named assertions, synthesis-excluded:

| Assertion | Invariant |
|---|---|
| `MBC1_REGISTERS_ONLY_IN_PROFILE` | A BANK1, BANK2 or MODE update implies `profile == MBC1_ID` |
| `MBC1_FIXED_WINDOW_BANK0` | A ROM access at `$0000`-`$3FFF` in `MBC1_ID` presents store offset bits 15:14 equal to zero |
| `MBC1_EFFECTIVE_BANK_NONZERO_ALIAS` | `BANK1 == 0` implies the switched window presents bank `MBC1_RESET_BANK` |
| `MBC1_IDENTITY_OUTSIDE_PROFILE` | Outside `MBC1_ID` the store offset is the zero-extended CPU offset |
| `MBC1_ALIAS_DECODE` | The generated alias ranges equal the owner's 8 KiB select decode (constant property) |
| `UART_LOAD_IMAGE_BYTES` | Every load operation starts with a session length that is one of the two profile image lengths |
| `LOADER_EXIT_ONLY_IN_GAME_PROFILE` | In the [loader](MAS_loader_profile.md#verification): a game exit effect implies `DIRECT_ID` or `MBC1_ID` |

## External test material

Loaded through `host load --external <pin>` from [`tools/n2m/dependencies.json`](../../../../tools/n2m/dependencies.json);
no image bytes are committed and the pin records its licence notice. Having
run on the board in this profile, it is registered at slot 10 of the
[flash library](../../../tools/n2m/SPEC.md#external-images) as the two-slot
64 KiB image. The board launcher lists it once a board session has captured it.

| Pin | Game | Author | Licence | Provenance | Header |
|---|---|---|---|---|---|
| `postbot` | PostBot, the MBC1 profile's test game | Tobias Rojahn (MasterIV) | MIT (`LICENSE`, sha256 `77103cf5…9acd`) | The author's repository at commit `5e9316ae…`, in-tree `PostBot.gb` (no release asset), sha256 `65824d3d…13ad`, 65,536 bytes | `$0147` `01`, `$0148` `01`, `$0149` `00`, CGB `00`, title `POSTBOT`; banks 1-3 hold data |

Test material rule: this profile has no cartridge RAM (`$A000`-`$BFFF` reads
`$FF`, writes are ignored, RAMG enables nothing), so a game whose header
declares cartridge RAM (`$0149` not `00`, or a type with RAM) is not test
material for it, whatever its bank count.

The pinned Mooneye MBC1 selection `emulator-only/mbc1/rom_512kb.s` (type
`$01`, four banks, no RAM) builds under the
[Mooneye adapter](../../../../src/dv/mooneye/README.md) and runs as
`mooneye-rom-512kb` in this profile against
[`n2m_smoke_system`](../../../../src/dv/integration/n2m_smoke_system.sv), which
composes the same `n2m_mbc1` owner; its expected table is the executable form
of the translation rules above. The adapter's README records why the other
64 KiB case, `bits_bank1.s`, is not selected.

## References

- [Pan Docs, MBC1](https://gbdev.io/pandocs/MBC1.html), the community reference this page follows for the zero translation, masking to the cartridge size, register widths, reset values and the absence of any mode effect at or below 512 KiB. No code or test was imported.
- [Mooneye test suite](https://github.com/Gekkio/mooneye-test-suite), pinned in [`src/dv/mooneye/pins.json`](../../../../src/dv/mooneye/pins.json): `emulator-only/mbc1/rom_512kb.s` as executable specification.
- [Shared interfaces](../interfaces/MAS_interfaces.md): profile table, load session, `PROFILE`, status codes.
- [Memory owner](../memory/MAS_memory.md): ROM store, host port, decoder.
- [Loader profile](MAS_loader_profile.md): commit observation, game exit register, swap rules.
