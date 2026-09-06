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

The initial [spatial oracle](scene.py) covers stable-register rendering. Its
host sanity checks use explicit bitplanes and remapped palettes. It does not
provide timing evidence and rejects special window activation geometry pending
the separate event model.

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

The shared interrupt integration fixture must coincide T4 retirement with VBlank
and STAT rises and an IF write. Check the interrupt owner's specified priority
and combinational next-IF observation captured by the CPU at B, without moving
retirement to another edge or duplicating IF state in the CPU.

## LY153 comparison fixture

`tb_ppu_ly153.sv` uses the real timebase, legal CPU T4 commits and public
FF44/FF41 readback. Fifty-four checks cover LYC 0/152/153/nonmatching values,
all invalid/valid window boundaries, immediate valid writes, retained IRQ
history across invalid writes, one-system-edge event publication, whole-window
IRQ totals, a held VBlank OR source, pause and reset. The expected edge table comes from MAS_ppu; it does not read DUT
line/quarter counters to choose expectations. Separate actual readback, missing IRQ and extra between-check IRQ corruptions must produce the intended raw fatal exits. This fixture
is pending runtime evidence; normal pixel recurrence remains a separate
composed regression. Same-edge natural-rise/write-fall coverage must respect
legal CPU phase; an impossible T4 stimulus is not composed evidence.

## Palette and asymmetric scene variant

`ppu-palette` uses the same passive row-major source observer with signed tile
addressing, 8x8 objects and eight distinct row patterns. Its oracle independently
selects raw BG/object color and winning palette from original scene memory.
Palette shadows update only from CPU input commits; each A snapshot precedes
that edge's write and is bound to the completed source dot at B. A rotating
legal T4 schedule changes BGP/OBP0/OBP1. Acceptance requires sensitive same-edge
old-palette pixels and later new-palette pixels for all three registers, along
with every-pixel comparison. The negative substitutes the new-palette shade
at an actual sensitive commit pixel. Existing static wrappers preserve the
unsigned/8x16 scene; this variant does not claim dynamic scrolling/window edges.
The variant is pending actual runtime evidence.

`ppu-stat-off` checks fourteen public readback/shared-line observations across off-state writes, equal and unequal restart, pause and core reset. `ppu-stat-off-corrupt` changes the actual retained line while off and must fail the corresponding independent check. These targets require actual runtime evidence; HBlank/OAM transition coverage remains separate.

`ppu-scroll-window` checks every pixel of a blank warm-up frame and a normal
frame with all eight fine-SCX values and WX7/8/15/47/80/159/167/255. Legal HBlank
writes prepare each following line. The independent spatial model counts window
row advances only for visible activations; hidden lines cannot substitute LY-WY.
Its corruption target changes the actual first normal source shade.

`ppu-fine-scroll` isolates nearest legal CPU writes before/after first-map
sampling by mapping every background entry to one repeated-pattern tile. Two
reset-separated cases check the complete blank frame, first normal line and
literal first-pixel timestamps. The normal-line reset origin70221 and first-map
sample70302 are relative to LCD-enable T4; writes70300/70304 select fine2/5.
The corruption target changes actual source shade in the after-write case.
These targets still require actual evidence. WX0/166, intra-fetch coarse
SCX/SCY and WY enable/equality edge coverage remain separate required cases.

`ppu-window-wy` enables the window during LY32 before its X trigger, changes WY
after the equality has latched, hides line34, then checks row2 on line35.
`ppu-window-wy-late` enables only after LY32 has ended and must keep the window
absent. Both use the existing independent full-frame spatial oracle.

`ppu-lcd-video` connects actual PPU transactions to the actual bridge. LegalT4
writes cancel a would-be first pixel and a would-be final frame pixel. Independent
assembly checks zero and23039 partial pixels, no phantom completion, restarted
blank/eligible frames and full VGA image release. Paused core reset retains the
last image; shared global reset clears both endpoints and blacks RGB. The fault
target changes the actual observer sequence while leaving source pixels intact.
These new cases require actual runtime evidence and retain the separate
synthetic mailbox coverage rather than replacing it.

`ppu-live-scroll` checks two legal T4 writes at elapsed70312 of the normal
line0 fetch. The selected source trace starts the second map at70308 and
captures it at70309; low and high planes capture at70311 and70313. Reload at
70315 supplies the first visible pixel atA70316 (completed-dot70317). SCY0 to1
therefore combines original row0 lowAA with row1 highAA for pixels0..7, then
uses both row1 planes. SCX0 to8 retains the already captured column0 for pixels0..7
and uses column2 from pixel8. Original flat tile colors distinguish the map
case; asymmetric plane bytes distinguish the SCY case. Registered memory
responses precede the consuming A. This is the approved digital phase mapping,
not a silicon sub-T measurement. The fault target forces the actual public
shade to0 where the first mixed-plane pixel must be3. Both targets require
actual positive/nonzero evidence and retained public wave declarations.

`ppu-window-wx0` checks every pixel for all eight static fine offsets from the
[PPU spatial contract](../../../wiki/src/rtl/ppu/MAS_ppu.md), using original
asymmetric window tiles. Legal HBlank writes prepare each following line.
A checked counter requires fine7 scenes to distinguish columns14 and15.
`ppu-window-wx166` uses a fresh WY32 match: line32 background, line33 window
row1/column8, line34 row2/column8 after WX255, then background. Both retain
public waves and need actual runtime evidence. Neither claims exact mode3
length or resolves the documented physical LCD phase limits.

`ppu-window-disabled-wx` qualifies WY32 with an offscreen window, then disables
Window enable and sets WX47 in HBlank before line33. An original asymmetric BG
oracle checks the selected delayed-load columns and all111 raw0 insertions,
without reading DUT fetch state. The source recurrence traces old WX match at
raw47/count7, no reload, raw48/color0, then the delayed tile at raw49. The fault
target changes the actual source shade at the first inserted pixel from0 to3.
Both targets require runtime evidence; the old failed WY run is not acceptance.

`ppu-access` reads only at legal T4 edges with no objects, DMA or scrolling.
Enable-relative452/456 bracket HBlank/OAM entry;532/536 bracket OAM/transfer;
704/708 bracket transfer/HBlank. Literal mode values are0,2,2,3,3,0; VRAM access
is allowed except the two mode3 samples, while OAM is allowed only at452/708.
The source projection has line reset453, first map534, first visible capture548
and terminal capture707. These are the selected digital timings, not new
sub-T hardware measurements. STAT enable remains reset0: this fixture does not
choose the disputed STAT-write mask or IRQ-source projection. The fault target
forces the actual OAM access output high at the blocked456 read. Both need
actual runtime evidence with public waves.

`ppu-lcdc-fetch` uses the same legal70312T4 seam for two additional existing
matrix entries. Changing BG map select after the second map capture preserves
column0 for the first eight pixels; the third fetch selects column1 of the
other map. Changing unsigned to signed tile addressing between low70311 and
high70313 mixes the old low bank with the new high bank for those first eight
pixels, then uses the new bank. Original flat tile IDs and asymmetric plane
bytes determine the expected shades. The reference LCD enable origin changes
only on bit7 rising, not a map/tile write while enabled. An actual public-shade
fault proves the shared pixel checker. These new targets need runtime evidence;
previous scroll cases do not by themselves prove these LCDC changes.
