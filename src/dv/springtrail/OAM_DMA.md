# Springtrail shadow OAM publication

Issue #299 replaces only the publisher. The existing nine-entry scene, art,
physics and one-update/one-prepared-frame display cadence remain unchanged.

## Contract

SceneBuffer is C100-C19F: one aligned 160-byte image, 40 four-byte objects.
PrepareScene clears unused bytes after its current 36-byte result every time.
Future #292 composition owns its active count and clears the remaining entries;
the publisher always transfers all 160 bytes without interpreting that count.
Zero Y hides an unused object, and the entire unused entry is zero.

Initialize a small original routine at FF80 while LCD is off. PublishScene calls
it with A=C1; the routine writes FF46 and executes only from HRAM through transfer
completion, then returns. The existing DFFE stack remains: CALL writes precede
the FF46 trigger, RET reads follow completion. No stack access occurs during DMA.
Reuse #308's qualified 160-byte/4-dot transfer timing and HRAM wait. Initialize
and publish once before LCD enable; subsequent calls stay in the existing
VBlank slot after map work and before visible-time game calculation. Include
the longer publisher in the reachable whole-VBlank bound before execution.

## Finite acceptance

1. Host/build checks establish literal HRAM bytes, shared assembled publisher
   identity and complete image layout. A CPU fixture calls that exact publisher
   with ordinary software-written representative multi-piece records, including
   first/last entries, then a smaller scene with explicit inactive clearing.
2. A short complete actual-system fixture observes every source read, destination
   byte and CPU return, then pauses and checks completion. The full case adds
   the second publication and all 160-byte stale-entry checks. Actual wrong-byte
   fault must fail the unchanged downstream checker; focused host omissions and
   stale-tail negatives exercise completion/count boundaries.
3. The smallest affected composed game proof retains independent state/pixel and
   input/publication cadence checks. Qualify unchanged physics and #308 overlap
   evidence; old startup timestamps are historical, not new-ROM expectations.

Use existing Python/Intel preload, passive public observations and the builder.
Run the complete harness briefly before the longer case. Target 120 seconds per
simulation and 300 seconds ordinary aggregate, with a 300-second total hard cap
per simulation. Freeze source-derived timing and measured aggregate forecast
before expensive runs; no physical test or FPGA rebuild is required here.
