# Snapshot verification

The [owner contract](../../../wiki/src/rtl/snapshot/MAS_snapshot.md) defines the
service. All fixtures use the installed Intel model with the product parameters.
Expected packed bytes come from original source-pattern arithmetic; no private
primitive array is loaded or inspected.

| Target | Required observation |
|---|---|
| snapshot | First complete frame, NO_FRAME, all 5,760 bytes and metadata; one-edge read service. |
| snapshot-lifecycle | 43,367 byte checks across pinned-source omission, delayed reads, old-bank response on publication, new-bank next response, abort, four core-reset cancellation phases and global reset. |
| snapshot-overwrite | Actual write to the published host primitive corrupts byte 3; the independent data check fails. |
| snapshot-latency | Suppressed actual frame_valid fails the response-edge check. |
| snapshot-ownership | Actual source-bank collision fires SNAPSHOT_BANK_OWNERSHIP. |
| snapshot-vga | Existing VGA source/raster/ownership fixture composed unchanged with the snapshot service: every-frame observation, delayed host reads across new frames and core resets, and a display swap during copy. The pre-global-reset coverage is 18 frames; the unchanged VGA fixture also checks its restart frame. |

The FPGA snapshot target uses scalar virtual ports around the same four product
stores. Its fitted inventory is four 5,760x8 memories, 32 M9K atoms and 184,320
logical bits. Input/address registers and unregistered outputs preserve the
single request-edge read latency; port B remains read-only on the system clock.
The proof wrapper exposes the fixed size through a state-dependent comparison,
avoiding constant physical output pins without changing the product ABI.

The composed waveform retains the existing bounded reset/first-image windows
and includes host reads. Swap-during-copy coverage comes from checked public
events and counts; its earlier transition is outside those waveform windows.

Commands, raw outcomes, hashes, public waves and independent reviews belong to
[PR151](https://github.com/amichai-bd/nand2mario/pull/151). Initial compiler and
virtual-pin failures, stopped fixture runs and the corrected swap-scheduling
coverage failure remain retained; they are not acceptance results. Simulation
and fit do not replace physical VGA or full UART integration evidence.
