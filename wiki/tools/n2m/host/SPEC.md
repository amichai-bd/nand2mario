# Host commands

Implemented by [tools/n2m/host](../../../../tools/n2m/host/client.py), dispatched
through `python tools/build.py host`. The [PRD](PRD.md) owns requirements.
The [interface MAS](../../../src/rtl/interfaces/MAS_interfaces.md) and generated
exports own all wire, register, profile and frame values.

The [paused Springtrail acquisition](../../../src/dv/springtrail/SPEC.md#paused-frame-acquisition)
reuses Client/session and full immutable frame readback. Its DV contract owns
the fixed reference mapping, complete batch evidence and fail-closed continuation;
ordinary host commands and recovery semantics do not change.

The focused `python tools/stackdrop_player.py` entrypoint uses this same Client,
package validator and durable session for the
[frozen Stackdrop comparison](../../../src/sw/stackdrop/SPEC.md#pixel-player-comparison).
Its explicit private setup/state files bind the verified device, board build,
prior paused dots, frame identity and durable sequence. Run baseline once, then
strategy once; an attempted or uncertain run cannot be silently restarted.
Each invocation uses the existing300-second supervisor and canonical machine
lock. Pixel observations and packet journals are retained under its build tag.

## Commands

Every operation accepts `--tag`, `--json` and the doctor's `--uart-port`,
`--uart-vid`, `--uart-pid`, `--uart-identity` selectors. Selectors combine; exactly
one healthy Windows PnP serial device must match. No selection fails. OS identity
is not device authentication or proof of correct wiring.

| Command | Result |
|---|---|
| `host status` | ABI/build identity and single-word state, image-valid, profile and input registers. No incoherent live split counters. |
| `host io --samples <n>` | Repeated live LCD triple and dot readings plus one pass over the frozen DMG I/O set. Reads only; the endpoint is never paused or stepped. Samples land in `io_samples.json`. |
| `host load --package <result.json>` | Validated immutable software attempt, load begin/write/end, complete byte-for-byte readback, valid/paused/profile checks. Does not run the ROM. |
| `host load --external <name>` | Same transmission and verification from a pinned external image fetched at run time. Exactly one of `--package` or `--external` is accepted. |
| `host reset` | Generated core RESET, acknowledged after initialization. |
| `host run` | Resume through generated RUN. |
| `host halt` | Pause through HALT; return completed dots. |
| `host step --dots <budget>` | One instruction with generated budget bounds; STEP_LIMIT is a known failure with consumed time retained. |
| `host run-dots --dots <count>` | Exact bounded real-dot execution; return completed dot, executed count and COUNT/STOPPED reason. |
| `host input --mask <integer>` | Replace the complete active-high eight-button mask, preserving simultaneous/opposite states. Decimal or prefixed hexadecimal is accepted. |
| `host keyboard --expected-build-id <32hex>` | Focused Windows classic-console key down/up to complete INPUT masks; see keyboard behavior below. |
| `host write --address <integer> --value <integer>` | Write the generated INPUT mask or INPUT_SOURCE selector; reject read-only/unknown addresses and reserved value bits before opening the port. |
| `host snapshot` | One SNAPSHOT followed by all READ_FRAME chunks; retain metadata and packed shades. No new snapshot during readback. |
| `host peek --store <wram\|hram\|vram\|oam\|wave>` | Read one whole non-ROM store from a paused board in PEEK chunks; retain its size and hash. Read-only; the core must be paused. Independent of snapshot readback. |
| `host crc-proof --expected-build-id <32hex>` | Fixed bad-CRC PING diagnostic on an already certain, reviewed endpoint. Requires the physical verification workflow below. |

`host peek` reads DMG memory off a paused board so a hardware-only defect can
be inspected without building a simulation. For the original game,
[observing and playing Springtrail from game state](../../host-play/springtrail-state.md)
is the practical how-to built on it. One rule covers all five stores:
**host reads use port B, are read-only, and are rejected unless the core is
paused.** The [memory MAS](../../../src/rtl/memory/MAS_memory.md) owns why that
is safe and why read-only is structural; the
[UART MAS](../../../src/rtl/uart/MAS_uart.md) owns the opcode and payload.
An unknown store name fails before the serial port opens. A peek that arrives
while an OAM port A sequence is still draining past the pause is held for those
few cycles rather than refused, so the host sees only its ordinary reply. ROM is not a peek
target and is unchanged: `host load` still reads it back through READ_ROM.

`Client.peek(store)` reads a whole store in wire chunks;
`Client.peek_range(store, offset, count)` reads one bounded range, checked
against that store before anything is sent. Both use the same command and the
same paused, read-only rule; the range form is what the
[Springtrail state reconstruction](../../host-play/SPEC.md#springtrail-state-reconstruction)
uses to read a few dozen bytes instead of the whole store.

Peek and snapshot readback are independent. A peek neither consumes nor
disturbs a held snapshot, and a held snapshot does not block a peek, so the two
may be interleaved; this is the deliberate opposite of `host snapshot`'s own
"no new snapshot during readback" rule, because peek and READ_FRAME address
disjoint storage while a second capture would overwrite the bank being read.

`Client.write_host(address, value)` uses the same whitelist.
`Client.select_input_source(source)` selects UART or PHYSICAL through that write.
Existing `Client.read_host` reads host, physical, source and effective observations;
legacy status/INPUT retain their original host-mask meaning. See the
[shared input owner](../../../src/rtl/input/MAS_input.md) for reset and authority.

Before any operation the host checks PING and host ABI, then records the stable
128-bit build ID. It sends no product operation after an ABI mismatch. The build
ID is evidence, not authentication. An all-zero ID fails before any product
command. The shared contract's unidentified simulation-fixture exception is
not exposed by the physical host CLI.

Load accepts a successful immutable
`workdir/builds/<tag>/sw/build/<target>/runs/<attempt>/result.json`, not a loose
ROM or mutable stage result. Validate attempt/profile, current interface input
hashes and every inventoried artifact within that attempt. Read the image once,
check its hash, exact size and strict owned header/checksums using the packager
validator, then keep immutable bytes for transmission and full comparison.
No expected byte values are logged on mismatch. Each write leaves space for its
generated offset record; every byte is read back after LOAD_END before success.

`--external <name>` selects an `external_roms.images` entry of the
[dependency manifest](../../../../tools/n2m/dependencies.json) instead. The pin
records the https source URL, SHA-256, size and license, and optional upstream
notices with their own URL, hash and size. The image is fetched at run time into
ignored `workdir/private/external-roms/<name>/`; no image bytes enter the
repository. Size is checked first, then SHA-256, on the downloaded bytes before
the cache is written and again on every cached read. An unknown pin, a missing
field, a non-https pinned URL, a redirect that lands off https, a size differing
from the direct-profile image size, or any hash mismatch fails before the serial
port opens, so no partial image is written. Verified bytes replace the cache
file in one step, so an interrupted run leaves no truncated cache. Everything
after that point, including readback and the valid, paused and profile checks,
is identical for both sources. Each pinned image is a reviewed freely licensed
release recorded under the [provenance policy](../../provenance.md); the
manifest names the title, author, release and licence text beside the pin.
The [Libbet play record](../../../../src/dv/libbet/README.md) drives the pinned
image through these commands on the board and retains its frames.

## DMG I/O register view

The host register map exposes the DMG's own I/O registers so a running board can
be observed directly. This table is frozen: it names every exposed register, the
host address, what the endpoint samples, and how that differs from a CPU read of
the same DMG address. The [generated tables](../../../cfg/interfaces.md#host-reg)
own the literal address values; this section owns the read semantics.

Reads are live. Every entry is a combinational view of a `clk_sys` flop reached
through the existing `READ_HOST` decode, so a read is allowed in `RUNNING` as
well as `PAUSED`, and nothing is cleared, latched or advanced by reading. No
pause, opcode, RAM port or chunked payload is involved. The map stays read-only:
`host write` still rejects every address outside the generated write mask.

One rule covers the whole table. The host observes the committed storage of the
owning module, zero-extended into the 32-bit word. It does not reproduce the
bit-stuffing a CPU read performs on unimplemented bits, because that stuffing
hides which bits the endpoint actually holds. Where a CPU read differs, the
difference column states it.

| Register | Host address | Endpoint value | Difference from a CPU read | Evidence |
|---|---|---|---|---|
| LCDC | `HOST_REG_IO_LCDC` | `lcdc` committed byte | none | [Pan Docs LCDC](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/LCDC.md); [MAS_ppu](../../../src/rtl/ppu/MAS_ppu.md) |
| STAT | `HOST_REG_IO_STAT` | `{1'b0, stat_enable, coincidence, mode}` | CPU read sets bit 7; the host leaves it zero | [Pan Docs STAT](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/STAT.md); [readable STAT rules](../../../src/rtl/ppu/MAS_ppu.md#stat-write-timing) |
| SCY | `HOST_REG_IO_SCY` | `scy` committed byte | none | [Pan Docs Scrolling](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Scrolling.md) |
| SCX | `HOST_REG_IO_SCX` | `scx` committed byte | none | [Pan Docs Scrolling](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Scrolling.md) |
| LY | `HOST_REG_IO_LY` | readable LY, the same value the PPU presents to the CPU | none; as for a CPU read, LY wraps to 0 early during line 153, so a sample can report LY 0 while STAT still reports VBlank | [Pan Docs STAT](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/STAT.md); [LY153 comparison](../../../src/rtl/ppu/MAS_ppu.md) |
| LYC | `HOST_REG_IO_LYC` | `lyc` committed byte | none | [Pan Docs STAT](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/STAT.md) |
| BGP | `HOST_REG_IO_BGP` | `bgp` committed byte | none; the renderer's one-dot old-or-new conflict value is not exposed | [Pan Docs Palettes](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Palettes.md); [MAS_ppu](../../../src/rtl/ppu/MAS_ppu.md) |
| OBP0 | `HOST_REG_IO_OBP0` | `obp0` committed byte | as BGP | [Pan Docs Palettes](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Palettes.md) |
| OBP1 | `HOST_REG_IO_OBP1` | `obp1` committed byte | as BGP | [Pan Docs Palettes](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Palettes.md) |
| WY | `HOST_REG_IO_WY` | `wy` committed byte | none | [Pan Docs Window](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Window.md) |
| WX | `HOST_REG_IO_WX` | `wx` committed byte | none | [Pan Docs Window](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Window.md) |
| DIV | `HOST_REG_IO_DIV` | upper byte of the 16-bit internal divider | none; the low byte stays internal, and reading never resets the divider as a CPU write to FF04 does | [Pan Docs timer registers](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Timer_and_Divider_Registers.md); [MAS_timer](../../../src/rtl/timer/MAS_timer.md) |
| TIMA | `HOST_REG_IO_TIMA` | `tima` committed byte | none; the reload delay and hold are internal and are not disturbed | [Pan Docs obscure timer behavior](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Timer_Obscure_Behaviour.md) |
| TMA | `HOST_REG_IO_TMA` | `tma` committed byte | none | [Pan Docs timer registers](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Timer_and_Divider_Registers.md) |
| TAC | `HOST_REG_IO_TAC` | committed 3-bit control in bits 2:0 | CPU read sets bits 7:3; the host leaves them zero | [Pan Docs timer registers](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Timer_and_Divider_Registers.md) |
| IF | `HOST_REG_IO_IF` | committed 5-bit request flags in bits 4:0 | CPU read sets bits 7:5; the host leaves them zero, and the host shows the committed flops, not the same-edge combinational observation the CPU uses | [Pan Docs Interrupts](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Interrupts.md); [interrupt sources](../../../src/rtl/interrupts/references.md) |
| IE | `HOST_REG_IO_IE` | `ie_stored` committed byte, all eight bits | none; the upper three bits are storage on DMG and are reported as stored | [Pan Docs Interrupts](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Interrupts.md); [MAS_interrupts](../../../src/rtl/interrupts/MAS_interrupts.md) |
| LCD status triple | `HOST_REG_IO_LCD_STATUS` | `{8'b0, LCDC, STAT, LY}`, the three bytes above sampled on one edge | same per byte | this section |

### Why the LCD status triple exists

A scanline is 456 dots; one `READ_HOST` round trip costs milliseconds. Reading
LY and STAT as separate commands therefore pairs values taken from different
frames' worth of emulated time, and a pair like LY 50 with VBlank mode looks
like a defect that is not there. The triple samples all three bytes on one
endpoint edge, so a board capture can check the mode progression across a frame
against a coherent pair. It is the one register in this table that has no single
DMG address behind it; the three bytes it carries are the three rows above.

During global or core reset each owner drives its documented reset fill, and the
host view carries that same value rather than a separate default.

Audio channel registers, JOYP, DMA and the boot-disable latch are not exposed.
They are not part of this frozen set and require their own evidence before any
are added.

## Transport and recovery

### Focused keyboard

`host keyboard` supports a local Windows10/11 classic console with native input,
a visible console window and foreground ownership. Windows Terminal/ConPTY,
WSL/SSH and redirected input are unsupported and rejected before serial open.
To open the supported console without changing defaults, use Windows Run with
`conhost.exe cmd.exe`, change to the repository, then invoke:

```text
python tools/build.py host keyboard --uart-port <verified-port> --expected-build-id <reviewed-wire-id> --tag <tag>
```

Release mapped keys before invocation. Arrows map to directions, Z to A, X to B,
right Shift to Select and Enter to Start. Down adds a button; up removes it.
Each changed union is one ordinary INPUT with its acknowledged dot retained.
Repeated downs are ignored; chords/opposite directions are preserved. Unmapped
characters are neither sent nor logged. Ctrl/Alt-modified downs are ignored;
releases still clear held keys. Escape, Ctrl+C and Windows keys exit.
Pre-capture queued events are discarded, and a mapped key observed held in that
queue is ignored until its release. Foreground ownership is checked again at
serial open. This observes console events, not unreported physical key state.

Require a certain durable session, expected build/ABI, valid image, UART source
and initial host/effective0. No implicit source selection, RUN/HALT, load or reset
occurs. Existing machine/device locks serialize the whole session. `--json` and
`--endpoint-restarted` are rejected for this interactive operation; tagged
result/transaction files retain its outcome.

Native events and foreground ownership are polled with20ms idle waits; an
outstanding UART exchange may delay observation until its existing deadline.
Recorded focus-loss events also cause exit if focus returned before the next
poll. Focus loss exits without rearming or consuming queued gameplay keys. Ordinary
exit/read failure sends INPUT0 once if the Client is certain, and requires an
acknowledgement before claiming release. Ambiguous transmission/completion
retains pending and sends nothing further. Console mode is restored on exit;
a restoration failure reports failure without inventing wire pending. Killing
the process or unplugging the adapter cannot guarantee a released mask.

The implementation uses native console events, not global key-state polling or
hooks. [Windows key records](https://learn.microsoft.com/en-us/windows/console/key-event-record-str)
carry down/up and repeats. A
[pseudoconsole window](https://learn.microsoft.com/en-us/windows/console/getconsolewindow)
is not its displayed terminal, so it cannot satisfy this foreground check.
Native injected-event tests prove the event path; actual manual keyboard/VGA
release acceptance stays in the charter's
[remote acceptance](../../../src/project-charter.md#remote-acceptance) split,
whose monitor entry is [#417](https://github.com/amichai-bd/nand2mario/issues/417).

Discovery reuses the doctor without running its licensed probes. The optional
[pinned serial backend](../../../../tools/n2m/host/THIRD_PARTY.md) opens only the
selected OS port, configured to the generated baud and 8N1 without flow control.
DTR/RTS are set inactive before open; driver-level glitches cannot be ruled out,
so verified wiring and the physical workflow still apply.

The serial device is configured once with nonblocking reads. A transport wrapper
waits for received bytes with a monotonic deadline and sleeps at most one
millisecond between empty reads. Client timeout updates change that local wait,
not the device configuration. This avoids pyserial 3.5 on Windows reapplying
line settings while a packet is transmitting. Packet writes remain whole and
unpadded; there is no inter-byte pacing, flush loop or automatic replay.

Only one request is outstanding. Replies must match generated version, response
kind, sequence, command, status and exact payload shape/length, with valid COBS
and CRC. Empty delimiters are ignored within a bounded overall response timeout.
Partial writes, timeout, malformed or mismatched replies make completion
uncertain. The host stops immediately without retry, reset, reload or another
request. A valid endpoint error is a known failure, not an uncertain reply.

Each selected PnP identity has a repository-shared lock and sequence journal in
ignored `workdir/host-sessions/`, shared across build tags and linked worktrees.
Reserve the next modulo-width sequence and mark pending before transmission;
clear pending only after a valid reply. This retains uncertainty after crashes
or separate CLI invocations. A subsequent command fails before opening while
pending. A stale lock requires confirming its recorded process has stopped;
commands never delete it automatically.

`--endpoint-restarted` is an explicit operator statement that a separately
completed endpoint global reset ended the uncertain session. It clears pending
under the exclusive lock while preserving the increasing sequence. It never
sends reset or replays the previous request. Core RESET does not meet this
condition because it preserves the endpoint retry cache. An immediate retry
within an uninterrupted session is not exposed by this initial host UI.

## Evidence and tests

The CRC proof requires a matching reviewed wire build ID, PAUSED state, UART
source and zero requested/effective input. It rejects `--endpoint-restarted`.
After the prerequisites, it reserves a token and sends an empty PING with one
CRC bit flipped before COBS encoding. Any received byte in the generated
two-second response window fails. A fresh-token normal PING must return ABI1;
subsequent state and stable paused dot/retirement reads must match the baseline.
The diagnostic keeps its durable session pending through all recovery reads and
clears it only after the entire proof succeeds. Failures stop without retry or
state-changing commands. Ordinary Client timeout handling is unchanged.
Run physical proof under the existing 60-second whole-process supervisor,
including its standard cleanup reserve, with verified setup and exclusive access.
This observes silence and recovery, not an internal discard counter or monitor
output; the remaining [board criteria](../../../src/board-bring-up.md) remain
separate.

Every invocation is fresh, never cached. Unique attempt artifacts live under
`workdir/builds/<tag>/host/<action>/<attempt>/`: discovery, device identity,
transaction journal, result and optional `frame.2bpp` or `<store>.bin`. Journals
contain command, sequence, byte length/hash, response status and decoded non-ROM
metadata, never raw ROM request/readback bytes. Snapshot shades and peeked store
bytes remain ignored private artifacts.
The builder retains commit/dirty fingerprint, requested command and artifact
hashes; failures retain their reason and transaction prefix. Build and device
paths/identities remain local and must not be pasted into public documentation.

The DMG I/O view is checked at three levels. `uart-validation` sweeps every
literal host address, the unaligned bytes between them and the unassigned words
above the map. `io-peek` runs two identical copies of every owning module on one
stimulus, peeks only one, and requires their committed state, interrupt flags and
timer progression to stay identical; `io-peek-disturb` routes the peek through
copy A's DMG port instead and must be caught. `python-v05-iopeek` samples the
registers over real UART pins while the composed core runs, and checks the
endpoint stayed RUNNING, that dots and the divider advanced, that reserved bits
stayed clear and that the mode matched the scanline; `python-v05-iopeek-fault`
breaks the LY route and must fail. Whole-frame coverage including VBlank belongs
to the board session, not to simulation.

[Fake endpoint tests](../../../../tools/n2m/tests/test_host.py) drive encoded
packets, verify all load/readback chunks including the final byte, all input
masks, control transitions, immutable snapshot chunks, malformed replies,
uncertain persistence and device failures before open. They run through
`python tools/build.py check --tag <tag> --json`. Physical evidence is separate
and is not claimed by these tests.
