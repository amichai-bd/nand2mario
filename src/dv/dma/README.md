# OAM DMA verification

Full scope follows [DMA MAS](../../../wiki/src/rtl/dma/MAS_dma.md) and #132.
The fixtures below cover pure corruption and composed arbitration. The adopted
digital policies and physical-model limits are defined in the MAS.

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

Composed verification uses the actual shared Intel OAM store, delivered CPU
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

The dma-composition fixture runs an original HRAM program on the actual CPU, enables the actual PPU, and transfers160 bytes through the shared Intel stores while checking64 HL increments. Independent OAM words, physical writes, PPU pre-dot pair data and complete final public readback are checked. The source-bus, restart, power-state and other IDU-family witnesses below complement this case. dma-composition-byte corrupts the actual raw OAM write value and requires DMA_COMPOSITION_WRITE.

The halt case uses a real CPU HALT after LDH retirement at DMA byte0, checks actual partial-even pair0810 through1000 system clocks, then enables an IRQ input and requires the next DMA byte at wakeT4+4 dots. The unresolved case changes the accepted observation qualifier and checks no current write before its named fatal. A separate literal SYNTHESIS wrapper runs the same product with hardware assertion exclusion and checks200 further clocks without effects after the sticky fault; it does not waive the normal assertion target.

The HALT witness seeds OAM byte1=08 but source byte1=27, so even-pair0810 is distinguishable from the later transferred odd-pair2710. The earlier inserted-NOP fixture failed with two transferred bytes and remains retained; it was a fixture schedule error, not an RTL failure.

The HALT fixture checks the actual service output. The terminal fixture below supplies the separate actual phase2 consumer witness; the overlay fixture checks the held response after simultaneous effects.


The dma-terminal fixture uses the actual object scanner and Intel OAM store.
Only object39 is admitted before DMA. Synthetic five/six-clock dots exercise
the phase2 pair79 response and captured attributes at5/11/17 clocks after
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


The STOP composition runs an original STOP instruction. Its existing policy
qualifies pause on the accepting carry; registered stopped then holds time.
A thousand system clocks preserve the pair and dot count. An upstream-qualified
phase0/off-tick wake precedes the first resumed transfer by four dots. This
fixture does not implement analog oscillator restart qualification.

Four pause targets request host pause in each CPU phase. They require one
accepting dot, then frozen phase/dots/transfer count for200 system clocks.
Accepted writes may drain; after23 clocks every public effect output must be
quiet. Resume completes full byte/readback checks. The pause-fault target forces
the actual raw write control during the held interval and requires
DMA_PAUSE_SERVICE_DRAIN.


The access fixture drives a shortest-interval five/six-clock-dot CPU boundary around the
actual DMA and Intel stores. Seven source cases cover C0, ROM00, VRAM80 with
both write-gate states, absent A0, and E0/FE mirrors. It checks1,120 destination
bytes and44 reads: accessible M1, conflicting prepared data, RAM AND feedback,
ignored ROM-source writes, gated VRAM redirect, active separate-bus reads,
HRAM/FF46 separation and blocked OAM/unusable reads. Public readback checks
all destination bytes and the untouched CPU-addressed source locations.
This complements real-CPU fixtures; it does not implement other I/O owners.
The corrupt target changes the actual CPU read output81 toFF and requires
DMA_ACCESS_READ with the exact address and values.


The restart fixture supplies four literal CPU-boundary timelines to the actual
DMA and Intel stores: different-page restart at offset20, consecutive FF46
triggers, a mature trigger at old159, and a new trigger arriving at old159.
It checks985 physical writes at exactly13 system clocks after their accepted
T4s and640 final readback bytes. The new trigger on159 is not yet mature:
completion deactivates ownership, M1 writes no old byte, then new offset0
follows. The early target injects a valid physical write one clock early and
requires the independent expected13/actual12 timing failure.

The reset fixture drives both global and core reset in four CPU phases during
pending start, pending transfer, pending restart and corruption service. Its
32 cases check each physical write prefix, cancellation of pending responses
and effects, all 160 cleared OAM bytes, FF46 reset and eight idle M-cycles
without stale work. The corruption context supplies a public row4 prefetch
before the row5 effect; it does not model the PPU scanner. The stale target
forces the actual write output during reset and requires DMA_RESET_CANCEL.

The overlay fixture distinguishes a row5 DMA byte F3 from RAM write feedback
03 at the same T4 as a separately observed FE-page IDU effect. Literal operands
make corruption preserve that distinction: row5 and the held pair must contain
55F3 or 5503, rather than the old 55AA. Actual byte39 commits before the row4
prefetch. Both cases check all 48 physical writes, the held phase2 response and
unchanged WRAM source and CPU-addressed bytes. The corrupt target substitutes
the unmasked F3 for the actual 03 write. This is a synthetic CPU/PPU boundary
witness of the adopted ordering, not a new hardware measurement.

Four original CPU programs exercise INC BC, DEC SP, LD(HL-),A and POP BC in
64-iteration loops around the actual PPU, DMA and Intel stores. They check
literal old addresses, decrement direction, a store plus one IDU effect, and
POP's first read with an effect versus its second ordinary read. POP checks
128 reads. D controls the loop so changing BC cannot alter the iteration count.
The POP fault removes the actual first-read write effect and requires the
independent expected-one/actual-zero observation failure.

The qualifier matrix checks 6,811 finite cases: independent ordinary and IDU
addresses at FE00/FE9F/FEA0/FEFF/FDFF/FF00, full and high-only masks, three
scan phases, seven scan indices and unsampled activity. High-only cases leave
unclaimed low bits unknown. This is a typed-boundary matrix, not an exhaustive
CPU opcode test. Actual-class corruption and an incomplete high mask each
require their intended failure.

The I/O fixture uses the actual interrupt owner and declared replies for other
peripheral boundaries. It checks 18 owner commits (two setup and 16 during
DMA), nine reads, the complete transfer and readback. IF/IE observations remain
available immediately before T3 while the raw port reads an operand. The held
event input proves availability, not single-pulse counting. The fault removes
the actual IF observation. Other peripheral replies prove routing only.

The LCD restart program executes real FF40 off/on writes between two 64-IDU
loops. It requires canceled OAM requests and validity after off, scan effects
before and after reenable, every physical write and full readback. The negative
forces actual response validity while off. This proves cancellation and resumed
composition; fresh-row replacement is checked separately by the scan-tag fixture.

The scan-tag fixture moves from row4 through an excluded interval to row12,
then checks a row13 effect against literal fresh operands and eight readbacks.
It proves replacement after a row jump, rather than isolating invalidation of
an otherwise matching tag. Its data fault changes a returned prefetch byte.
Three further targets require named failures for a missing raw response,
an unmatched operand tag and missing destination-pair readiness.
