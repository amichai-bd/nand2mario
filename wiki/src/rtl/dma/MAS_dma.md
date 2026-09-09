# OAM DMA and access arbitration

Implementation: [DMA owner](../../../../src/rtl/dma/n2m_dma.sv).
The four adopted digital compatibility projections below define the selected
model. The verification boundary distinguishes component, composed and physical
claims.

## Ownership and boundaries

This owner schedules FF46 transfers and DMG-B OAM corruption. It uses the
single [memory store](../memory/MAS_memory.md), the CPU's
[typed address effects](../cpu/MAS_cpu.md#internal-address-observation), and
the PPU's [scan and fetch port](../ppu/MAS_ppu.md#oam-scan-and-fetch-port).
There is no second OAM image or retirement-based reconstruction of CPU effects.

All state uses clk_sys. The shared [clock contract](../../clocks-resets-cdc.md)
owns gb_tick and the five/six-system-edge dot spacing at 25 MHz. The exported CPU
address_effect_phase directly follows its bus phase, including HALT and idle
cycles. Periodic preparation uses gb_tick and phase3, independently of the
address_effect_sample pulse. Host pause and STOP tick withholding hold phase;
qualified wake resumes phase0. A CPU fault must not authorize further work.

Reset cancels pending transfers and effects. Memory owns its existing OAM
clear sweep; VGA mailboxes and immutable host snapshots are not this owner's
reset targets. FF46 starts at the generated PERIPHERAL_FILL value for the
direct profile, independently of physical boot-state observations.

## Established transfer requirements

The pinned [Mooneye startup test](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/oam_dma_start.s)
places the FF46 write in M0, an accessible delay in M1 and activation in M2.
On restart, the old transfer remains active through M1. The
[duration](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/oam_dma_timing.s)
and [restart](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/oam_dma_restart.s)
fixtures bracket completion with reads one M-cycle apart. A transfer writes
160 bytes at FE00-FE9F, one per M-cycle. Exact T-edge projection remains below.

[Register reads](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/oam_dma/reg_read.s)
return the last written FF46 byte during and after transfer. The
[DMG source test](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/oam_dma/sources-GS.s)
establishes E0-FF source-page mirroring to C0-DF, including FE to DE and FF to
DF. The direct profile's approved absent-cartridge policy still supplies FF
for A000-BFFF; it does not allocate the upstream test's MBC5 RAM.

These MIT-licensed tests report their verified model scope. They are technical
sources; citing them does not establish a passing local test run.

## Corruption qualification and combined service

The pinned [corruption specification](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/OAM_Corruption_Bug.md)
defines read, write and combined read/IDU transformations on twenty eight-byte
rows. Row0 is protected. The combined preliminary transformation applies only
to rows4-18, followed by normal read corruption. Ordinary writes plus an IDU
write count as one write class. Qualify ordinary and additional addresses
separately, including FEA0-FEFF. Reject unresolved or incomplete-high-mask
effects; consume only the CPU's accepted T4 sample.

The raw port serves corruption, DMA and CPU reads in one schedule.
Ordinary line reset is T1; the scanner captures even objects on
T3 and odd objects on the next T1. At T4, row r is pre-edge scan_index divided
by two. The next consumer needs current-row word2. Initial LCD startup has no
enabled scan until the first line reset. Delayed readable STAT is not the
qualification signal.

Let A be accepted T4. The maximum combined transformation writes three rows.
Source operands are the previous row's eight bytes, the row-before-previous
first word and the current first word. They are prepared before A.

| System edges after A | OAM pair banks | Independent byte banks |
|---|---|---|
| 1 | Write current row word2, the next object's Y/X. | No access |
| 2-4 | Write current row words0,1,3. | No access |
| 5-8 | Write previous row words0-3. | No access |
| 9-12 | Write row-before-previous words0-3. | No access |
| 13 | Write an uncovered DMA byte using one byte enable. | No access |
| 14-17 | Read current row words0-3 for the next event. | No access |
| 18 | Read previous row word0. | No access |
| 19 | Read next row word0; capture at20. | No access |
| 20 | Read next DMA destination pair. | Read next DMA source byte. |
| 21 | Grant CPU preparation if it selects OAM. | Grant CPU preparation for other stores. |
| 22 | Capture the tagged CPU response. | Capture the tagged CPU response. |

The minimum M-cycle interval is 23 system edges. DMA source addresses cannot
select OAM: the engine's existing FE/FF mirroring selects DE/DF. Thus the two
edge 20 reads access independent physical memories. Prior writes finish before
next operands are read, preserving consecutive-event coherence. Shorter
classes write only the current row. No speculative write is authorized by
prefetch. Operands and pending results are transaction registers, not a second
authoritative store. Preparation continues when no CPU effect is sampled.

Suppress a raw PPU B-port read only when it collides with a same-pair A write;
restore the registered pair before its consuming dot. The first word2 writes
finish at edge1, allowing a fresh read at edge2 before the next T1. Preserve
the previous request's tag and validity. CPU read response/tag storage must
also be independent of raw A-port reuse. CPU memory data is ready before
its next T4; the separate IE/IF owner must still meet its pre-T3 snapshot.

A DMA byte covered by a corruption row is folded into that row's writes.
Otherwise edge 13 commits it. Keep the resulting pair tagged as pending until
the matching physical write completes: the single uncovered byte, or the
covered pair's atomic two-bank write. This tag is separate from DMA
ownership, which ends at accepted byte159. After ownership ends, only a
request for the pending pair receives its forwarded data. Register selection
and data with the request, including the physical commit edge; subsequent
raw reads supply the committed pair. Reset and fault invalidate this forwarding.
No pending pair may be broadcast to unrelated OAM addresses.

### Qualified late writes

The [addressed-row late class](../memory/MAS_memory.md#direct-path-late-oam-writes)
also applies to this owner through the [DMA service](../../../../src/rtl/dma/n2m_dma_service.sv).
It retains the pinned permission evidence, conditional data semantics and
revision limits of that class. It does not replace ordinary scanned-row or
IDU-only transformations.

At the preceding accepted T4 P, retain the PPU prediction: enabled active scan,
line quarter18, phase3. The next accepted T4 reaches quarter19/phase3. This
prediction survives host pause; selecting from the live phase at a later system
edge would lose it when dots stop but memory service drains.

At slot14, a retained prediction, stable prepared FE00-FE9F CPU write and inactive
DMA select late operands instead of normal prefetch. Read last-row pairs76-79
at slots14-17 and the addressed pair at18; capture finishes at19. All preceding
corruption and DMA writes finish by13, so these operands include their changes.
Otherwise the normal six-read prefetch is unchanged. Preparation authorizes no
write. At actual T4 A, require the late permission, matching address/data and
complete tagged operands. An inconsistent selected transaction faults rather
than consuming stale normal operands. Reset cancels it; pause retains it.

The selected result is the addressed row, with the CPU byte applied last by the
same transform used by the direct owner. Suppress the raw CPU byte write and
normal scanned-row result for this class. Write its words2,0,1,3 at A+1..4.
For row19 this restores pair78 at A+1, permits a fresh B read at A+2 and supplies
the next capture by A+5. Other addressed rows do not collide with that capture.
CPU raw OAM preparation resumes in the existing slot21 window, with its full
response address tag. Each accepted T4 invalidates late readiness, including
consecutive writes to the same address.

Pre-edge active DMA excludes late permission, including accepted byte159 and
restart. Those simultaneous cases retain the ordinary projection and held-pair
forwarding. A terminal DMA byte at P may finish at P+13; the next late operands
then include that physical write. No simultaneous allowed DMA/late class or
additional memory port is introduced.

Unavailable operands, other-byte data, or a granted raw read response raise
named faults. An unresolved CPU sample cancels same-edge effects and latches
fault. Preserve that edge's prepared CPU response: feeding sample-dependent
fault qualification into response_valid would create a cycle-end loop.
The latched fault suppresses later requests, responses and effects.

## Adopted digital compatibility projections

These choices define this DMG-B digital model. They are not physical measurements;
retained hardware tests do not distinguish their same-edge alternatives.

- At a transfer T4, apply same-bus RAM-source CPU write feedback (DMA byte AND
  CPU data), then overlay the DMA destination byte, then apply qualified row
  corruption. Forward the overlay into every affected staged operand. DMA does
  not suppress a separately qualified CPU internal-address effect.
- A conflicting CPU read observes the byte prepared for this T4 transfer.
  Main bus covers cartridge/WRAM; VRAM is separate. A RAM-source conflicting
  write modifies the transferred byte, not the CPU-addressed RAM location.
  Direct ROM writes have no mapper effect. A VRAM-source conflicting write
  targets the redirected source byte only when the normal PPU write gate allows
  it, after DMA samples the old byte. FF46, internal I/O and HRAM remain separate.
- Progress requires pre-edge CPU neither halted nor stopped, plus the emulated
  T4 tick. HALT entry may finish that edge's transfer. HALT wake T4 does not
  advance; the next T4, four dots later, resumes. STOP wake restores phase0;
  its next T4 may advance. During suspension, PPU phase2 receives the pair
  selected by the most recent DMA destination byte, including its overlays.
  An even-byte write updates the low byte while retaining the existing high
  byte; it does not select the preceding completely transferred pair.
- FF46 changes the live page at its accepted T4. That edge consumes its already
  prepared old-page byte. The following M1 consumes the new-page byte at the
  continuing old offset; M2 starts new-page offset0.

The [pinned GateBoy DMA research](https://github.com/aappleby/metroboy/blob/36797ad4cf77b3e04ffe45716218a79b5280076a/src/GateBoyLib/GateBoyDMA.cpp)
locates live page writes at NAFA-MARU, delayed trigger at LUVY/LENE, counter
reset at LAPA and completion reset at MYTE. CPU clock request qualifies the
trigger/counter clocks. Its
[OAM bus](https://github.com/aappleby/metroboy/blob/36797ad4cf77b3e04ffe45716218a79b5280076a/src/GateBoyLib/GateBoyOamBus.cpp)
is a port-ownership reference, not a complete analog corruption oracle.
The retained source manifest records exact hashes and research-only use.

## Sequencer timing projection

The public interface projects the established M-cycle schedule onto accepted
T4 edges. M0 accepts FF46; fresh M1 has no byte write and activates offset0
at its end. M2 writes byte0, through M161 writing byte159. Ownership is active
before the final write and inactive afterward. E0-FF pages alias C0-DF.

| Accepted edge | Fresh transfer | Restart from active offset20 |
|---|---|---|
| M0 T4, FF46 commit | No write; record trigger/page | Write old-page20; record trigger/page |
| M1 T4 | No write; activate offset0 | Write new-page21; reset offset0 |
| M2 T4 | Write0 | Write0 |
| M3 T4 | Write1 | Write1 |
| M4 T4 | Write2 | Write2 |
| M5 T4 | Write3 | Write3 |
| M160 T4 | Write158 | Write158 |
| M161 T4 | Write159; deactivate | Write159; deactivate |

A pending trigger matures on the next qualified T4 independently of a new
FF46 commit. The old scheduled byte completes first; maturation sets index0
and active, overriding terminal completion. A simultaneous new commit records
another pending trigger rather than postponing the old trigger. Consecutive
commits therefore produce consecutive resets. This preserves the source's
separate page, delayed trigger and reset-dominant completion roles; it is an
explicit cycle projection rather than a claim of measured half-phase timing.
A newly accepted FF46 trigger on old byte159 is not yet mature: the old
transfer completes and deactivates; the following M1 activates offset0 without
an old-byte write. A trigger already pending before159 instead matures on
that edge and keeps ownership active at offset0.

Source requests are side-effect-free preparation and persist during pause.
Only a qualified T4 consumes the response. A missing promised response cancels
that edge's byte write and advancement, raises a named assertion and latches
fault; later requests and effects stay suppressed until reset. Neither reset
path clears VGA state. The arbiter supplies pre-edge source data and owns all
physical OAM writes and the held pair; the sequencer adds no backing store.

## Verification boundary

The [directed fixtures](../../../../src/dv/dma/README.md) combine the actual
CPU, PPU and Intel stores where those consumers are needed. Synthetic boundary
fixtures isolate exact restart, feedback, reset and service-fault cases. They
do not substitute for the real consumer checks or implement neighboring I/O
owners. Accepted service may finish while ticks pause; reset cancels unfinished
work. LCD request cancellation and fresh scan-row replacement are distinct
checks.

The pure truth table covers all transformation classes and rows. Composed
fixtures cover transfer/time, CPU address effects, concurrent PPU consumption,
reset/pause/HALT/STOP and deliberate actual faults against the shared Intel
store. A normal copy or pure formula alone is not acceptance. Exact sources,
commands, traces and independent review remain in PR evidence and artifacts.
These component checks do not establish analog DMG measurements, board execution or whole-system
acceptance.

## Settled transformation component

[`n2m_oam_corrupt`](../../../../src/rtl/dma/n2m_oam_corrupt.sv) has no storage or
temporal state. clk_sys and reset sample named invariants only. Its
[package](../../../../src/rtl/dma/n2m_oam_pkg.sv) defines NONE, READ, WRITE and
READ_WRITE. Inputs are row_index and three original 64-bit rows, with the
lowest-address byte in bits7:0. Outputs preserve or transform those rows and
provide a three-bit write mask: current, previous, older in bits0,1,2.
The arbiter owns accepting and physically writing the result.

Row0 and NONE preserve inputs with zero mask. Invalid indices20-31 also
preserve inputs, set invalid_row and return zero mask; an integration sample
must reject them. Row1 requires the real row0 as previous input; only its older
input is unused. READ/WRITE and the excluded preliminary rows use mask001.
Combined rows4-18 use mask111. The implementation retains the sequential
preliminary and normal-read transformations, without any DMA-order policy.

The [test plan](../../../../src/dv/dma/README.md) owns the independent word
oracle, invalid-row cases and actual output/mask faults. This component does
not satisfy transfer, storage composition or full corruption timing acceptance.
