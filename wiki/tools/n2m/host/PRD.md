# ROM loading and host control

Provide verified Python ROM loading, host execution control, complete button
masks and immutable frame readback through the shared builder.

The [Windows console keyboard path](../../../../tools/n2m/host/keyboard.py)
turns real down/up events into complete UART masks, preserving holds and chords.
It captures only its foreground classic console, releases on ordinary exit or
focus loss when completion is certain, and never retries an uncertain request.
It does not start/load the game or replace physical display/control acceptance.

The [Stackdrop player comparison](../../../src/sw/stackdrop/SPEC.md#pixel-player-comparison)
uses these public controls and rendered snapshots for software decisions.
It must preserve the same package, identity, uncertainty and safe-stop rules;
it adds no gameplay memory access or alternate protocol.

The [Springtrail state reconstruction](../../host-play/SPEC.md#springtrail-state-reconstruction)
uses the same Client, package validator and durable session to read selected
memory ranges from a paused core and rebuild the scene from the game's own
records. It must bind an exact qualified image and its linked symbol layout,
acquire only at a documented coherent boundary, label what an image represents,
and refuse an unsupported image or an incomplete observation rather than
substitute a predicted one. It adds no register, no protocol and no game-memory
write, and it does not replace actual-pixel snapshot acceptance.

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
