# Executable interface contracts

The [source](../../../../cfg/interfaces.json) owns numeric Game Boy, host, wire,
direct-entry and trace values. Its [generated tables](../../../cfg/interfaces.md)
are the human-readable view. The closed schema and semantic validator live in
[the generator](../../../../tools/n2m/interfaces.py); the source's schema version is
independent of the packet, host-register and trace ABI versions.

This delivers [#30](https://github.com/amichai-bd/nand2mario/issues/30)'s data,
generation and byte-codec checks. CPU/register behavior, transport/controller
RTL and differential adapters are future implementations. The
[host loader](../../../tools/n2m/host/SPEC.md) implements the Python transport and
commands with fake-endpoint evidence; physical/RTL acceptance remains separate. Delivery
is tracked by [UART endpoint #91](https://github.com/amichai-bd/nand2mario/issues/91),
[host loader #92](https://github.com/amichai-bd/nand2mario/issues/92),
[host snapshots #93](https://github.com/amichai-bd/nand2mario/issues/93), and
[verification baseline #31](https://github.com/amichai-bd/nand2mario/issues/31).
No device is opened by the pure codecs. The [charter](../../project-charter.md) still requires full
load/readback, all eight buttons and a simultaneous pair, every retirement,
and independent pixel comparison. Codec tests are not those acceptance runs.

## Authority and generation

This shared interface contract governs RTL, host software, and verification
consumers of the schema. The [generator specification](../../../tools/n2m/SPEC.md#interface-generation)
owns schema validation, regeneration, export provenance, and consumer imports.
The generated tables retain schema ownership; do not hand-copy their constants.

## Address spaces

Game Boy addresses denote bytes on the original 16-bit CPU bus; data is eight
bits. Host addresses denote aligned 32-bit control/status words on a
separate 32-bit bus entirely above the CPU range. No CPU transaction decodes
host registers. `READ_HOST` and `WRITE_HOST` carry host addresses.
Unknown/unaligned host addresses fail without aliasing or truncation.

ROM and snapshot commands carry byte offsets into named storage, not either
address bus. The direct profile maps each CPU ROM address to the same file
offset. CPU writes to ROM never load bytes. Each direct-profile ROM bank is a
section boundary; each vector reserves its generated slot size, and the
packager reserves the generated header range. Linkable RAM is WRAM and HRAM;
VRAM/OAM are explicit program-visible graphics storage, not general allocation
regions. Echo, unusable, I/O and absent cartridge RAM are never linker RAM.
The LDH view intentionally overlaps I/O, HRAM and IE; views are not new decoders.

Register constants identify addresses only. They do not define read masks,
write effects, bus blocking, timer edges or undocumented behavior. The direct
profile has no mapper or cartridge RAM. Other profiles require new reviewed
contracts before loading. The planned original v0.9 platformer uses this same
profile; loading and execution preserve the exact built image bytes.

## Direct entry and reset

`dmg-direct-v1` is the project-defined entry state for original v0.5 software
and the planned original platformer,
not a claim about DMG power-on or Nintendo post-boot state. The generated
profile sets PC/SP, all eight byte registers, IME and pending-EI/HALT/STOP/bug
state. The cartridge entry stub executes first. There is no boot ROM mapping.
Reset initializes internal WRAM, HRAM, VRAM, OAM and wave RAM to `RAM_FILL`;
the echo range aliases WRAM and has no separate backing store. ROM is retained
on RESET. There is no cartridge RAM to clear in this profile.

Writable peripheral storage and internal execution state initialize to
`PERIPHERAL_FILL`, except the generated JOYP select value. This includes timer
divider/counters/reload pipeline, serial transfer state, interrupt requests,
DMA progress, LCD/PPU timing/FIFO/window state, and inactive audio channel state.
LCD and audio are off, all buttons released, boot mapping disabled, dot phase,
dot count, retirement count and source-frame counter zero. Hardware read masks
still apply; zero storage is not a promise that every I/O read returns zero.
The initial LY/LYC comparison must be derived normally from initialized state.
Profile initialization does not weaken later subsystem runtime semantics.

RAM clearing may take many system cycles. A reset completes only after all
specified storage and state are initialized. Emulated time is frozen until
completion; the result is PAUSED. RUN and STEP require a valid loaded image.
Global reset starts with no valid image/profile, empty transport state and no
host snapshot. Only LOAD_BEGIN is needed to establish the direct profile.
RESET with no valid image returns BAD_STATE. RESET while LOADING also fails;
LOAD_BEGIN restarts an interrupted load, including while already LOADING.

As required by [timing/reset/CDC](../../clocks-resets-cdc.md), core reset and loading
keep UART, PLL, VGA and frame ownership handshakes alive. Clear partial writer
progress, but never mutate an offered/displayed frame or clear one side of a
mailbox. Keep the last displayed image until a new complete frame replaces it.
Host snapshots survive core reset; new SNAPSHOT requests require a complete
frame in the current epoch. Reset acknowledgement waits for core initialization,
not for a VGA swap or pixel-clock acknowledgement.

## Packet format and transport

UART uses generated baud, eight data bits, no parity, one stop bit, idle high
and no flow control. The decoded packet is `packet_header`, payload, then a
two-byte little-endian CRC-16. All multibyte integers are unsigned little-endian.
CRC-16/CCITT-FALSE covers header and payload: generated polynomial/initial
value, no reflection, xorout zero; `123456789` gives `0x29B1`.

Encode the entire decoded packet using COBS and append a zero delimiter. The
canonical encoder emits a code byte even for a final empty block; decoders may
accept equivalent COBS encodings. A code describes itself plus the following
nonzero bytes; codes below 255 insert a zero between blocks. Delimiters cannot
appear inside an encoded frame. Empty delimiter-only frames are ignored.
The receiver caps decoded payloads at MAX_PAYLOAD and encoded frame storage at
`raw_max + floor(raw_max / 254) + 1`, excluding delimiter, where
`raw_max = PACKET_HEADER_BYTES + MAX_PAYLOAD + 2`. Oversize input is discarded
through the next delimiter. An incomplete frame is discarded after the generated
idle timeout; framing then resumes on the next complete delimited frame.
Malformed COBS, truncation, invalid kind/request status or bad CRC has no effect
and no reply. A valid-CRC unsupported version returns BAD_VERSION in the current
version. Unknown commands return BAD_COMMAND. Other complete malformed requests
return the generated status appropriate to the failed check.

The [pure codecs](../../../../tools/n2m/interface_codec.py) reject malformed byte
records without opening a device. Their decoder raises on unsupported versions;
the future endpoint must map that validated header to the specified error reply.
Request/response payload layouts come from the generated command table. `empty`
is zero bytes; `bytes` is the requested byte count; `offset+bytes` is an offset
record followed by nonempty data. No padding bytes or optional trailing fields.
An error response has no payload, including STEP_LIMIT. Successful replies echo
sequence and command, set response kind and OK, and carry the documented payload.

One request may be outstanding. Commands execute in received order, with reply
only after transition completion. The endpoint retains the last completed
decoded request and response. An identical immediate retry returns that response
without repeating effects; the same sequence with different bytes returns
SEQUENCE and preserves the cache. A different sequence replaces the cache after
completion. There is no durable exactly-once guarantee across global reset or
after an intervening command. The host uses increasing tokens modulo their
width. On timeout it reports uncertain completion and stops; no automatic retry
or reset/reload is allowed. An explicitly chosen immediate retry is safe only
within the same uninterrupted endpoint session. Reset of the emulated core
does not clear this transport cache. Extra requests received while busy are
discarded; the host must recover the outstanding response before proceeding.

## Commands and ordering

### Bounded dot execution

Planned under [#278](https://github.com/amichai-bd/nand2mario/issues/278):
`RUN_DOTS` (command15) carries one little-endian32-bit count from1 through70224.
It requires PAUSED and a valid image. Zero or an excessive count is BAD_VALUE;
wrong length/state uses the existing validation order and has no effects.
RUN, HALT and instruction STEP retain their meanings.

Resume the retained timebase phase and count real `gb_tick` edges, independently
of instruction retirement or CPU HALT. Request pause on the requested final
tick, so no extra tick occurs. Reply after the final tick's ordinary B-edge
settlement, with the timebase paused. The13-byte success payload is completed
dot64, executed count32 and completion reason8, all little-endian. Reason0 means
COUNT: executed equals requested and completed dot equals the initial dot plus
that count modulo2^64. Reason1 means STOPPED: an already STOPped CPU does not
unpause and returns zero/current dot; STOP entered during the operation finishes
at the next natural tick with the actual partial count. Reaching the requested
count on that tick takes precedence over STOPPED. Neither path changes input,
wake state, phase, epoch or reset except for normal execution effects.

STOPPED is a completed operation with an explicit reason, not an exact-count
success. The host must check the reason and count before accepting frame advance.
Malformed requests remain error-status/empty-payload replies. Identical duplicate
tokens return the cached result without executing again; conflicting tokens
return SEQUENCE. Global reset cancels in-flight work/cache as before; loss of a
reply leaves host completion uncertain. RESET cannot interleave with an
outstanding request. With the documented active system clock, the existing
timebase supplies a tick within six edges. Clock loss is not synthesized progress:
the ordinary host timeout leaves uncertainty instead of claiming completion.

Validate payload length, ranges and permitted state before effects; invalid
commands do not partially change state. PING and status reads work in any state.
Host registers are read-only except INPUT and INPUT_SOURCE. `WRITE_HOST` accepts
only these generated addresses and writable bits; all other writes fail before
effects. Its address32/value32 request returns the accepted dot64. Invalid length
precedes BAD_VALUE, which precedes BAD_STATE, including while LOADING.
Legacy INPUT remains the same atomic host-mask operation and readback.
INPUT_SOURCE selects UART (reset default) or PHYSICAL; INPUT_PHYSICAL and
INPUT_EFFECTIVE expose the observed and selected masks. This additive command
retains ABI1; older endpoints reject it without an implicit fallback.
Reserved enum values fail. Profile reads zero before a load
has established it. Multiword live counts require HALT before coherent reads;
snapshot sequence and the 128-bit build identifier are stable. Build ID is a
deterministic build identity supplied by implementation, zero only for explicitly
unidentified simulation fixtures; it is not a device identity/authentication key.

- HALT means host pause, not the CPU HALT opcode. Finish the current emulated
  dot and freeze all emulated state and phase, even mid-instruction. RUN resumes
  that state without catch-up ticks. Idempotent HALT returns the paused dot count.
- STEP requires a budget from one through STEP_MAX_DOTS. Resume at the retained
  phase, execute through the next retired instruction, then pause on its ending
  dot. Interrupt-entry events do not count as instructions. If the CPU is already
  oscillator-STOPped when STEP is accepted, return STEP_LIMIT immediately with
  no payload or delivered dots. Stay host-paused and preserve CPU state, input
  and any pending wake; STEP does not start oscillator restart or consume that
  wake. Otherwise, if no instruction retires before the budget, pause and return
  STEP_LIMIT; consumed time/state is retained, readable through host registers.
  If retirement and budget end coincide, retirement wins. CPU HALT never freezes
  the PPU/timebase. Stepping a partially executed instruction completes that
  instruction; no rewind. A zero/out-of-range budget fails before execution.
- LOAD_BEGIN checks profile, exact size and expected whole-image CRC32 before
  pausing/resetting and invalidating the previous image. It resets a per-byte
  presence bitmap. LOAD_WRITE accepts arbitrary in-range order, overlaps and
  rewrites while LOADING; the most recent byte wins. Never accept ROM writes
  while RUNNING. LOAD_END requires every byte present and matching
  CRC-32/ISO-HDLC (generated reflected polynomial and initial/final XOR;
  Python `zlib.crc32`, `123456789` gives `0xCBF43926`). On failure stay LOADING,
  invalid, and repair/restart explicitly. On success reinitialize direct state,
  mark valid and PAUSED. READ_ROM permits full chunked readback before RUN;
  offsets/counts must fit storage without arithmetic wrap, with count in
  1..MAX_PAYLOAD. During an incomplete load unwritten bytes are unspecified;
  full post-commit readback must equal the original image.
- INPUT replaces all eight host button bits atomically in either source mode.
  Only UART mode selects that mask for JOYP; PHYSICAL mode retains it as host
  shadow readback. While running, apply
  it between completed dots, before the next dot observes JOYP/interrupt edges;
  while paused apply it immediately without advancing time. Return the count
  of already completed dots. CPU HALT/STOP does not discard input. Host bits
  are active-high, while selected JOYP rows expose active-low buttons. Both
  selected rows combine pressed bits; neither selected returns a released low
  nibble. Opposite directions and simultaneous buttons are preserved. Joypad
  interrupt edge behavior belongs to the joypad subsystem contract. Deterministic
  scripts may HALT then INPUT then RUN; acceptance run bounds prohibit
  host pauses except the explicitly approved v0.9 full-frame acquisition. The simulation input driver schedules masks at
  exact dot boundaries on this same input interface without UART timing jitter.

Synchronous priority is core reset, host transition/input latch, then emulated
dot effects. A running command becomes effective after the current dot; do not
drop or repeat it. The wire does not expose arbitrary writes to CPU registers
or RAM. Load and input cannot masquerade as DMG MMIO side effects.

## Immutable frame snapshot

Keep a dedicated system-domain latest-complete-frame store, separate from all
three VGA ownership banks, and a dedicated host snapshot store. The PPU observer
assembles a complete source frame separately before publishing it to that store;
partial frames are never visible. SNAPSHOT copies a published complete frame
into the host store and atomically publishes its epoch, sequence, completion dot and
size only after the copy finishes. Its source is pinned during the copy; source
frames arriving meanwhile may be omitted from this convenience latest-frame
store. Such omission must never stall emulation, change VGA ownership, or drop
the verification observer's every-frame evidence. An implementation can use
double buffers for assembly/latest storage; resource fit remains implementation
evidence, not a claim here.

READ_FRAME reads only the dedicated immutable snapshot. No host command leases,
reads or steals a changing writer bank or the displayed VGA bank. A successful
new SNAPSHOT replaces the old one; NO_FRAME preserves it. Pixels are row-major,
top-left first, four final two-bit shades per byte, first pixel in low bits.
Frame sequence starts at zero at the first completed source frame per core reset.
The snapshot includes its core-reset epoch; host snapshots are convenience
readback and cannot satisfy every-frame comparison alone.

## Retirement records

The generated fixed-size retirement record is an observation ABI, not UART
streaming. Publish one event after all architectural effects of each instruction
commit, and separate interrupt-entry events after entry completes. Prefix and
following opcode are one instruction, not separate retirements. HALT/STOP idle
dots produce no retirements. `dot` counts completed emulated T-cycles since core
reset, including peripheral time during CPU HALT; host pauses add no dots.
`pc_before` is the first fetched opcode address, or interrupted PC for an entry;
`pc_after` is the actual post-event PC, including branches and HALT-bug effects.
Fetched bytes reflect memory at fetch time, not a later ROM disassembly.

All CPU fields are post-event values. Interrupt entry has zero opcode/length;
instructions have one through three fetched bytes, unused high opcode bytes
zero. Boolean state fields are zero or one, F's low nibble and IF's high bits
are zero. Event sequence counts both kinds from zero. The host retirement
counter counts only instruction kind. Epoch starts at zero after global reset
and increments on every completed core initialization, including load resets.
Counters wrap modulo their generated widths; test bounds must not span wrap.
Adapters record ROM hash, profile/trace ABI, reference version/configuration and
epoch in ignored run metadata. They normalize independent observations into this
format without sourcing expected CPU state from the DUT. Bus-cycle/access logs
and exact instruction semantics remain the CPU verification contract's scope.

Packed SV structs place the first record field at the least-significant bits;
serialize each field low byte first. Python codecs use explicit little-endian
conversion, never native struct alignment. The [SV fixture](../../../../src/dv/interfaces/tb_interfaces.sv)
checks imported widths/offsets and an independently written literal byte vector.
Its corrupt variant must fail with the expected mismatch. Host tests cover
CRC vectors, full byte alphabets, maximum payload, malformed frames, range
neighbors, unsigned width failures, disjoint spaces and generation mutations.
These prove representations, not a working CPU/PPU or UART controller.

## References

The source pins Pan Docs commit `fe246067b695b5404a4a6a47efb4fd6d921ececb`,
CC0-1.0. Consulted [memory map][map], [joypad][joypad] and [audio register][audio]
addresses; no reference HDL, boot assets, test code or prose was imported.
The direct-entry values, host layout, wire framing and trace format are original
project decisions. See the [source policy](../../../tools/provenance.md).

[map]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Memory_Map.md
[joypad]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Joypad_Input.md
[audio]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Audio_Registers.md
