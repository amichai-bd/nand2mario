# JOYP verification plan

Status: preparation for issue134. No runtime evidence yet.

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
