# UART endpoint

The [UART owner](../../../../src/rtl/uart/n2m_uart.sv) implements this boundary.
Already-STOPped STEP returns immediately without consuming time.

The [shared interface contract](../interfaces/MAS_interfaces.md) owns packet,
command, duplicate and core-transition behavior. Its generated package supplies
numeric values. The [clock/reset contract](../../clocks-resets-cdc.md) owns dot
ordering and the UART synchronizer. This owner implements those rules without
adding DMG address decoding or a second peripheral state owner.

## Module boundaries

All modules use `clk_sys`. Global `reset_sys` clears transport and image validity;
synchronous core reset never clears packet state or the last completed exchange.
The serial boundary synchronizes RX through two flops before sampling 8N1 bytes.
It supplies byte pulses and accepts bytes for TX; baud events are enables.

The packet receiver stores at most `UART_ENCODED_MAX` nonzero bytes, derived from
the generated header and payload sizes. A delimiter freezes the encoded store.
It then decodes COBS into a separate bounded packet store, checks CRC16, and
publishes the header and decoded byte count together. Both stores use the
[shared Intel RAM wrapper](../common/MAS_memory_primitives.md). Public decoded
reads have its one-edge latency and remain stable until the dispatcher releases
the request. No command is exposed before integrity checking completes.

`n2m_uart_packet_store` owns only these two in-flight stores: 270 encoded bytes
and 268 decoded bytes with the current generated ABI, 4304 logical bits total.
It does not contain the completed request/response cache. Both RAMs use nine-bit
addresses, one `clk_sys`, byte writes on port A and one-edge read-only port B.
The receiver writes and decoder reads the encoded bank in disjoint states;
the decoder writes and dispatcher reads the decoded bank in disjoint states.
There is no required mixed-port collision value. Reset masks read validity and
writes but does not initialize contents; per-frame lengths prevent stale reads.
The initial `uart-packet-stores` FPGA target exposes these actual stores with
57 virtual input bits and 18 output bits. It uses the nominal system clock and
explicit 0-2 ns service budgets. The early fit must establish both logical shapes,
actual M9K resources, registered inputs/unregistered outputs and clock/reset
connections before broad dependent verification; generic fit success alone does
not establish that inventory. Later caches and presence storage require their
own capacity and primitive proof, not extrapolation from this first target.

Malformed COBS, short frames, invalid request kind/status and bad CRC are silently
discarded. An intact request with a bad declared payload length is passed to
command validation for BAD_LENGTH, as is an unsupported version for BAD_VERSION.
Oversize input is discarded through its delimiter. Idle timeout drops incomplete
input. Empty delimiters do nothing. Frames arriving while decoding, executing or
replying are discarded, including a frame that straddles return to idle.

The dispatcher validates the entire command before any effect. It compares the
complete decoded request with the last completed request, independent of COBS
encoding choices. Identical immediate retries replay the retained response;
same-sequence differences return SEQUENCE without changing the cache. Completion
publishes request and response cache state atomically. Global reset invalidates
the cache; core reset preserves it.

`n2m_uart_exchange_store` provides three separate raw-packet banks. Bank 0 holds
the last completed decoded request; bank 1 holds its raw response; bank 2 stages
the current response. Each bank has `UART_RAW_MAX` byte words. A fixed bank's
address/data occupies the correspondingly indexed slice of the packed port bus.
The executor cannot overwrite a cached response while constructing a new one.
After command completion, the controller copies the accepted request and staged
response into the cache while transport remains busy, then atomically publishes
the new cache metadata. Same-sequence errors never replace either cached packet.
Only global reset invalidates the cache; core reset is not a store reset input.

These stores use one system clock, A byte writes and one-edge read-only B ports,
with uninitialized contents and reset-masked validity. Their early
`uart-exchange-stores` fit target has 85 virtual input bits, 27 output bits and
6432 logical memory bits at the current ABI. It must establish three physical
M9Ks with matching clock/read/reset structure before dependent cache acceptance.

`n2m_uart_exchange` holds `command_valid` until the executor finishes writing its
entire raw response and asserts `command_done` with the response size. Its
`command_forced_status` is OK for a new command or SEQUENCE for a conflicting
retry; the executor must build that error reply without command effects. The
exchange supplies the executor's packet reads only during execution. Compare and
copy reads use the same one-edge packet-source port while the receiver holds the
request. An identical retry never asserts `command_valid`.

