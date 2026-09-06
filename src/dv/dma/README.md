# OAM DMA verification

Full scope follows [DMA MAS](../../../wiki/src/rtl/dma/MAS_dma.md) and #132.
Pure corruption has reviewed bounded runtime evidence. The adopted digital
policies are in MAS; composed arbitration verification remains incomplete.

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

The `dma-engine` fixture independently supplies the expected page and destination
for all256 pages and160 offsets, fresh timing, changed-page/middle/consecutive
restarts, terminal/restart priority, suspended progression and reset at all
four public phases. It checks preparation and writes separately. This synthetic
source proves sequencer behavior only; actual memory/CPU/PPU remains required.
`dma-engine-byte` corrupts actual byte7, `dma-engine-time` advances its actual
valid to T3, and `dma-engine-service` withholds the promised first response.
The exact expected failures are DMA_ENGINE_BYTE, DMA_ENGINE_TIME and the local
DMA_SOURCE_SERVICE assertion. All public ports and independent expected fields
are dumped, and every phase observation has a CSV row.

The first dma-composition fixture runs an original HRAM program on the actual CPU, enables the actual PPU, and transfers160 bytes through the shared Intel stores while checking64 HL increments. Independent OAM words, physical writes, PPU pre-dot pair data and complete final public readback are checked. This initial case does not replace the remaining source-bus, restart, power-state and other IDU-family witnesses. dma-composition-byte corrupts the actual raw OAM write value and requires DMA_COMPOSITION_WRITE.

The halt case uses a real CPU HALT after LDH retirement at DMA byte0, checks actual partial-even pair0810 through1000 system clocks, then enables an IRQ input and requires the next DMA byte at wakeT4+4 dots. The unresolved case changes the accepted observation qualifier and checks no current write before its named fatal. A separate literal SYNTHESIS wrapper runs the same product with hardware assertion exclusion and checks200 further clocks without effects after the sticky fault; it does not waive the normal assertion target.

The HALT witness seeds OAM byte1=08 but source byte1=27, so even-pair0810 is distinguishable from the later transferred odd-pair2710. The earlier inserted-NOP fixture failed with two transferred bytes and remains retained; it was a fixture schedule error, not an RTL failure.

The HALT fixture checks the actual service output, not a PPU phase2 fetch. Actual DMA-held phase2 consumption remains a separate required full-composition witness.


The dma-terminal fixture uses the actual object scanner and Intel OAM store.
Only object39 is admitted before DMA. Synthetic twelve-clock dots exercise
the phase2 pair79 response and captured attributes at12/24/36 clocks after
the final accepted byte, with old159=3C and new159=A5. A separately tagged
pair78 probe rejects broadcasting the pending pair. Actual core reset cancels
a later pending byte. This is a consumer-boundary fixture, not full PPU timing
or pixel output evidence. dma-terminal-corrupt changes the returned pair to
002A and requires DMA_TERMINAL_PAIR.


The read and read-increment composition targets use original opcodes7E and2A
in the same64-iteration CPU loop. They independently check committed FE reads,
old-HL IDU addresses, READ versus READ_WRITE row results, every physical OAM
write and full readback. Scan and excluded-read counts plus a row bitmap bound
actual coverage; nonzero scan coverage is not all twenty rows. The row-fault
target changes the first eligible current-row Y write from10 to00 and requires
the independent DMA_COMPOSITION_WRITE failure.
