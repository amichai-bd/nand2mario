# Loader profile

Planned owner: `src/rtl/cartridge/`. No implementation exists yet; the slot
loader, loader mapper and KEY1 slices of
[#658](https://github.com/amichai-bd/nand2mario/issues/658) implement this page
and close the gap. Until then this is the contract those slices derive their
tests from.

## Scope

The loader profile is our own cartridge behavior for the on-board menu. It
governs: what the Game Boy CPU sees at `$0000`-`$7FFF` and `$A000`-`$BFFF`
while the menu runs; the bank and select registers; the copy engine that moves
a 32 KiB image between [SDRAM](../storage/MAS_sdram.md) and the ROM store; the
core reset sequence around a swap; image validity; KEY1 return; and the rules
between this hardware and the [UART endpoint](../uart/MAS_uart.md). It is not
an MBC and does not run any cartridge not built here. The menu program itself
is software with its own specification; this page fixes only what hardware
gives it.

## Terms

| Term | Definition |
|---|---|
| Profile | The value the endpoint publishes in the `PROFILE` host register: `DIRECT_ID` (1) is the existing mapperless game profile; `LOADER_ID` (2) is this profile. The generated [interface table](../interfaces/MAS_interfaces.md) owns both constants once the loader slice adds `LOADER_ID`. |
| ROM store | The existing 32 KiB `dmg-direct-v1` store in the [memory owner](../memory/MAS_memory.md#stores-and-ownership); byte offset `o` is CPU address `o`. |
| Low half, upper half | ROM store offsets `$0000`-`$3FFF` and `$4000`-`$7FFF`. |
| Image index | 0-15 a game slot, 16 the menu image; the [SDRAM layout](../storage/MAS_sdram.md#address-space-layout) puts image `i` at device address `i * 32768`. |
| Window bank | A 6-bit number `n`; window bank `n` is SDRAM device addresses `n * 16384` to `n * 16384 + 16383`. Image `i` is banks `2i` and `2i+1`; the catalogue is in bank 34. |
| Copy | The engine moving 32 KiB (image swap) or 16 KiB (window fill) from SDRAM into the ROM store. |
| Swap | A copy of a whole image into the ROM store followed by a core reset into that image's profile. |
| Edge | One `clk_sys` rising edge, 40 ns. |

## Contract

### Address map in the loader profile

While `PROFILE == LOADER_ID`, the CPU memory decoder applies this table in
place of the direct profile's ROM and absent-cartridge rules. Everything else
(`$8000`-`$9FFF`, `$C000`-`$FFFF`) is unchanged from the
[direct profile](../memory/MAS_memory.md#fixed-service-and-cpu-commit).

| CPU range | Read | Write |
|---|---|---|
| `$0000`-`$3FFF` | ROM store low half, the fixed menu code | `$0000`-`$1FFF`: ignored. `$2000`-`$3FFF`: bank register. |
| `$4000`-`$7FFF` | ROM store upper half, the window into SDRAM bank `bank`; `$FF` while `window_busy` | `$4000`-`$5FFF`: ignored. `$6000`-`$7FFF`: select register. |
| `$A000` | Status byte, [below](#status-bytes) | ignored |
| `$A001` | `bank` register value, bits 5:0; bits 7:6 zero | ignored |
| `$A002` | Last result code, [below](#status-bytes) | ignored |
| `$A003` | Last image index selected, 0-16; `$FF` before the first selection since global reset | ignored |
| `$A004`-`$BFFF` | `$FF` | ignored |

Reads keep the memory owner's one-edge service: every byte above is either a
ROM store read or a registered byte, so no CPU cycle is stretched. Register
writes take effect on the `bus_commit` edge, like every peripheral write. The
register addresses use the ranges MBC1 uses for its bank and mode registers so
that our assembler and linker conventions carry over; the meaning is ours and
the profile is identified by `LOADER_ID`, never by an MBC cartridge type byte.

### Bank register

A commit to `$2000`-`$3FFF` writes `bank[5:0] = data[5:0]` and starts a window
fill: the copy engine reads SDRAM bank `bank` (16 KiB, 1024 lines) and writes
it into the ROM store upper half. `window_busy` is true from the commit edge
until the last byte is written. A commit while `copy_busy` (window fill or
swap in progress) is ignored and sets no error; the menu polls `$A000` bit 7
first. After global reset `bank` is 0 and no fill has run: the upper half
holds whatever the last image left there, and `window_ready` is 0 until the
first fill completes. `window_ready` is also cleared by every swap and by
every host load session, because both overwrite the upper half; `bank`
keeps its value, and the menu must commit the bank register again to
refill the window.

Reads of `$4000`-`$7FFF` return `$FF` while `window_busy`, so a program that
does not poll observes a defined value rather than a mix of old and new bytes.
The window is a copy, not a live view: SDRAM writes by the host after the fill
are not seen until the next bank commit.

Window fill bound: 40,000 edges (1.6 ms) from the commit edge to `window_busy`
falling. Derivation: the fill is SDRAM-bound at 1024 lines of about 18.6
edges each, about 19,050 edges; the 16,384 byte writes on the ROM store's
host port overlap the SDRAM reads through the engine's one-line buffer and
nothing else uses that port during a fill. The bound is checked; the
derivation is guidance.

### Select register

A commit to `$6000`-`$7FFF` with `data` in 0-16 starts a swap of image index
`data`. Other values are ignored and leave `$A002` unchanged. A commit while
`copy_busy` is ignored. The engine:

1. Reads catalogue entry `data` (2 lines) and checks `valid == 0x01`,
   `length == 32768` and `profile` in {`DIRECT_ID`, `LOADER_ID`}. Failure:
   result `INVALID_SLOT`, nothing else changes, the menu keeps running.
2. Requests a pause from the core control owner and waits for `paused`.
3. Clears `image_valid`; the endpoint reports `LOADING`.
4. Copies the 32 KiB image, line by line, into the ROM store through the host
   ROM write port, accumulating CRC-32/ISO-HDLC over the 32768 bytes in the
   order written, with the same `crc32_byte` function `LOAD_END` uses.
5. Compares the CRC with the catalogue `crc32`. Mismatch: result
   `CRC_MISMATCH`, `image_valid` stays 0, the core stays paused with `PROFILE`
   0; the host `LOAD_BEGIN` or the physical KEY1 recovers. Match: publish
   `PROFILE = catalogue profile`, `image_valid = 1`, result `OK`.
6. Requests a core reset through the core control owner (same effect as the
   host `RESET` command: epoch + 1, dot and retirement counters 0, direct
   entry state), waits for `core_initialized`, then releases its own pause
   request so the new image runs without a host `RUN`. The engine's pause
   request is a separate bit from the host's `host_pause`: a host `HALT`
   held before or during the swap keeps the console paused afterwards until
   the host sends `RUN`.

`copy_busy` is true from the accepting commit edge through step 6.
Swap bound: 80,000 edges (3.2 ms) from the accepting edge to `copy_busy`
falling, including the pause wait (at most one M-cycle, 24 edges), the 2048
lines (at most 38,100 SDRAM edges, overlapped with 32,768 ROM writes that have
the port to themselves while paused, so about 38,200 edges), the reset and the
8192-edge RAM initialization sweep. The bound is checked; the sum is guidance.

### Copy engine and ROM store port ownership

The engine is the only writer of the ROM store other than the UART load owner.
Both reach the same host ROM write port of the memory owner through a port
arbiter in this owner:

- The UART load owner owns the port while the endpoint is in a host load
  session (`LOAD_BEGIN` accepted, `LOAD_END` or a new `LOAD_BEGIN` not yet
  completed).
- The engine owns the port while `copy_busy`.
- Neither may start while the other owns it; see [host interaction](#host-interaction)
  for the visible rules. A grant to both on one edge is a named fatal
  assertion, `LOADER_PORT_EXCLUSIVE`.

The ROM store's [host port](../memory/MAS_memory.md#raw-store-service) is
port A of the store; CPU and DMA ROM reads use port B. The two ports are
independent, so the engine writes on every edge it has data and nothing
yields to CPU reads, during a fill as well as during a swap. During a window
fill the core runs and the engine writes only offsets `$4000`-`$7FFF`; a CPU
read of the byte being written on the same edge is the primitive's
unspecified mixed-port case, and the `$FF`-while-`window_busy` rule masks it
because that read never reaches the CPU. The engine never reads the ROM
store; the CRC comes from the bytes it writes.

### Storage arbiter

The engine and the host SDRAM commands are the two clients of the single
[line request interface](../storage/MAS_sdram.md#line-request-interface).
The arbiter presents them to the controller as one requester:

- At most one outstanding line per client; the arbiter holds a client's
  request until the controller accepts it and, for reads, returns its
  response to that client only.
- While `copy_busy` for a swap, host line requests wait; the host command
  completes after the swap (the [host interaction](#host-interaction) bounds
  it). During a window fill the arbiter alternates: after an engine line is
  accepted, a waiting host line is accepted next.
- The arbiter adds one edge of latency to acceptance and none to the response.
- The [boot copier](../storage/MAS_flash_library.md#boot-copier) is the third
  client. While it is in `CHECK` or `COPY` it has priority and is in practice
  the only requester, because the core is paused with an invalid image and
  `sdram_ready` is 0 to the host; after it reaches `DONE` it never requests
  again until `reset_sys`, and the two rules above apply unchanged.

### Status bytes

`$A000`:

| Bit | Name | Meaning |
|---|---|---|
| 7 | `copy_busy` | A window fill or swap is in progress |
| 6 | `window_ready` | The upper half holds bank `bank` completely; cleared by a bank commit, set when its fill completes |
| 5 | `sdram_ready` | The SDRAM controller's `initialized` and the [boot copier](../storage/MAS_flash_library.md#boot-copier) not in `CHECK` or `COPY` |
| 4 | `key1_pending` | KEY1 has been held past the debounce threshold and the return is waiting for `copy_busy` to fall (see [KEY1](#key1-return)) |
| 3 | `flash_boot` | This power-up's library was copied from flash: set on the edge the [boot copier](../storage/MAS_flash_library.md#boot-copier) leaves `COPY`, cleared only by `reset_sys` |
| 2:0 | 0 | Reserved |

`$A002` result codes: `0` `NONE` (no swap since global reset), `1` `OK`,
`2` `INVALID_SLOT`, `3` `CRC_MISMATCH`, `4` `NOT_READY` (select or bank commit
while `sdram_ready` was 0). The code changes on exactly these events: a swap
ends (`OK` or `CRC_MISMATCH`), a select is refused in step 1
(`INVALID_SLOT`), or a select or bank commit is refused because
`sdram_ready` was 0 (`NOT_READY`). A completed fill and an ignored commit
during `copy_busy` leave it unchanged. `$A003` is written with `data` on
every select commit with `data` in 0-16, including refused ones, so the menu
can pair a result with the index that produced it.

### Boot source

Two sources fill SDRAM; both leave the CPU-visible rules above unchanged.

Host load (phase 1): after configuration the host loads the library over
UART with [`host library load`](../../../tools/n2m/host/SPEC.md#commands):
images to slots 0..N-1, the `--menu` image to index 16 and the catalogue
through the [host SDRAM line commands](#host-interaction), each slot read back
and compared by CRC32 with its catalogue entry, the catalogue compared byte for
byte; a mismatch is reported by slot and fails the command. `host library
status` reads the catalogue as stored (and `LIBRARY_STATUS` once it exists).
Then the host loads the menu into the ROM store with the existing
`LOAD_BEGIN`/`LOAD_WRITE`/`LOAD_END` sequence using profile `LOADER_ID`, then
`RUN`. From then on the player uses only the board.
A power cycle or global reset requires the host load again unless the flash
library is present.

Flash boot (phase 2): the [flash library](../storage/MAS_flash_library.md)
holds the 17 images and the catalogue in the MAX 10 internal flash. Its boot
copier fills SDRAM after the controller's `initialized`, then requests a
select of slot 16 through the [copy engine](#copy-engine-and-rom-store-port-ownership)
exactly as [KEY1 return](#key1-return) does, so the menu runs without a host.
While the copier runs, `sdram_ready` is 0 and the endpoint reports `LOADING`;
the [host interaction](#host-interaction) rules bound the host's wait. A host
load afterwards overwrites SDRAM only; flash is never written by the console.
An erased flash skips the copier and leaves phase 1 behaviour.

### Core reset sequencing and image validity

The engine does not drive `pause_request` or `core_reset` itself. It issues
requests to [`n2m_uart_core_control`](../uart/MAS_uart.md#ordered-endpoint-composition)
through a second request client, and that owner serializes them with host
commands using its existing `IDLE`/`RESET_WAIT`/`RESET_ASSERT`/`INIT_WAIT`
states. The existing invariants hold unchanged: `core_reset` only while
`paused` and not on a tick; `INIT_WAIT` frozen; every reset increments the
epoch and clears the dot and retirement counters. `image_valid` and `PROFILE`
are owned by the endpoint's command owner today; this contract adds the
engine as a second writer with the same rules: cleared before any ROM byte
changes, set only after the full CRC check. The engine does not use the UART
presence bitmap: its validity comes from the CRC over the bytes it wrote, and
`LOAD_BEGIN`/`LOAD_END` semantics are unchanged because every host session
still starts with its own presence sweep.

After a swap into a game, `PROFILE == DIRECT_ID` and the console is
indistinguishable from a host `LOAD_BEGIN`/`LOAD_END`/`RESET`/`RUN` of the same
32768 bytes: the direct profile's ROM reads, ignored ROM writes, `$FF`
absent-cartridge reads and disabled boot mapping apply, and none of the
loader registers are decoded. The [game specification](../../sw/springtrail/SPEC.md)
and every existing game fixture remain valid without change. The endpoint's
`RETIRE`, `DOT`, epoch and snapshot behavior are those of a normal reset.

### KEY1 return

DE10-Lite `KEY1` (`PIN_A7`, active low, 3.3 V Schmitt trigger, from the same
pin data as `KEY0`) is the return-to-menu button. Hardware detects it; no game
cooperation is required and the game sees nothing until it is reset.

- Synchronize the pin through two `clk_sys` flops, then debounce: the level
  must be stable for 125,000 edges (5 ms) before the debounced level changes,
  the same figure the [board controls](../../fpga-controls.md) use.
- A hold counter runs while the debounced level is pressed. At 12,500,000
  edges (0.5 s) it raises one `key1_return` event and stops; a longer hold
  raises nothing more. Release clears the counter; the next press starts from
  zero. A press shorter than 0.5 s has no effect.
- `key1_return` performs the swap of image index 16 through the select
  sequence above, with the same bounds and results, in every profile (in the
  menu it restarts the menu). If `copy_busy` is set when the event arrives,
  `key1_pending` is set and the swap starts when `copy_busy` falls; a second
  event while pending is dropped.
- If the endpoint is in a host load session, `key1_return` is dropped and
  `key1_pending` is not set: the host owns the console.
- Global reset (`KEY0`) clears the synchronizer, debounce and hold state.

Testbenches use the model-independent timing above: a 0.49 s press must not
return, a 0.51 s press must; a 4 ms glitch must not change the debounced level.

### Host interaction

The host remains able to load one image directly and to drive every existing
command. Rules, in priority order:

1. A host load session (`LOAD_BEGIN` accepted until `LOAD_END` completes)
   excludes the engine: select and bank commits cannot happen (the core is
   paused with an invalid image) and `key1_return` is dropped.
2. While `copy_busy` for a swap, the endpoint reports `STATE == LOADING`. Host
   commands whose precondition is `not loading` or `paused valid image`
   return `BAD_STATE` as today. `LOAD_BEGIN` (precondition `any`) also returns
   `BAD_STATE` while `copy_busy`; the host retries after at most 3.2 ms.
   `LOAD_WRITE`/`LOAD_END` return `BAD_STATE` because no host session is open.
   The [boot copier](../storage/MAS_flash_library.md#precedence-over-host-loads)
   reports the same `LOADING` while it fills SDRAM after a power-up; there
   the host retries after at most 32 ms, the copier's whole-boot bound.
3. While `copy_busy` for a window fill, the core runs and the endpoint reports
   `RUNNING`; every host command keeps its normal behavior. A `LOAD_BEGIN`
   during a fill waits for the fill to finish (at most 1.6 ms) before it pauses
   the core, so the fill never writes into a host session.
4. Host SDRAM line commands in the generated command table (the SDRAM
   bring-up slice adds them; the loader slice adds the arbiter): `SDRAM_WRITE` (26-bit line-aligned device address plus 16
   bytes; response empty) and `SDRAM_READ` (device address plus a line count
   1-15; response the bytes). Both require `sdram_ready` and a line-aligned
   address, else `BAD_VALUE`; both are accepted in every endpoint state and
   complete after the line transfers, at most 23 edges per line plus swap
   waiting, so the host client's existing timeout covers them.
5. The host reads this owner through two new read-only host registers,
   `LIBRARY_STATUS` (the `$A000` byte in bits 7:0, `$A002` in 15:8, `$A003`
   in 23:16, `bank` in 29:24) and `LIBRARY_KEY1` (hold counter in edges),
   and may trigger the menu return itself with a whitelisted
   `WRITE_HOST(LIBRARY_CONTROL)` write of value 1, which behaves exactly like
   `key1_return`. `WRITE_HOST` keeps its existing `not LOADING`
   precondition, so this write is accepted in `PAUSED` and `RUNNING` only;
   after a `CRC_MISMATCH` the endpoint is `LOADING` and the host recovers
   with `LOAD_BEGIN`, not with this write. Exact addresses and command codes
   belong to `cfg/interfaces.json`; the names here are the contract.

## Edge cases

In priority order:

1. `reset_sys`: every register and counter above returns to its reset value;
   `PROFILE` 0, `image_valid` 0, `bank` 0, `$A002` `NONE`, `$A003` `$FF`,
   `flash_boot` 0. SDRAM contents are lost; the
   [boot copier](../storage/MAS_flash_library.md#boot-copier) reloads them
   from flash when the flash library is present, otherwise the host reload
   is the fallback.
2. Select and bank commits on the same edge are impossible (one CPU commit per
   edge). A select commit while a fill is in progress is ignored; the fill
   completes normally.
3. Select of index 16 from the menu: a legal restart of the menu.
4. Catalogue entry valid but SDRAM contents wrong: the CRC step catches it;
   result `CRC_MISMATCH`; the console is paused with no valid image; the host
   sees `LOADING` and can `LOAD_BEGIN` immediately (no `copy_busy`), or the
   physical KEY1 can try the menu again. `WRITE_HOST(LIBRARY_CONTROL)` is
   refused in `LOADING`, so it cannot be the recovery path.
5. `key1_return` during a swap started by select: `key1_pending`, then the
   menu swap runs after the game swap completes; the player sees the game for
   at most 3.2 ms plus its own boot.
6. Host `RESET` while a game runs after a swap: identical to today; the ROM
   store still holds the game.
7. Host `LOAD_BEGIN` with `profile == LOADER_ID` and a 32768-byte image: the
   loader profile registers become live after `LOAD_END`; the upper half holds
   the image's own bytes until the first bank commit.

## Verification

Simulation runs under Verilator on WSL with the real memory owner, core
control owner, [SDRAM controller and device model](../storage/MAS_sdram.md#verification),
and a CPU bus driver or the real CPU. Fixtures, each within the
[wall budget](../../../tools/n2m/SPEC.md#test-wall-budget):

| Fixture | Checks |
|---|---|
| `loader-map` | All 65,536 addresses in `LOADER_ID`: reads and writes route per the [address map](#address-map-in-the-loader-profile); `$FF` window reads while busy; in `DIRECT_ID` the loader registers are absent and the direct rules hold byte for byte |
| `loader-window` | Bank commits 0, 1, 33, 34, 63; upper half equals the SDRAM bank after `window_busy` falls; 40,000-edge bound; ignored commit during busy; `window_ready` and `$A001` |
| `loader-swap` | Select 0, 15 and 16 with a valid catalogue: pause, `image_valid` low before the first ROM write, CRC, `PROFILE`, epoch + 1, running without host `RUN`; 80,000-edge bound; the ROM store equals the image byte for byte |
| `loader-swap-fault` | Invalid entry, wrong length, bad profile, CRC mismatch: exact result codes, no ROM byte changed for refused selects, paused with `image_valid` 0 for the mismatch |
| `loader-key1` | 4 ms glitch, 0.49 s and 0.51 s presses, hold through the swap, press during a swap (`key1_pending`), press in a host session (dropped), release and re-press |
| `loader-host` | `LOAD_BEGIN` during swap returns `BAD_STATE`; during fill it waits; `SDRAM_WRITE`/`SDRAM_READ` round trips; `LIBRARY_STATUS`; `WRITE_HOST(LIBRARY_CONTROL)` return; a direct host load of a game after a swap behaves as today |

Named assertions the owner carries:

| Assertion | Rule |
|---|---|
| `LOADER_PORT_EXCLUSIVE` | The engine and the UART load owner never both own the ROM host write port |
| `LOADER_IMAGE_INVALID_BEFORE_WRITE` | An engine write into the ROM store during a swap implies `image_valid == 0` |
| `LOADER_VALID_IMPLIES_CRC` | `image_valid` rising from an engine swap implies the CRC compared equal on that edge |
| `LOADER_SWAP_PAUSED` | Engine ROM writes with a 32 KiB job imply `paused` |
| `LOADER_FILL_UPPER_ONLY` | Engine writes during a fill have offset bit 14 set |
| `LOADER_FILL_HOST_PORT` | Every engine write reaches the ROM store through its host port (port A) and never coincides with a UART load owner write |
| `LOADER_REGS_ONLY_IN_PROFILE` | A bank or select register effect implies `PROFILE == LOADER_ID` |
| `LOADER_SWAP_BOUND` | `copy_busy` for a swap falls within 80,000 edges of rising |
| `LOADER_FILL_BOUND` | `copy_busy` for a fill falls within 40,000 edges of rising |
| `LOADER_KEY1_THRESHOLD` | `key1_return` implies the debounced press has lasted exactly 12,500,000 edges |
| `LOADER_ONE_CORE_CLIENT` | The core control owner never accepts a host command and an engine request on the same edge |

The Questa compile-only gate, the fit and the board sessions follow the
[charter workflow](../../project-charter.md#game-library). Board proof for
this owner: after a host library load, the UART log shows the swap epoch
change and `LIBRARY_STATUS` for a selection made through the physical joypad,
the game's frame hashes match the direct-load run of the same image, and a
KEY1 hold returns to the menu; the owner confirms the picture when present.

## References

- [SDRAM storage and timing](../storage/MAS_sdram.md): line interface, latency bounds, layout and catalogue format.
- [Memory owner](../memory/MAS_memory.md): ROM store, host ROM port, decoder and one-edge service.
- [UART endpoint](../uart/MAS_uart.md) and [shared interfaces](../interfaces/MAS_interfaces.md): load session, `image_valid`, `PROFILE`, `STATE`, command preconditions and status codes.
- [Clock, reset and CDC contract](../../clocks-resets-cdc.md#reset-and-run-control): host core reset semantics this owner reuses.
- [Board controls](../../fpga-controls.md) and [board bring-up](../../board-bring-up.md): KEY0, debounce figure and pin conventions.
- [Charter](../../project-charter.md#game-library): the decisions this page implements.
