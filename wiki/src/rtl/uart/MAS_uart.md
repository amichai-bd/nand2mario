# UART endpoint

Status: implementation in progress under [#91](https://github.com/amichai-bd/nand2mario/issues/91).

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
memory port is enabled. The memory implementation in pending #130 is not copied
into this branch; later composition must bind these reviewed ports explicitly.

The snapshot owner in #93 supplies a separate completion/read boundary; UART
does not read or lease VGA banks. CPU, PPU, DMA, JOYP and endpoint framing are
distinct owners. Boundary fixtures do not claim those pending implementations
are composed or physically tested.

## Verification

The [test plan](../../../../src/dv/uart/README.md) separates serial framing,
packet integrity, duplicate handling and completed control effects. Required
actual runs use Questa and the installed Intel model, through the shared builder.
No physical transmission is part of this issue's acceptance.
