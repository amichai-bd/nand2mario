# Preloaded execution simulations

This boundary supplements the [real UART integration](../integration/SPEC.md); it does not
replace loader, transport or end-to-end acceptance.

Validated initialization, loader lifecycle, checked execution and matched
real-UART/preload state, trace and performance comparisons are implemented.
[#168](https://github.com/amichai-bd/nand2mario/issues/168) retains only the exact
finite-Tcl execution-delay investigation and its final review. The comparison
requirements below remain the criteria for qualifying equivalence on changed inputs.

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

## Reuse and measurements

`integration-preloaded` selects the existing integration scenario with
`PRELOADED=1`. Its peer uses `n2m.preload.prepare` before simulator startup and
`n2m.preload.adopt` for the real BEGIN/END commands. The target's explicit
`driver.preload` flag requires a fresh file/hash check before launch.
`integration-smoke` retains the full real load and readback path.

A new simulation composition selects `SIM_INIT_FILE` on its ROM and presence
wrapper instances and `SIM_PRELOAD` on the load owner. These are declared module
parameters, not access to vendor internals. All three must refer to the same
prepared image/configuration. Other memory instances retain `UNUSED`, and all
synthesized instances ignore simulation initialization.

The focused `preload-lifecycle` and `preload-crc-fault` targets check the load
boundary with the same installed Intel model. The offline comparison command is:

```text
python src/dv/preload/compare.py --root <workspace> --normal <real-result.json> --preloaded <preload-result.json>
```

It requires accepted results from the distinct declared modes, matching source,
seed, simulator, Python runtime and trace configuration. It verifies retained
hashes before comparing the complete image and ordered initial-state,
retirement, bus and pixel files. Partial or failed runs cannot establish full
equivalence. Request/cache histories remain different by design.

`loader_command_wall_seconds` excludes preparation and model startup.
`peer_to_loaded_wall_seconds` includes software/MIF preparation, model startup,
identification and loader completion, but excludes compilation before the peer
starts. The retained builder start and loaded-checkpoint timestamps permit a
separately labeled compile-inclusive duration. Execution wall/simulation times
cover the same INPUT/RUN/WAIT/HALT sequence in both modes.

## Continuous Client comparison

`python-integration-uart` and `python-integration-client-preloaded` use the same
product Client, serial transport and independent Python execution monitors.
The first uploads and reads back all 32768 bytes. The second selects supported
Intel initialization and real BEGIN/END adoption. Both read the same initial
public fields, send INPUT0/RUN, reach dot136280 and send HALT/STATE_PAUSED.
The original 69 retirement, 145 bus and 46080 pixel expectations remain unchanged.
The default `python-integration` scheduled diagnostic remains a separate mode.

```text
python src/dv/preload/compare_continuous.py --root <workspace> --normal <real-result.json> --preloaded <preload-result.json>
```

The comparator requires both explicit modes and exact common source, model,
Python runtime, seed and trace configuration. Only the declared initialization
selection and Python entry module differ. It validates artifact hashes, complete
ordered outputs and normalized initial state, including released resets, paused
state and zero observed activity. Receipt count, presence and CRC retain their
dedicated lifecycle proof; no new public loader register is introduced.

Both modes emit UTC checkpoints at test entry, loader start, loaded/paused,
RUN request and final paused. The builder's recorded stage start precedes image
preparation, compilation and model startup. Subtracting that start from the
loaded checkpoint includes those costs, but excludes earlier tool discovery,
source hashing and environment installation. Loader-command and loaded-to-paused
intervals are reported separately. Stage duration ends after result checks,
before final artifact hashing and publication. Reject unordered timestamps;
do not infer a performance improvement
from unlike configurations or these intervals alone.

Successful continuous execution establishes the checked correspondence under
this mechanism. It does not identify the exact cause of the retained finite-Tcl
failures. Those failures and that limitation remain explicit in issue168.