The transmitter holds `transmit_read` and an in-range raw-byte address for each
one-edge read, then asserts `transmit_done` only after sending the delimiter.
Only that completion releases the receiver. Staged responses cannot transmit
before executor completion; new cached replies cannot transmit before the final
copy write and cache publication. There is no ready signal that can alter core
execution timing: these handshakes order host commands outside emulated bus
retirement.

## Core and storage integration

The controller drives the existing timebase `pause_request` and observes `paused`
and `gb_tick`. It observes instruction retirement separately from interrupt entry
and CPU HALT/STOP. Reset completion requires the explicit aggregate core
initialization acknowledgement. Dot and instruction counters are endpoint-owned
observations; they do not create an alternative timebase.

ROM load/readback uses a bounded offset interface to the memory owner. The
endpoint owns image validity, expected CRC32 and per-byte presence. LOAD_BEGIN
pauses, invalidates the image, restarts presence tracking and resets the core.
LOAD_END checks complete presence and reads the actual ROM bytes to compute
CRC32 before reinitializing and publishing valid PAUSED state. A presence bitmap
alone cannot prove data integrity. Running ROM writes are rejected before the
memory port is enabled. The [memory implementation](../memory/MAS_memory.md) remains its own owner; endpoint composition
binds its reviewed ROM ports rather than copying backing storage.

The [snapshot owner](../snapshot/MAS_snapshot.md) supplies a separate completion/read boundary; UART
does not read or lease VGA banks. CPU, PPU, DMA, JOYP and endpoint framing are
distinct owners. Boundary fixtures do not establish their full system composition
or physical operation; the [system contract](../system/MAS_system.md) owns composition.

## Verification

The [test plan](../../../../src/dv/uart/README.md) separates serial framing,
packet integrity, duplicate handling and completed control effects. Required
actual runs use Questa and the installed Intel model, through the shared builder.
Component simulation does not establish physical transmission acceptance.

## Serial byte boundary

The original 8N1 RX and TX modules use clk_sys at25 MHz and the generated
115200 baud rate. Each byte retains fractional clock residue across its ten
bit cells. TX accepts a held byte only while ready, emits start/data-LSB-first/
stop, and returns idle high. The source holds valid/data through acceptance.
RX uses two synchronizer registers and samples only the second stage. It
validates the start midpoint and samples each data/stop midpoint. A false
start produces no byte; a low stop produces a one-cycle framing error and no
valid byte. Global reset cancels partial bytes and drives TX idle high.

A framing error discards the current encoded packet through its next delimiter.
It cannot publish a partial request or disturb an already delimited request
being processed. The serial fixture checks all 256 byte values against a
literal per-clock rational TX oracle, asynchronous RX phase offsets, held TX
input, false start, bad stop and reset in every bit. It also sends literal PING
frames through the actual serial RX and Intel-backed packet receiver: a bad
stop invalidates one frame, and the next complete frame recovers. A deliberate
actual TX pin corruption must fail the independent bit oracle. These are
logical simulation boundaries; no physical wiring or electrical claim follows.


## Response packet transmission

`n2m_uart_packet_tx` reads the held raw response through the exchange's existing
one-edge public port. It scans each COBS block to determine its code byte, then
rereads and sends the nonzero data. It allocates no additional packet memory.
Zero bytes, full 254-byte blocks and a trailing zero produce canonical COBS;
the final delimiter is a separate zero byte. Response size and contents remain
stable through transmission. `transmit_done` occurs only after the actual
serial transmitter finishes the delimiter's stop cell and returns ready.
Global reset cancels scanning or output and resets the serial output to idle.
A missing scheduled memory response produces a named contract assertion.


`n2m_uart_response` captures the reply metadata, emits the generated ten-byte
header, accepts a held byte stream for the declared payload, and appends CRC16
low byte first to the existing staging bank. It reports completion only after
the final CRC write. Error replies contain no payload. Payload gaps stall host
construction without advancing the emulated core or publishing a partial reply.
Global reset cancels this construction; core reset does not reset transport.


## ROM presence storage

`n2m_uart_presence_store` holds one bit per generated `PROFILE_ROM_BYTES` byte,
32768 bits for the direct profile. It uses the same explicit Intel primitive
in simulation and FPGA, one system clock, A bit writes and one-edge B reads.
Reset cancels service/validity; it does not initialize the array. LOAD_BEGIN's
load owner must explicitly sweep every bit to zero before accepting writes.
It marks a bit only with its corresponding accepted ROM byte and does not
clear bits on overlapping rewrites. A presence query and same-address write
must occupy separate edges; mixed-port collisions remain forbidden.

