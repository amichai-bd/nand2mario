# Flash-resident game library and boot copier

Owner: `src/rtl/storage/` and `src/dv/storage/`. Implemented: the flash
reader [`n2m_flash_reader`](../../../../src/rtl/storage/n2m_flash_reader.sv)
with its constants in [`n2m_flash_pkg`](../../../../src/rtl/storage/n2m_flash_pkg.sv),
the IP double [`n2m_sim_onchip_flash`](../../../../src/rtl/storage/n2m_sim_onchip_flash.sv),
the boot copier [`n2m_boot_copier`](../../../../src/rtl/storage/n2m_boot_copier.sv)
composed in [`n2m_v05_system`](../../../../src/rtl/system/n2m_v05_system.sv)
as the [storage arbiter](../cartridge/MAS_loader_profile.md#storage-arbiter)'s
third client, the [`tb_flash_reader`](../../../../src/dv/storage/tb_flash_reader.sv)
and [`tb_loader_system`](../../../../src/dv/cartridge/tb_loader_system.sv)
fixtures, the [`flash-proof`](../../../../src/fpga/de10_lite/flash_proof.sv) fit,
the copier in the `v05-board` image and the builder's
[library image and `.pof` path](../../../tools/n2m/SPEC.md#flash-library-image).
The [flash-resident boot sessions](../../board-bring-up.md#flash-resident-boot-and-sdram-sweep-sessions)
record the programmed `.pof`, the power-up to the menu and the read-back
library state on the board; the programming section below is the contract
those slices derive from. The board's current flash-resident image is the
[session 10](../../board-bring-up.md#session-10-reflash-with-the-composite-menu)
`v05-board` fit, packed `catalogue.bin` SHA-256 `f8425a03…`. That digest
records what is programmed into the board, not what the packer writes today:
the catalogue carries each image's CRC-32 and title and the tagline table,
so any change to the menu image or to a declared tagline after that session
moves it, and the board keeps the bytes of its own session until it is
reflashed. The tagline table moves the digest only when an entry declares a
tagline, because an undeclared one packs zero into bytes that were already
zero; every registered game declares one, and session 10 is the first image
whose board copy carries them.

## Scope

This page governs the copy of the game library held in the MAX 10 internal
flash of the DE10-Lite: the internal configuration mode the bitstream uses,
the flash layout of the images and catalogue, the on-chip flash IP boundary
and its simulation double, the power-up copier that moves the library into
SDRAM, its precedence over host loads, and how the flash is programmed. The
[SDRAM contract](MAS_sdram.md) owns the SDRAM layout the copier fills and the
line interface it writes through. The [loader profile](../cartridge/MAS_loader_profile.md)
owns the storage arbiter, the copy engine, the status bytes and what the Game
Boy CPU sees. The [charter](../../project-charter.md#game-library) owns the
decision to hold the library in flash.

## Terms

| Term | Definition |
|---|---|
| Flash | The 10M50's internal flash: sectors UFM1, UFM0, CFM2, CFM1, CFM0, in that address order. |
| Word | One 32-bit flash word; every flash address on this page is a word address in the MAX 10 flash's own numbering, where UFM1 starts at word `0x00800`. The On-Chip Flash IP's Avalon-MM data slave numbers the same words from 0 and adds that base internally (`ADDR_RANGE1_OFFSET`), so the reader drives `avmm_data_addr = flash_word - 0x00800` (`n2m_flash_pkg::FLASH_DATA_BASE`) and every image the IP or its double loads is written in the 0-based Avalon numbering. |
| Page | 64 Kb (8 KiB, 2048 words), the smallest erasable unit; a 32 KiB image is exactly 4 pages. |
| User range | Words `0x00800`-`0x2E7FF` (736 KiB): UFM1, UFM0, CFM2 and CFM1, the sectors left to the user in the single compressed image mode. |
| Library | The sixteen game slots (32 KiB images, or 64 KiB MBC1 images each filling two adjacent slots), the menu in slot 16 and the catalogue, 545 KiB, laid out as in [SDRAM](MAS_sdram.md#address-space-layout). |
| Line | 16 bytes, one SDRAM line request; four consecutive flash words, little-endian, word `k` of the line in bits `32k+31:32k` of `request_data`. |
| `clk_sys` | 25 MHz; the flash IP, the copier and the SDRAM controller share it. Counts below are `clk_sys` clocks unless a unit is given. |
| Copier | The power-up state machine that reads the library from flash and writes it to SDRAM through the [storage arbiter](../cartridge/MAS_loader_profile.md#storage-arbiter). |

## Contract

### Configuration mode

The bitstream uses the MAX 10 internal configuration mode "Single Compressed
Image". The builder writes `set_global_assignment -name INTERNAL_FLASH_UPDATE_MODE "Single Comp Image"`
into every generated project; the mode is a device option applied by the
fitter, so an assembler-only rerun cannot change it. The compressed image
lives in CFM0; UFM1, UFM0, CFM2 and CFM1 form the contiguous user range. The
`.sof` that `fpga program` writes over JTAG is unaffected by the mode. Dual
image modes are excluded: they leave 64 KiB, one image.

### Flash layout

The library mirrors the SDRAM layout word for word from flash word `0x00800`:

```text
flash_word(a) = 0x00800 + (a >> 2)      for SDRAM device byte address a, 0 <= a < 0x88400
```

| Flash word | Size | Content | Sector |
|---|---|---|---|
| `0x00800 + i * 0x2000`, i = 0..16 | 8192 words, 32 KiB | Slot `i`: one complete 32 KiB image, or half of a 64 KiB image that starts in slot `i` or `i - 1`; slot 16 is the menu | slots 0-1 UFM1, UFM0; 2-13 CFM2; 14-16 CFM1 |
| `0x22800`-`0x228FF` | 256 words, 1 KiB | Catalogue, 17 entries x 32 bytes then 17 taglines x 24 bytes, same format as the [SDRAM catalogue](MAS_sdram.md#address-space-layout), including its 24-bit length encoding (`length` word plus `length_high` in byte 24, so 32 KiB entries are byte-identical to the one-size catalogue) and its tagline table in the bytes behind the entries (an all-zero record is no tagline, so a catalogue packed before the table existed reads the same) | CFM1 |
| `0x22900`-`0x2E7FF` | 48,896 words, 191 KiB | Erased, reserved | CFM1 |

Slot `i` byte `b` is at flash word `0x00800 + (i * 32768 + b) / 4`, byte
`b % 4` of the word, least significant byte first; a 64 KiB image at slot
`i` continues into slot `i + 1` with `b` up to 65535. Slot boundaries fall
on page boundaries, so one image can be re-programmed without touching
another. Capacity: sixteen game slots, so a library of `n32` 32 KiB and
`n64` 64 KiB games needs `n32 + 2 * n64 <= 16`; the ten registered 32 KiB
games and the one registered 64 KiB game (slots 10-11) leave four slots, room
for two more 64 KiB images.
The catalogue is written with the images and is the copier's validity source:
the library is present when entry 16 has `valid == 0x01`, `length == 32768`
and `profile == LOADER_ID`. An erased flash reads `0xFF` everywhere, which is
an invalid entry.

### On-chip flash IP boundary

The flash reader [`n2m_flash_reader`](../../../../src/rtl/storage/n2m_flash_reader.sv)
wraps the Intel On-Chip Flash IP and exposes a line read interface to the copier:

| Signal | Direction | Meaning |
|---|---|---|
| `line_valid` | in | Request the line whose first word is `line_word`; held until `line_ready`. |
| `line_word[19:0]` | in | Flash word address, bits 1:0 zero. |
| `line_ready` | out | Request accepted this edge. |
| `line_data_valid` | out | One clock; `line_data[127:0]` holds the four words, word `k` in bits `32k+31:32k`. |
| `line_data[127:0]` | out | Stable until the next acceptance. |

The reader holds one line at a time: `line_ready` is high only while it is
idle, it drops with the acceptance and returns the clock after
`line_data_valid`. Counted from the accepting edge with the IP idle, the IP
accepts the Avalon read at edge 3, the reader captures word 0 at edge 11 and
word 3 at edge 14, publishes the line in clock 14 and is ready again in
clock 15. The IP is idle again only 17 clocks after a read was presented, so
a stream with `line_valid` held high waits one more clock on the second and
later lines and accepts one Avalon read, and one line, every 17 clocks
(`n2m_flash_pkg::FLASH_LINE_PERIOD_CLOCKS`). Reset returns the reader and
the IP to idle and abandons the outstanding read; nothing is published.

Inside, under synthesis the wrapper instantiates `altera_onchip_flash` from
Quartus 25.1std `ip/altera/altera_onchip_flash/` with: parallel data
interface, incrementing burst, read-only data slave, configuration mode
"Single Compressed Image", sectors UFM1, UFM0, CFM2, CFM1 "Read only", CFM0
"Hidden", clock `clk_sys`, and the 10M50 sector parameters recorded in that
IP's `altera_onchip_flash_hw_proc.tcl`. The IP is plain parameterised
Verilog, so no Platform Designer or megafunction generation runs: the wrapper
instantiates it directly with the parameter values the hw.tcl derives for
`10M50DAF484C7G` (Avalon address 18 bits, burstcount 3 bits, sectors 1-4 at
words `0x00000`-`0x2DFFF`, `ADDR_RANGE1_OFFSET 0x800`, 25 MHz timeouts,
`FLASH_SEQ_READ_DATA_COUNT = 4`, `FLASH_READ_CYCLE_MAX_INDEX = 5`), and the
[builder](../../../tools/n2m/SPEC.md#fpga-build) stages the four pinned
synthesis files ([`fpga_flash.py`](../../../../tools/n2m/fpga_flash.py)) and
writes the configuration mode assignment for every image that lists the
reader. Each line is one Avalon-MM read with `burstcount = 4` at an aligned
word address. The IP holds `waitrequest` so that the read is accepted at the
third edge after it is presented, then returns word 0 eight edges after that
acceptance and words 1-3 on the next three edges (address phase, three dummy
cycles from `FLASH_READ_CYCLE_MAX_INDEX` 5, then four words from its 128-bit
data register); a longer burst continues at four words per seven clocks. It
is idle again in the seventeenth clock after the read was presented, so a
held read is accepted every 17 clocks. These counts are simulated from the
pinned data controller, not read from its documentation. The IP's control
slave is not connected to any writer: no erase and no program path exists in
the console.

The IP drives the flash array's `xe_ye` enable from one LUT,
`(~is_busy && avmm_read) || is_read_busy` in its data controller, and the
array samples it against the IP's own LUT-gated `drclk`
(`~enable_drclk_neg_reg || clock || ...`), which reaches the array about
0.7 ns after the fabric clock at the fast corner with a 1.0 ns hold
requirement. Synthesis merges the reader's `avmm_read` decode into that LUT,
so both the reader's `state.phase` register and the IP's `read_state`
register reach `xe_ye` with a hold margin the fitter alone leaves near zero
(0.068 and -0.044 ns measured); the vendor `.sdc` constrains only its
`flash_busy_reg`/`flash_busy_clear_reg`. The
[system-clock hold uncertainty](../../clocks-resets-cdc.md#timing-constraints)
supplies the margin; no false path is applied to this check.

Under the predefined `VERILATOR` macro the wrapper instantiates
[`n2m_sim_onchip_flash`](../../../../src/rtl/storage/n2m_sim_onchip_flash.sv)
instead, the same rule as the [ADC double](../../fpga-controls.md) and the
[memory primitive](../common/MAS_memory_primitives.md): a repository double of
the data slave (`read`, `write`, `addr`, `burstcount`, `waitrequest`,
`readdatavalid`, `readdata`, the IP's port names) that loads the build's
flash image with `$readmemh`, returns `0xFFFFFFFF` for words the file does
not define, and reproduces the cadence above: the read accepted at the third
edge, four `readdatavalid` words eight to eleven edges after it, four words
per seven clocks for a longer burst, the next read captured 17 edges after
the previous capture, at most 128 words per burst. The image is a
word-addressed Verilog hex file (`@<avalon word>` records, one 32-bit word
each) in the 0-based Avalon numbering; the Intel HEX the assembler reads for
`INIT_FILENAME` encodes the same words byte-addressed, so the builder emits
both, as the vendor IP itself keeps separate `.hex` and `.dat` files. The
double fails with a named fatal on a write (`FLASH_MODEL_WRITE`), a read
whose fields change under `waitrequest` (`FLASH_MODEL_HOLD`), a misaligned,
out-of-range or zero burst (`FLASH_MODEL_ALIGNED`, `FLASH_MODEL_RANGE`,
`FLASH_MODEL_BURST`). Quartus never sees the double. The Windows
[Questa compile gate](../../../tools/n2m/SPEC.md#questa-compile-gate) has one
elaboration stand-in for the IP, `altera_onchip_flash`, port- and
parameter-compatible and empty, beside the other five.

### Boot copier

[`n2m_boot_copier`](../../../../src/rtl/storage/n2m_boot_copier.sv) owns the
flash reader instance (`u_reader`) and one pending SDRAM write. `FLASH_LIBRARY`
places that instance and defaults to 1, so every target that reads a library is
unchanged, down to the fitted instance path every check here pins: the conditional
holds one unnamed item, which Quartus flattens, where a named generate block would
have moved the reader to `g_reader.u_reader` and broken each of them. A composition selecting 0 omits the reader and the
[On-Chip Flash IP](#on-chip-flash-ip-boundary) beneath it, and the copier's line
interface reads as never ready with no data: it reaches `WAIT_SDRAM` and stays
there, because a board with no library also has no storage to copy into. That is a
compile-time choice rather than a runtime one because the IP names the MAX 10 part
it belongs to, so a device without that internal flash cannot elaborate the reader
at all; [the composition](../system/MAS_system.md#host-free-composition) owns
which boards select it. Clock 0 is
the first clock after `reset_sys` release, as in the
[SDRAM initialization](MAS_sdram.md#initialization). From release the copier
performs, in order:

1. `WAIT_SDRAM`: wait for the SDRAM controller's `initialized`, visible from
   clock 5036; `CHECK` begins in clock 5037.
2. `CHECK`: read the catalogue's entry 16 (flash words `0x22880`-`0x22887`,
   two line reads). The first line is accepted at the edge ending clock 5037
   and published in clock 5052 (14 clocks after acceptance at the
   [reader cadence](#on-chip-flash-ip-boundary)); the second is presented
   the clock the reader is ready again and published 17 clocks after the
   first, in clock 5069, where the entry is decoded. `CHECK` therefore lasts
   exactly 33 clocks (5037-5069) and the next phase begins in clock 5070.
   The entry is present when `valid == 0x01`, `length == 32768` and
   `profile == LOADER_ID`; a `DIRECT_ID` entry 16, which the engine's select
   would accept, is invalid to the copier because the flash menu is the
   loader-profile menu. Otherwise go to `DONE` with `flash_boot` still 0:
   SDRAM is left as [phase 1](../cartridge/MAS_loader_profile.md#boot-source)
   expects and nothing else on this page happens at this power-up.
3. `COPY`: for SDRAM byte address `a = 0x0000000` to `0x00883F0` in steps of
   16, read flash line `flash_word(a)` and write it to SDRAM line `a` through
   the arbiter, in ascending order: slots 0-16, then the catalogue. 34,880
   lines (`n2m_flash_pkg::FLASH_COPY_LINES`). The reader's published line is
   the first pipeline stage (it holds until the next acceptance) and the
   pending write register the second: a published line moves into the free
   pending register, otherwise it waits in the reader, and the next flash
   line is requested only once the reader's line has moved, so at most one
   flash read and one SDRAM write are in flight. `flash_boot` is set on the
   edge the last line is accepted, which is the edge `COPY` leaves; this is
   its only setting event, and only `reset_sys` clears it.
4. `BOOT`: one clock. Request a select of slot 16 through the
   [copy engine](../cartridge/MAS_loader_profile.md#copy-engine-and-rom-store-port-ownership)
   exactly as [KEY1 return](../cartridge/MAS_loader_profile.md#key1-return)
   does (`boot_return` into the loader's return path), so the menu image is
   swapped into the ROM store and the core is reset; and clear the
   [host pause](../uart/MAS_uart.md#core-and-storage-integration) exactly as
   the host `RUN` command does (`boot_run` into the core control owner), so
   the menu runs without any host command. A later host `HALT` pauses it as
   usual.
5. `DONE`: idle until the next `reset_sys`. Core resets and host loads never
   restart the copier.

Timing bounds a testbench checks:

- Flash side: a line read is published 14 clocks after the reader accepts
  it from idle (3 clocks of `waitrequest`, 11 to the last word) and a held
  stream delivers one line per 17 clocks. The reader never issues a second
  read before the previous data arrived.
- SDRAM side: the copier keeps `request_valid` high through `COPY`; the
  [sustained throughput](MAS_sdram.md#access-sequence-and-latency-bounds) of
  one line per 18.6 clocks bounds the copy: 34,880 lines complete within
  648,768 clocks (25.95 ms) of arbiter access plus the flash prefetch of the
  first line, so `COPY` lasts at most 700,000 clocks (28.0 ms,
  `FLASH_COPY_BOUND_CLOCKS`) and at least 34,880 x 18 = 627,840 clocks. At
  17 clocks per line the flash stays ahead of the SDRAM's 18.6, so the SDRAM
  sets the pace; the `flash-copy` fixture measures 647,216 clocks (25.9 ms, 18.56 per line)
  from clock 5070 to the last acceptance in clock 652,286.
- Whole boot: `CHECK` 33 clocks, `COPY` at most 700,000 clocks, the slot 16
  swap at most 80,000 edges (3.2 ms, the
  [swap bound](../cartridge/MAS_loader_profile.md#select-register)):
  the menu runs within 800,000 clocks (32.0 ms) of `initialized`, so within
  805,036 clocks of reset release; the fixture measures the menu
  running (paused released, first dot) in clock 705,389 from release, 700,353
  after `initialized`. `flash_boot` is visible before the `BOOT` select is
  requested.

### Precedence over host loads

While the copier is in `CHECK` or `COPY`:

- `sdram_ready` (`$A000` bit 5 and `LIBRARY_STATUS` bit 5) is 0: it is
  defined as the controller's `initialized` and the copier in `BOOT` or
  `DONE` (`library_pending` low), so it never pulses in the clock between
  `initialized` and `CHECK`; with erased flash it rises in clock 5070. The
  UART endpoint validates `SDRAM_WRITE`/`SDRAM_READ` against this bit, so
  they return `BAD_VALUE` as the
  [host interaction](../cartridge/MAS_loader_profile.md#host-interaction) rules
  already state.
- The arbiter serves only the copier; no engine or host line request exists
  yet because the core is paused with an invalid image after `reset_sys`.
- The endpoint reports `STATE == LOADING`, exactly as during a swap (the
  loader's exported `copy_busy` and `swap_busy` include the copier's `CHECK`
  and `COPY`), so `LOAD_BEGIN` and `WRITE_HOST(LIBRARY_CONTROL)` return
  `BAD_STATE`; the host retries after at most 32 ms (the whole-boot bound
  above) instead of the 3.2 ms swap bound. Every other host command keeps its
  existing precondition behaviour. Before `initialized` the endpoint is
  `PAUSED` as in phase 1; at 115200 baud no host packet completes inside
  those 5036 clocks.

After `DONE`, host commands behave as in phase 1: a host load session
excludes the engine, host SDRAM line commands overwrite slots and catalogue
in SDRAM, and `key1_return` works. Flash is never written by the console, so
the next power-up restores the flash library regardless of what the host
loaded. `$A000` bit 3, `flash_boot`, and `LIBRARY_STATUS` bit 3 report
whether this power-up's library came from flash; the menu may display it.

### Programming the flash

The flash is programmed only through JTAG with the Quartus Programmer:

1. The [builder](../../../tools/n2m/SPEC.md#flash-library-image) assembles
   the library image `library.hex` (Intel HEX, byte addressed at
   `4 * (flash_word - 0x00800)`, the 0-based Avalon numbering of the Terms
   above) from the registered images and the catalogue it produces for the
   [host loader](../../../tools/n2m/host/SPEC.md) with the same code; every
   word of the user range is written, empty slots and the reserved range as
   `0xFFFFFFFF`, so the programmed flash reads exactly what the double reads
   from the sparse `library.dat`.
2. The flash IP instance names `library.hex` through the reader's
   `INIT_FILENAME` parameter, so the assembler's `design.pof` holds the
   compressed bitstream in CFM0 and the library in the user range; the
   builder checks the user range of the `.pof` word for word against the
   assembled image and records the CFM0 bytes used. A changed image changes
   the build fingerprint, so the builder runs a new attempt rather than an
   assembler-only rerun.
3. [`fpga program --pof`](../../../tools/n2m/SPEC.md#flash-programming)
   writes that `.pof` over JTAG with the same attempt-record rules as the
   `.sof` path plus the flash evidence rules, running
   `quartus_pgm -m jtag -o "pvb;<pof>"`: program, verify and blank-check.
   Programming replaces the CFM0 image and the user range; the in-system
   programming time from the MAX 10 configuration guide is 52.9 s for CFM0,
   22.7 s for CFM1 and 30.2 s for CFM2 on the 10M50 before verify and system
   overhead. The tool records the measured time as `isp_seconds`; the
   [board sessions](../../board-bring-up.md#flash-resident-boot-and-sdram-sweep-sessions)
   hold the measured values.
4. A host command that writes flash through the IP's program path is
   deferred: the IP is instantiated read-only, and every sector keeps its
   write protection. Reopening this needs an owner decision.

## Edge cases

In priority order:

1. `reset_sys` at any clock: the copier returns to `WAIT_SDRAM`, `flash_boot`
   to 0, every outstanding flash read is abandoned; the flash IP is reset with
   the console.
2. Erased or invalid entry 16: no SDRAM write, no select, `flash_boot = 0`;
   the host load of phase 1 is the only way to a valid library at this
   power-up.
3. A flash read returning a line while the arbiter has not yet accepted the
   previous SDRAM write: the line waits in the reader, which holds it until
   its next acceptance, and no further flash read is issued; nothing is
   dropped or reordered (`FLASH_COPY_ORDER`, `FLASH_COPY_HOLD_FREE`).
4. Host `LOAD_BEGIN` or a `WRITE_HOST(LIBRARY_CONTROL)` during `COPY`:
   refused with `BAD_STATE` by the existing `LOADING` rules; the copier is
   never interrupted.
5. A catalogue in flash whose entry 16 is valid but whose game entries are
   invalid: the copy still runs for all 17 slots; the menu shows the empty
   slots as phase 1 does.

## Verification

Simulation runs under Verilator on Linux with the double loaded from the same
`library.hex` the build would use. Required fixtures, each within the
[wall budget](../../../tools/n2m/SPEC.md#test-wall-budget):

| Fixture | Checks |
|---|---|
| `flash-copy` | [`tb_loader_system`](../../../../src/dv/cartridge/tb_loader_system.sv) with the double programmed from the fixture's own 17-image library, slot 3 left erased: `initialized` at clock 5036, no SDRAM request before it, every accepted write ascending from 0 with the flash line's bytes (34,880 lines), `COPY` within 627,840-700,000 clocks of clock 5070, `sdram_ready` low until `flash_boot`, the menu running (profile `LOADER_ID`, not paused, dots advancing, epoch 1) within 800,000 clocks of `initialized` with no host command; then every SDRAM word of the library range equals the flash byte (erased slot 3 reads `0xFF`), `LIBRARY_STATUS` shows `flash_boot`, `sdram_ready` and result `OK`, a host `HALT` pauses and `RUN` resumes |
| `flash-blank` | Erased double: `sdram_ready` first high in clock 5070 exactly, no SDRAM request, no engine job, `flash_boot = 0`, the console paused with no image; then phase 1 unchanged: `LIBRARY_STATUS` `0x00FF0020`, an `SDRAM_WRITE`/`SDRAM_READ` round trip, a host load of a game paused until `RUN` |
| `flash-precedence` | Programmed double with the host present during `COPY`: `STATE == LOADING`, `LIBRARY_STATUS` `0x00FF0000`, `LOAD_BEGIN` and `WRITE_HOST(LIBRARY_CONTROL)` `BAD_STATE`, `SDRAM_READ` and `SDRAM_WRITE` `BAD_VALUE`; after the boot the menu runs, SDRAM equals the flash, `SDRAM_READ` returns library lines, a host load of a game succeeds, `SDRAM_WRITE` overwrites a library line and every double word is unchanged |
| `flash-reader` | Through the reader against the double loaded from a fixture image the testbench writes: every slot's first and last line, the whole catalogue, the line either side of each sector start and the last user line, each compared word for word with the fixture's own copy; an untouched slot, the reserved range and the user range's end read `0xFFFFFFFF`; the Avalon address equals the flash word less `0x00800`, burstcount is 4, `waitrequest`/`readdatavalid` and `line_data_valid`/`line_ready` follow the edge counts above, the catalogue streams back to back at one Avalon read per 17 clocks, the published line holds until the next acceptance, and a reset during a read publishes nothing |
| `flash-reader-fault-misaligned`, `flash-reader-fault-range` | A misaligned request fails `FLASH_LINE_ALIGNED`; a word past the user range fails `FLASH_LINE_RANGE` |

Assertions the copier and reader carry:

| Assertion | Rule |
|---|---|
| `FLASH_LINE_ALIGNED` | acceptance implies `line_word[1:0] == 0` |
| `FLASH_LINE_RANGE` | acceptance implies `0x00800 <= line_word <= 0x2E7FF` |
| `FLASH_ONE_OUTSTANDING` | no acceptance while a read has no `line_data_valid` yet |
| `FLASH_DATA_EXPECTED` | `readdatavalid` only while a line is outstanding |
| `FLASH_COPY_ORDER` | each accepted SDRAM write address is the previous one plus 16, starting at 0 (an independent order register) |
| `FLASH_COPY_BOUND` | `COPY` leaves within 700,000 clocks of entering |
| `FLASH_COPY_REQUEST_IN_COPY` | an SDRAM request implies `COPY` |
| `FLASH_COPY_LINE_EXPECTED` | a published line implies a flash read outstanding |
| `FLASH_COPY_HOLD_FREE` | a flash line is accepted only while the reader's previous line has moved on |
| `FLASH_BOOT_AFTER_COPY` | `flash_boot` rises only from `COPY` |
| `LOADER_COPIER_EXCLUSIVE` | the copier's `CHECK`/`COPY` never overlaps an engine job ([loader](../cartridge/MAS_loader_profile.md)) |
| `FLASH_NO_WRITE` | the IP's control slave `write` is constant 0 |

Questa compiles the wrapper against the `altera_onchip_flash` stand-in under
the compile gate. The [`flash-proof`](../../../../src/fpga/de10_lite/README.md)
fit places the reader on the composed image's PLLs and reset and walks the
user range continuously; the builder checks `UFM blocks : 1 / 1`, the
configuration mode assignment and the unchanged PLL, pin and slack evidence.
The `v05-board`, `v05` and `v05-controls-board` images place the copier and
the IP under `u_system|u_copier|u_reader` ([`fpga_flash.reader_path`](../../../../tools/n2m/fpga_flash.py))
with the same staging, mode assignment and classified diagnostics, and the
builder feeds the reader's `INIT_FILENAME` and checks the `.pof` for them as
for `flash-proof`; their audit reports the IP's strobe clock once per timing
netlist update (seven, against one for `flash-proof`), which the builder
counts from the audit script. The board check, program the `.pof`,
power-cycle without a host, observe the menu and read the library state back,
ran on `v05-board` in the
[flash-resident boot sessions](../../board-bring-up.md#flash-resident-boot-and-sdram-sweep-sessions):
the copier set `flash_boot`, the catalogue read from SDRAM equalled the packed
catalogue and the menu frame was pixel-exact. After host library loads and a
full SDRAM sweep had overwritten the SDRAM, both a JTAG flash programming
(the device reconfigures from CFM0 without a power cycle) and a KEY0 press ran
the copier again and restored the flash menu with the same catalogue and a
pixel-exact frame
([session 6](../../board-bring-up.md#session-6-flash-reconfiguration-restores-the-library-without-a-power-cycle)).
A fourth write carried a rebuilt game into CFM0 and repeated the proofs on the
new image: the device reconfigured from CFM0 again without a power cycle, the
catalogue read from SDRAM equalled the packed one, the menu frame was
pixel-exact, and the rebuilt game started from the menu and answered the joypad
([session 8](../../board-bring-up.md#session-8-reflash-with-the-updated-v05-image)).
A fifth write carried the plated-list menu image into CFM0 and repeated the
same proofs: the device reconfigured from CFM0
without a power cycle, the catalogue read from SDRAM equalled the packed one,
the menu frames were pixel-exact in both nudge phases, and a game started from
the menu and returned to it
([session 9](../../board-bring-up.md#session-9-reflash-with-the-plated-list-menu)).
A sixth write carried the composite menu and the populated tagline table into
CFM0, the image the board now holds: the catalogue read from SDRAM equalled the
packed one, taglines included, and every menu frame class was read back
pixel-exact
([session 10](../../board-bring-up.md#session-10-reflash-with-the-composite-menu)).
The copier's and reader's timing evidence remains simulation against the
double plus the fit.

### Measured facts

Measured on 2026-09-15 for the go decision recorded in the
[charter](../../project-charter.md#game-library), on `v05-board`
at `5da9148` with Quartus Prime 25.1std.0 Build 1129 Lite on Windows:

- Sector sizes: UFM1 4 pages, UFM0 4, CFM2 48, CFM1 36, CFM0 84 of 64 Kb
  (UG-M10UFM Table 1); user range 5,888 Kb = 736 KiB in the single compressed
  mode, 448 KiB (UFM1+UFM0+CFM2) in the single uncompressed mode, 64 KiB in
  the dual and memory-initialization modes (UG-M10UFM Table 2, UG-M10CONFIG
  Table 3 and Figure 2). Word addresses from the IP's
  `device_sector_address_offset`, 10M50 rows.
- Default build (no mode assignment; Quartus default `Single Image`): whole
  `fpga build` 188 s; 10,222 of 49,760 logic elements, 761,704 memory bits,
  UFM blocks 0 of 1; `design.sof` 3,216,546 bytes; `design.pof` 1,450,252
  bytes, of which the first 455.9 KiB are erased (`0xFF`) and 870.0 KiB are
  programmed: the uncompressed image in CFM0+CFM1.
- Same sources with `INTERNAL_FLASH_UPDATE_MODE "Single Comp Image"` added:
  fit and assembler pass in 154 s with identical resources; `design.pof` is
  the same size with 743.9 KiB erased from its start and 339.1 KiB
  programmed, so the compressed image fits CFM0 (672 KiB) with about 333 KiB
  spare. `quartus_cpf` emits no `.rbf` for the 10M50, so erased-byte counts
  are the size evidence.
- `flash-proof` fit of the reader on the composed image's PLLs and reset
  (Quartus Prime 25.1std.0 Build 1129 Lite): 428 logic elements, 317
  registers, 2 PLLs, `UFM blocks : 1 / 1`, no memory bits; every setup,
  hold, recovery, removal and pulse-width slack positive at the three
  corners (worst hold 0.11 ns); the IP's sense-enable strobe is the one
  unconstrained clock and, with the atom register it clocks, one of two
  extra `no_clock` rows, both classified by name in the
  [builder record](../../../tools/n2m/SPEC.md#diagnostic-classification).
  The IP cadence in simulation (read accepted at the third edge, four words
  sampled at edges 8-11 after it, idle again in the seventeenth clock, so 17
  clocks per line back to back) was simulated from the shipped data
  controller under Verilator with the reader's parameters and is checked by
  `flash-reader` against the double; it is not yet measured on the board.
- Flash IP sustained burst rate (4 words per 7 clocks) and program/erase times
  (word typical 102 us, maximum 305 us; sector or page erase at most 350 ms;
  endurance at least 10,000 cycles) come from the shipped IP RTL and
  UG-M10UFM; they are not yet measured on the board.

## References

- Intel MAX 10 User Flash Memory User Guide, UG-M10UFM, 2020.06.30: Table 1
  "UFM and CFM Array Size", Table 2 "Dynamic Flash Size Support: Flash and
  Analog Variants", section 4.2 (Avalon-MM operating modes, read and burst
  timing, program and erase), Table 7 (initialization files).
- Intel MAX 10 FPGA Configuration User Guide, UG-M10CONFIG, 2020.11.05:
  Table 3 "Supported Internal Configuration Modes", Figure 2 "Configuration
  Flash Memory Sectors Utilization", Table 4 "Configuration Flash Memory
  Programming Time", section 3.3 (selecting the mode, `.pof` generation).
- Quartus Prime 25.1std Lite, `ip/altera/altera_onchip_flash/`: `altera_onchip_flash.v`,
  `altera_onchip_flash_avmm_data_controller.v`, `altera_onchip_flash_hw_proc.tcl`
  (sector sizes, address offsets, 10M40/50 read cycle parameters),
  `bin64/assignment_defaults.qdf` (`INTERNAL_FLASH_UPDATE_MODE` default).
- [SDRAM storage and timing](MAS_sdram.md), [loader profile](../cartridge/MAS_loader_profile.md),
  [shared memory primitives](../common/MAS_memory_primitives.md),
  [n2m builder](../../../tools/n2m/SPEC.md#fpga-build), [charter](../../project-charter.md#game-library).
