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
integration. Licensed runs require the root's exclusive slot.


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
