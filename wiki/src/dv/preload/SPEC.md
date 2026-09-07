# Preloaded execution simulations

This boundary is being implemented for [#168](https://github.com/amichai-bd/nand2mario/issues/168).
It supplements the [real UART integration](../integration/SPEC.md); it does not
replace loader, transport or end-to-end acceptance.

## Image and state boundary

The software pipeline supplies the complete original ROM and its SHA256.
Preload preparation validates that exact hash, image size and direct-profile
header before producing Intel MIF files for the ROM and its presence bits.
Record both source image and generated file hashes. The installed Intel model
loads these files through its documented altsyncram initialization parameter.
The existing memory ports, latency, collision rules and reset behavior remain.
No behavioral replacement RAM, persistent force or vendor-private state access
is permitted.

A declared simulation-only configuration permits the first LOAD_BEGIN to adopt
those initialized bytes instead of clearing their presence bits. Its expected
CRC must match the generated preload configuration. Normal command validation
still checks length, size and profile. LOAD_END scans every real ROM byte and
presence bit, checks the complete CRC and runs ordinary core initialization.
No loader or core-control register is deposited. The adoption is one-shot for
the simulation lifetime; global reset cannot re-arm it. Later LOAD_BEGIN clears
presence normally and requires a complete fresh load.

The observation boundary is after successful LOAD_END and before RUN:
image_valid1, loading0, state PAUSED, selected direct profile, epoch2 from the
two actual reset operations, dot/retirement counts0, default UART input source
and zero host/effective buttons. CPU and writable memories finish their normal
initialization, and no snapshot is published. Loader receipt presence and CRC
state must correspond to the complete image. Transport request/cache history
is recorded separately because the preload omits LOAD_WRITE transactions.

## Verification and limits

Compare publicly observed initial state and ordered retirement, bus and pixel
traces with real loading, using the same original image and execution scenario.
A mismatch or failure to reproduce a stall is evidence of a difference, not
permission to claim equivalence. Record comparable setup and execution times
with the simulator mode and clock configuration; do not mix them into a speedup
claim without matching workloads.

Required checks include invalid image/hash and CRC rejection, one-shot adoption,
reset followed by normal clearing, successful installed-model execution and an
actual failing case. Real-UART evidence remains separately identified.
The current source is a contract/preparation increment; RTL and runtime proof
are still pending.
