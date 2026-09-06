# PPU verification plan

Planned verification for the [PPU MAS](../../../wiki/src/rtl/ppu/MAS_ppu.md)
and [#120](https://github.com/amichai-bd/nand2mario/issues/120). No simulation
result is claimed by this plan. Resolve the MAS timing and interface gates
before implementing dependent checks or RTL.

## Independent boundaries

Stimulus schedules CPU transactions and emulated dots without reading DUT state.
A memory model records every PPU read and CPU/DMA access. The passive observer
records source pixels, frame events, mode/access outputs, register reads and
interrupt requests with external dot identity. A scene oracle computes final
shades from original asymmetric tile/object data. A separate event/timing oracle
uses pinned source expectations and the scheduled writes; it must not use DUT
counters, fetch state or completion to choose an expected result.

## Required matrix

| Group | Directed cases and independent checks |
|---|---|
| Background | Both maps, signed/unsigned tile addressing, all palette values, X/Y wrap, SCX fine offsets 0–7, asymmetric rows/columns and tile indices |
| Fetch changes | SCX coarse change, SCY changes at each bitplane fetch, LCDC map/tile selection, and palette writes before/at/after independently predicted output positions |
| Window | WY match history, hidden lines and internal row count, WX boundaries including 0/7/166/offscreen, midline disable/re-enable and repeated activation, window fetch penalty |
| Objects | First ten Y matches including X-hidden entries, 8/16 height and tile addressing, flips, X clipping, transparent colors, smaller-X/OAM-tie ordering, winner selection before BG priority, both object palettes |
| Timing | Every scanline and complete frame, fine-scroll/window/object variable transfer penalties, no-object baseline, overlapping objects in one tile and X=0 penalty |
| Registers/access | Masks and writes, blocked VRAM/OAM reads/writes, LY/LYC transitions including line153, shared STAT edge blocking, write glitch, line144 STAT/VBlank coincidence, LCD-off comparison retention |
| Startup/reset | First-line mode sequence and first-frame white source pixels, disable before/at/after first/last pixel, core reset initialization, partial source cancellation with no false completion |
| Control | Host pause at varied dot phases, resume, CPU HALT with continued dots, externally scheduled same-edge CPU commit and PPU event ordering |
| Bridge composition | Every source frame observed independently of display discard, stopped/slow pixel clock, old pending offer, acknowledgement and swap boundaries, repeated disable-enable-disable before acknowledgement, only qualified newer frame releases white presentation |

Cross meaningful cases: window with sprites, fine scroll with objects, palette
changes with variable stalls, reset/disable with partial and offered frames.
Coverage records the case and expected result; counters alone do not prove it.
Use BGP maps where raw BG color0 maps black and a nonzero color maps white,
proving object-behind-BG priority tests raw color before palette mapping. Cross
that with winning-object selection and OBP-remapped color0 transparency.
A frame checksum supplements every-pixel comparisons and cannot replace them.

## Failure and evidence

Shared-builder Questa targets must include positive rendering/timing/integration
and deliberate pixel, timing and interrupt faults. Each negative must produce
its own named diagnostic and nonzero raw exit, not merely a generic timeout.
Unknown outputs and missing memory responses fail. Named local assertions
supplement the independent models, with reset/history behavior checked and
synthesis exclusion preserved.

Retain source-pixel CSV, externally timed register/mode/access/IRQ events,
expected/actual mismatches, original fixture identity, seed, exact command/tool
records and waves under the build tag. Declare complete line/frame counts and
coverage before runs. Bound the watchdog from the planned dot schedule, without
shortening coverage to avoid a failure. No physical or full-system acceptance
is implied by these unit and bridge-composition tests.
