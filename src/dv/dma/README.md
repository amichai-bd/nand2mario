# OAM DMA verification

Full scope follows [DMA MAS](../../../wiki/src/rtl/dma/MAS_dma.md) and #132.
Transfer/arbitration and composed corruption tests remain planned while their
explicit policy gates are unresolved. No runtime pass is claimed yet.

The initial `oam-corrupt` target checks the pure transformation against an
independent sequential word oracle. It covers twenty rows, four classes,
sixteen bit positions and all sixteen combinations of the relevant four bits:
20,480 cases. Distinct remaining words check row copies. Another48 cases cover
every invalid row20-31 and class. The oracle counts set bits for write-majority
and uses Boolean per-bit operations, retaining both combined stages rather
than deriving expectations from DUT results.

`oam-corrupt-output` changes the actual current-row output at row4 READ_WRITE;
the unchanged expected rows must fail. `oam-corrupt-mask` forces a write mask
on invalid row20 and must fire the local CORRUPTION_MASK_RANGE assertion.
Public inputs/results/masks are explicitly dumped; the CSV contains original
rows, complete expected/actual rows and every case coordinate. A system-time
watchdog is independent of DUT completion. No random seed influences selection.

Later acceptance retains the actual shared Intel OAM store, delivered CPU
internal-address events, real PPU scan/fetch consumers, reset/pause/HALT/STOP,
all transfer bytes/times and actual timing/arbitration defects. A pure formula
pass or normal DMA copy cannot replace that evidence.
