# Springtrail shadow OAM publication

The publisher transfers the complete prepared scene without interpreting its
object count. Physics and one-update/one-prepared-frame cadence are unchanged.

## Contract

SceneBuffer is C100-C19F: one aligned 160-byte image, 40 four-byte objects.
PrepareScene clears unused bytes after its current 80-byte result every time.
The [composition contract](../../../wiki/src/sw/springtrail/COMPOSITION.md)
owns the active count and clears the remaining entries;
the publisher always transfers all 160 bytes without interpreting that count.
Zero Y hides an unused object, and the entire unused entry is zero.

Initialize the nine bytes `E0 46 06 28 00 05 20 FC C9` at FF80 while LCD is off. PublishScene calls
it with A=C1; the routine writes FF46 and executes only from HRAM through transfer
completion, then returns. The existing DFFE stack remains: CALL writes precede
the FF46 trigger, RET reads follow completion. No stack access occurs during DMA.
Reuse #308's qualified 160-byte/4-dot transfer timing and HRAM wait. Initialize
and publish once before LCD enable; subsequent calls stay in the existing
VBlank slot after map work and before visible-time game calculation. Include
the publisher in the reachable whole-VBlank bound before execution.

The publisher body is 880 dots (including its RET), versus the old 904; the
caller CALL costs 24 in both cases. The 40-iteration HRAM NOP/DEC/JR wait costs
796 dots plus LD B's 8, exceeding the qualified final-byte boundary. The
whole-VBlank bound is 3944 dots, below 4560. Initialization adds 428 dots for
CALL/setup/nine copies/RET and 4 to restore A=0.

The historical nine-object fixture used a 36-byte scene, a 20000-dot ready
window and LCD enable at 81352 = 76964 + 432 + 3980 - 24. Those timestamps do
not qualify the current courier ROM. Its composition checker bounds initial
LCD enable at 100000..130000 dots and combined visible preparation at 46000
dots, preserving the same following VBlank. The current actual enable is
119948; expected pixels and state are independent of that observed phase
origin. The shared 880-dot publisher body and DMA byte timing are unchanged.

## Finite acceptance

1. Host/build checks establish literal HRAM bytes, shared assembled publisher
   identity and complete image layout. A CPU fixture calls that exact publisher
   with ordinary software-written representative multi-piece records, including
   first/last entries, then a smaller scene with explicit inactive clearing.
2. A short complete actual-system fixture observes all software source writes,
   accepted DMA byte data and CPU destination readback/return, then pauses and
   checks completion. It reuses #308's unchanged DMA read-path qualification;
   this fixture does not independently observe every raw RAM read. CPU bus
   commits stay in HRAM throughout the qualified active interval and a settled
   post-ack hold proves no dot/retirement progress. The full case adds
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
