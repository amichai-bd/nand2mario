# JOYP verification plan

Status: matrix, register and event acceptance complete for issue134.
Producing source identities, logs and independent review are recorded in PR150.

Use an independent literal matrix table: all256 active-high button masks and
select values00/10/20/30. Check each bit, high read mask, neither/both rows,
opposite directions, full ignored-write-bit sweep and generated resetFF.
Expected results must not call product functions or generated bit-map helpers.

Directed event cases cover each line fall/release/repress, repeated held masks,
simultaneous falls, shared-bit press while already low, switching between rows,
selecting/deselecting held buttons, and reset priority. Place INPUT and select
writes around T4 A and IF B, including IF clear/ack; preserve all accepted updates
and distinguish event transport from saturated IF storage. Hold host pause and
CPU HALT/STOP while changing buttons; verify no emulated time advances merely
because INPUT changes. Wake observation is raw selected-line intent, not an
oscillator-stable or complete CPU-execution claim.

Use actual mapping/lost-event/duplicate-event mutations and one meaningful local
assertion violation. Every target must compile, elaborate, run and check exact
raw exits. Dump explicit public signal lists and audit nonempty useful VCDs;
retain literal CSV/records and exact tool/source identities.


The register fixture sweeps all256 write bytes with only bits5:4 retained, then
all256 atomic input masks while gb_tick is held. It checks uncommitted writes,
neighbor selection, committed reads, simultaneous input/select replacement and
both reset types winning over both updates. Fourteen explicit public waveform
signals are retained. Actual commit suppression must cause the literal register
mismatch; an off-T4 commit must fire JOYP_COMMIT_BOUNDARY. Event/IF/wake proofs
use the approved selected-line digital event rule, separate from these state checks.

The event fixture checks187 system edges and42 literal falls through the actual
IF owner. It covers all eight buttons, adjacent falls, shared held lines,
select/input coincidence, three placements around A/B with clear/ack, reset
cancellation and withheld dots. Lost and duplicate actual output mutations fail
at cases4 and5. Twenty-four explicit public signals accompany the CSV. Mode
labels identify withheld-dot input scenarios; they do not claim composed CPU
execution, UART transport or physical clock qualification. Existing IF truth
and phase fixtures also pass with the new event input tied low.
