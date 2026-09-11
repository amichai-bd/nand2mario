# UART endpoint verification

Contract: [UART MAS](../../../wiki/src/rtl/uart/MAS_uart.md) and its shared ABI.
Issue #91 tracks full endpoint acceptance; completed slices remain bounded to
their named fixtures. The serial pair also composes the real packet receiver
and Intel stores to check framing-error discard and delimiter recovery.

| Boundary | Independent checks |
| --- | --- |
| Serial | Idle/start/data/stop timing, all byte values, fractional phase, false start, bad stop, reset during each bit; check public RX/TX bytes against driven bits |
| Framing | Literal known CRC vectors, COBS zero blocks and 254-byte blocks, equivalent trailing encoding, maximum payload, delimiter-only, truncation, malformed code, oversize and idle recovery |
| Validation | Bad CRC/kind/request status cause no request or response; valid unsupported version/command and invalid lengths give exact statuses without effects |
| Duplicate | Identical decoded retries, equivalent COBS forms, same sequence with changed bytes, intervening sequence, wrap and core/global reset; count effects independently |
| Load | Full public load/readback, arbitrary order, overlap/rewrite, missing byte, bad whole-image CRC, repair/restart, running write rejection, reset acknowledgement after initialization |
| Control | HALT after current dot, RUN resume without catch-up, STEP instruction versus interrupt events and HALT/STOP budget, retirement wins at budget, all eight input bits and simultaneous masks at exact dot boundaries |
| Isolation | Separate host-address and ROM-offset validation, every known/unaligned/unknown host word, no DMG bus decoder or CPU-address truncation |
| Harness sensitivity | Corrupt an actual returned byte or duplicate an actual accepted effect; require a named nonzero mismatch, plus a meaningful local assertion failure |

Stimulus, passive accepted-effect monitors and expected packet bytes remain
independent of DUT decode/next-state fields. Retain explicit public wave signals,
transaction logs, exact source snapshots and Intel binding evidence. Test-only
core/storage/snapshot models prove their boundary contracts, not full-system
integration. Licensed runs use the shared serialized tool slot recorded by the orchestrator.


### COBS response output

The packet-transmit fixture constructs an independent flat COBS byte vector
with reserved/backfilled code positions. It compares each accepted byte from
the DUT against this vector while the actual serial TX supplies backpressure.
Maximum-length zero, nonzero, incrementing, block-boundary-zero and trailing-zero
patterns plus lengths 12, 254 and 255 cover code and delimiter boundaries.
Eleven complete replies include recovery from three asynchronous resets during
scan, after a code and during the final data byte. The completion check requires
all ten serial cells per accepted byte, including the final delimiter stop.
Actual output corruption and missing public-read response have separate negative
targets. This fixture's response source is a public one-edge model; later full
endpoint composition binds the already fitted Intel exchange store.


The response fixture checks empty, maximum-payload and STEP_LIMIT raw replies
against fixed byte vectors generated with Python's standard-library CRC16,
then reads all bytes from the actual Intel staging bank. Payload gaps, sequence
and command echo, little-endian header/CRC order and completion-after-write are
checked. Three global cancellations cover header, held payload and CRC stages;
fresh public writes recover. An actual CRC-byte corruption must fail the fixed
expected stream. This response-construction test does not claim command effects.


The load fixture binds the real memory owner's ROM port and the fitted one-bit
presence store. An original deterministic 32768-byte image has a fixed expected
Python zlib CRC32. Descending chunk writes leave one byte absent, repair it,
replace and repair an overlapping byte, then read every byte with backpressure.
A second BEGIN leaves one byte unmarked while retained ROM data already matches
the full CRC, independently sensitizing the presence check. Global resets cancel
a partial sweep and a partial write; committed ROM data survives, and new END
cannot reuse old presence. Actual ROM-response corruption and an actual presence
bit force must fail opposite literal success/error expectations. Loader tests do
not substitute for the endpoint's later state validation and reset acknowledgement.


### Full wire command composition

`uart-endpoint` sends independent CRC16/COBS requests through actual serial pins,
all packet/cache/response owners, real Intel ROM/presence storage, the actual CPU
and its timebase. A deterministic original 32768-byte image has fixed zlib CRC32
83bb4628; every byte is loaded and read back through wire commands. The fixture
checks error precedence, completed replay and conflicting sequence preservation,
reset acknowledgement after the memory sweep, publication after successful END,
paused/running command rules, STEP completion/budget/interrupt exclusion, all
input bits and every generated host word. Actual reset-effect duplication and
actual ROM response corruption must fail the corresponding independent checks.

The CPU responder covers this program's ROM and HRAM stack only, gating service
during initialization and host loading. The snapshot boundary is an explicit
completion/read model, covering NO_FRAME, metadata, last-byte bounds and published
host retention across core reset. It does not claim full peripheral routing or
#93 storage composition. The wire clock ratio is deliberately eight clocks per
bit to bound the full-image test; physical 25 MHz/115200 timing remains covered
by the retained serial slice. Already-STOPped STEP returns immediate STEP_LIMIT without advancing time.


The focused `uart-snapshot` wire fixture binds the delivered
`n2m_frame_snapshot` and all four Intel banks. Original public observer pixels
produce independently packed bytes and literal epoch/sequence/dot metadata.
It reads all 5760 bytes after capture, rereads the old publication after a new
source completes, then captures and reads the replacement. Metadata/validity
cannot change before the completion pulse. Actual UART LOAD_BEGIN supplies the
core reset; published bytes survive and remain readable while LOADING. Global
reset invalidates publication, NO_FRAME recovers, and a fresh source captures.
An actual returned frame byte force must fail the wire payload comparison.

This focused test performs no ROM load/readback traffic and uses an explicit
16-clock aggregate core-initialization boundary. It complements the unchanged
actual CPU/ROM endpoint proof. The source observer is driven directly, so no PPU
pixel or whole-system claim follows. Earlier model-backed snapshot cases remain
historical boundary evidence; this test supplies actual owner composition.


`uart-stopped-step` binds the actual CPU, existing timebase and host core-control
owner. An original STOP instruction establishes oscillator sleep. Four immediate
STEP failures cover budgets1/70224 with and without a queued wake and held A5/FF
input. Public pause, dots, retirements, epoch, CPU sleep and absence of effects
remain unchanged through each reply and following clocks. A later RUN delivers
the preserved queued wake once. The wake boundary is explicit stimulus, not a
claim about analog restart or the JOYP detector. Actual pause-output corruption
must fail the independent freeze checker. The normal full wire endpoint test
remains the affected command/status/reset/ROM regression after this control edit.

`uart-validation` is the focused synthesis-correction regression for the actual
host-register decoder and command validator. It checks all thirty-eight literal
host values, intervening unaligned bytes, the unassigned words above the map,
high address aliases and unknown rejection, plus seven reply lengths and
malformed lengths. Its 200 checks do not replace full serial endpoint evidence.
The negative corrupts the actual build-ID word.

`io-peek` proves a host read of the DMG I/O view disturbs nothing. Two identical
copies of `n2m_timer`, `n2m_interrupts` and `n2m_ppu_registers` run on one
stimulus; only copy A is peeked, with the decode sweeping every exposed address
each edge. Every committed observation, interrupt flag, timer output and register
readback must match on every edge, and each peeked word must equal copy A's live
value. `io-peek-disturb` routes the peek through copy A's DMG I/O port instead,
which is the wiring mistake the design avoids, and must fail with
`IO_PEEK_DIVERGENCE signal=tima`.
