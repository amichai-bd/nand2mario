# ROM loading and host control

Provide verified Python ROM loading, host execution control, complete button
masks and immutable frame readback through the shared builder.
[Issue #92](https://github.com/amichai-bd/nand2mario/issues/92) owns delivery.

The [Stackdrop player comparison](../../../src/sw/stackdrop/SPEC.md#pixel-player-comparison)
uses these public controls and rendered snapshots for software decisions.
It must preserve the same package, identity, uncertainty and safe-stop rules;
it adds no gameplay memory access or alternate protocol.

The tool consumes the [generated interface contract](../../../src/rtl/interfaces/MAS_interfaces.md)
and successful [packaged software attempts](../../sw/SPEC.md). It must reject
wrong profiles, sizes, stale interfaces, damaged artifacts and mismatched full
ROM readback. A timeout reports uncertain completion and never replays a command
automatically. Missing, ambiguous or unhealthy explicit devices fail before
serial open or transmission.

Fake endpoint tests prove the complete host path, all 256 input masks, controls,
snapshot chunking, errors and persistent uncertainty. Tagged evidence records
identity, commands and results without embedding ROM bytes in logs. Physical
execution follows the existing verified setup and serialized access workflow;
fake success does not establish RTL, wiring or board acceptance.

The [SPEC](SPEC.md) owns commands, transport and artifact rules. UART endpoint
RTL, hardware snapshot storage and software packaging remain separate owners.