The load controller owns sweep completion and remaining byte count; the command
owner publishes image validity after initialization. A presence result cannot replace reading actual ROM bytes for LOAD_END CRC32.
Global reset invalidates the endpoint's load state; stale array contents cannot
be used until the next complete sweep. Core reset does not clear transport load
metadata. The minimal `uart-presence-store` proof constrains 34 virtual input
bits and two output bits to clk_sys at25 MHz. Its first fit must establish the
actual one-bit logical shape, M9K allocation, registered addresses/read control,
unregistered data output and absence of array reset/initialization before
load-controller acceptance uses this store.


`n2m_uart_load` owns bounded BEGIN/WRITE/END/READ storage operations. The command
owner first validates state, profile, lengths and full-width ranges. BEGIN
captures the expected CRC and completes only after the full presence sweep.
WRITE marks presence on the same accepted edge as its actual ROM byte, including
overlaps. END reads every presence bit and actual ROM byte, accumulates reflected
CRC32, and returns BAD_IMAGE for missing bytes or checksum mismatch. This result
alone never publishes image validity or starts emulation: the command owner must
complete the specified direct-core initialization before replying to LOAD_END.
READ returns a held stream through the actual ROM read port, including paused
backpressure. Neither presence nor CRC relies on a private ROM mirror.

The ROM service is fixed one-edge latency, with separate scheduled read/consume
states. Missing service is a named integration contract failure, not an invented
wait state. Global reset cancels the storage operation and invalidates sweep
metadata while preserving already committed ROM bytes. A new BEGIN is required
before another WRITE/END; raw READ may still observe retained bytes. Core reset
is absent from this transport/load owner and cannot erase a pending response.


## Ordered endpoint composition

`n2m_uart` connects the serial, packet, completed-exchange cache, command and
response owners without another packet array. `n2m_uart_validate` applies the
generated error order before effects. `n2m_uart_commands` reads arguments through
the held request's public port, then orders storage, core and snapshot completion
before publishing a raw reply. READ_HOST uses only the generated host word table;
unknown and unaligned addresses return BAD_VALUE. It never decodes DMG memory.

LOAD_BEGIN invalidates the image and enters LOADING, stops the existing timebase,
resets and awaits aggregate core initialization, then completes the presence
sweep. LOAD_END publishes validity only after actual presence/ROM CRC success
and another completed core initialization. Failed END remains LOADING. RESET
preserves image validity and transport/cache state; its reply waits for aggregate
initialization. The system owner gates CPU memory service during initialization
and host loading. It supplies fixed one-edge ROM and snapshot read service.

`n2m_uart_core_control` owns host pause, epoch and dot/retirement counters. It
also owns the [RUN_DOTS countdown](../interfaces/MAS_interfaces.md#bounded-dot-execution).
The ordinary timebase supplies every counted edge; a final-tick pause
uses the same boundary and B-edge settlement as STEP. Count completion ignores
instruction completion. Existing duplicate caching and error validation apply.

The control owner uses the existing timebase's tick and registered paused acknowledgement. RESET
increments epoch and clears counters; the [shared input owner](../input/MAS_input.md)
restores UART source and released host buttons. INPUT and WRITE_HOST(INPUT)
normalize to one accepted mask operation between dot edges, returning that
boundary's count. WRITE_HOST(INPUT_SOURCE) uses the same acceptance boundary. STEP uses the
CPU's pre-T4 instruction-completion qualifier, excluding interrupt entry, and
counts actual delivered dots. Instruction completion wins a budget tie; the
reply follows the finishing B retirement publication. No synthetic tick or
wall-clock STEP timeout is introduced. An already oscillator-STOPped CPU returns
STEP_LIMIT immediately while host pause, dot/state/input and pending wake remain
unchanged. Named assertions check completion and frozen time; RUN owns subsequent
resumption through the existing wake boundary.

SNAPSHOT holds request until ready, then awaits done/ok and captures the generated
metadata before reply construction. NO_FRAME contains no payload. READ_FRAME
uses the published host bank through its one-edge byte port. The separate snapshot
owner retains published bytes and metadata across core reset and failed capture;
this UART composition does not implement the observer or snapshot storage.

## Simulation preload

The explicit [preload mode](../../dv/preload/SPEC.md) initializes the same Intel
ROM and presence store. Its first valid BEGIN may adopt those bytes only with
the configured CRC; END still scans every byte and performs ordinary core
initialization. The simulation-only adoption flag is consumed once and is not
re-armed by global reset. Later BEGIN executes the normal full presence clear.
Default simulation and synthesized loading do not take this path. No receipt
count is substituted for presence or CRC, and no loader/control state is forced.
