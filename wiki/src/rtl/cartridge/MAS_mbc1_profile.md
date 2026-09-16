# MBC1 profile

Owner: [`src/rtl/cartridge`](../../../../src/rtl/cartridge/n2m_loader.sv), beside
the [loader profile](MAS_loader_profile.md), which already observes the resolved
CPU ROM write commits this profile decodes. The generated
[interface table](../interfaces/MAS_interfaces.md) owns `PROFILE_MBC1_ID`,
`PROFILE_STORE_BYTES` and every `MBC1_*` constant this page names.

Implementation status: this page is the reviewed contract; the register block,
the 64 KiB store and the fixtures below are not in `src/` yet. The RTL slice is
[#714](https://github.com/amichai-bd/nand2mario/issues/714) under the parent
[#307](https://github.com/amichai-bd/nand2mario/issues/307).

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
given; the 32 KiB swap and window fill paths are unchanged and touch offsets
`$0000`-`$7FFF` only.

Width dependency: today `PROFILE_ROM_BYTES` sizes the store and its host range
in [`n2m_memory_stores`](../../../../src/rtl/memory/n2m_memory_stores.sv), the
load address and presence sweep in [`n2m_uart_load`](../../../../src/rtl/uart/n2m_uart_load.sv)
and [`n2m_uart_presence_store`](../../../../src/rtl/uart/n2m_uart_presence_store.sv),
and the `LOAD_BEGIN` size and `LOAD_WRITE`/`READ_ROM` range checks in
[`n2m_uart_validate`](../../../../src/rtl/uart/n2m_uart_validate.sv); the
15-bit offset ports of [`n2m_memory_decode`](../../../../src/rtl/memory/n2m_memory_decode.sv),
[`n2m_rom_port_arbiter`](../../../../src/rtl/cartridge/n2m_rom_port_arbiter.sv)
and [`n2m_loader_engine`](../../../../src/rtl/cartridge/n2m_loader_engine.sv)
carry the same assumption. The implementation re-parameterizes the store,
presence bitmap and offset ports on `PROFILE_STORE_BYTES` and the session
checks on the loaded profile's image length; `PROFILE_ROM_BYTES` keeps its
32 KiB meaning for the direct and loader profiles.

The [SDRAM layout](../storage/MAS_sdram.md#address-space-layout), the flash
library and the catalogue carry 32 KiB images only: `LIBRARY_SLOT_BYTES` is
32768 and the catalogue `length` field is 16 bits wide, so it cannot express
65536. A 64 KiB image therefore reaches the store through the host load session
only; carrying it in the library is
[#712](https://github.com/amichai-bd/nand2mario/issues/712).

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

Simulation runs under Verilator on WSL with the real memory owner and the
bus-driven fixture style of [`tb_loader`](../../../../src/dv/cartridge/tb_loader.sv);
expectations come from this page and an original image the fixture builds
itself: every bank carries a distinct signature (its bank number, its
complement and an address-dependent pattern) so that a wrong bank is a byte
mismatch, never a silent pass. Composed execution uses the existing Intel
preload path with an original program that switches banks and reports what it
read. Mooneye `emulator-only/mbc1/rom_512kb` and `bits_bank1` are the pinned
external executable specification for this capacity (type `$01`, four banks,
no RAM) once the [Mooneye adapter](../../../../src/dv/mooneye/README.md) accepts a 64 KiB
MBC1 selection; their expected tables encode the same zero-translation and
masking rules.

| Fixture | Independent check |
|---|---|
| `mbc1-map` | All 65,536 addresses in `MBC1_ID` after reset: fixed window equals bank 0, switched window equals bank 1, `$A000`-`$BFFF` reads `$FF`; in `DIRECT_ID` and `LOADER_ID` the same image bytes at `$0000`-`$7FFF` read as today and BANK1 writes change nothing |
| `mbc1-bank` | BANK1 values 0-31 and 32-63 through both ends of the alias range: the switched window equals the effective bank byte for byte on the read after the commit; BANK2 0-3 and MODE 0-1 change nothing; RAMG `$0A`/`$00` change nothing |
| `mbc1-reset` | Bank 3 selected, then host `RESET` and then a fresh load: the switched window shows bank 1 at the first read; the store is retained across `RESET` |
| `mbc1-load` | Full 64 KiB `LOAD_BEGIN`/`LOAD_WRITE`/`LOAD_END`/`READ_ROM` round trip, byte for byte; the size mismatches of edge case 5 refused; a 32 KiB direct load still refuses offset `$8000` |
| `mbc1-exit` | `$10` to `$6000` and `$7FFF` raises one return request each, `$00`/`$01`/`$11` raise none, and MODE reads back as `data[0]` through the test hook |
| `mbc1-fault` | A deliberately wrong bank in the reference (bank 2 expected where 1 is read) fails with the expected/actual bytes and a nonzero exit |

Named assertions, synthesis-excluded:

| Assertion | Invariant |
|---|---|
| `MBC1_REGISTERS_ONLY_IN_PROFILE` | A BANK1, BANK2 or MODE update implies `profile == MBC1_ID` |
| `MBC1_FIXED_WINDOW_BANK0` | A CPU read at `$0000`-`$3FFF` in `MBC1_ID` presents store offset bits 15:14 equal to zero |
| `MBC1_EFFECTIVE_BANK_NONZERO_ALIAS` | `BANK1 == 0` implies the switched window presents bank `MBC1_RESET_BANK` |

## References

- [Pan Docs, MBC1](https://gbdev.io/pandocs/MBC1.html), the community reference this page follows for the zero translation, masking to the cartridge size, register widths, reset values and the absence of any mode effect at or below 512 KiB. No code or test was imported.
- [Mooneye test suite](https://github.com/Gekkio/mooneye-test-suite), pinned in [`src/dv/mooneye/pins.json`](../../../../src/dv/mooneye/pins.json): `emulator-only/mbc1/rom_512kb.s` and `bits_bank1.s` as executable specification.
- [Shared interfaces](../interfaces/MAS_interfaces.md): profile table, load session, `PROFILE`, status codes.
- [Memory owner](../memory/MAS_memory.md): ROM store, host port, decoder.
- [Loader profile](MAS_loader_profile.md): commit observation, game exit register, swap rules.
