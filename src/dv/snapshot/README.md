# Snapshot verification

The [owner contract](../../../wiki/src/rtl/snapshot/MAS_snapshot.md) defines the
service; issue93 owns full acceptance. The initial fixture publishes an original
23040-pixel pattern through public observation ports, copies it through actual
Intel stores, and checks all5760 independently packed bytes and metadata. It also
checks NO_FRAME before first completion and one-edge read-valid behavior.

No actual runtime is claimed yet. Remaining acceptance includes delayed reads
across subsequent frames, reset/abort and replacement-edge behavior, real VGA
composition and every-frame observation, actual data/latency/ownership faults,
and constrained resource/timing evidence for all four stores. No private Intel
array is loaded or inspected. These remain required before issue closure.
