# OAM DMA and access arbitration

Status: contract preparation for [#132](https://github.com/amichai-bd/nand2mario/issues/132).
The four digital compatibility projections below are adopted under the user's
delegation. The pure corruption component has bounded reviewed Questa evidence;
transfer and composed arbitration acceptance remain incomplete.

## Ownership and boundaries

This owner schedules FF46 transfers and DMG-B OAM corruption. It uses the
single [memory store](../memory/MAS_memory.md), the CPU's
[typed address effects](../cpu/MAS_cpu.md#internal-address-observation), and
the PPU's [scan and fetch port](../ppu/MAS_ppu.md#oam-scan-and-fetch-port).
There is no second OAM image or retirement-based reconstruction of CPU effects.

All state uses clk_sys. The shared [clock contract](../../clocks-resets-cdc.md)
owns gb_tick and the eleven/twelve-system-edge dot spacing. The exported CPU
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

These MIT-licensed tests report verified model scope. Their sources and notice
are retained with hashes; they have not been executed locally for this issue.

## Corruption qualification and service proposal

The pinned [corruption specification](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/OAM_Corruption_Bug.md)
defines read, write and combined read/IDU transformations on twenty eight-byte
rows. Row0 is protected. The combined preliminary transformation applies only
to rows4-18, followed by normal read corruption. Ordinary writes plus an IDU
write count as one write class. Qualify ordinary and additional addresses
separately, including FEA0-FEFF. Reject unresolved or incomplete-high-mask
effects; consume only the CPU's accepted T4 sample.

The following schedule is reviewed for corruption alone, not complete DMA
arbitration. Ordinary line reset is T1; the scanner captures even objects on
T3 and odd objects on the next T1. At T4, row r is pre-edge scan_index divided
by two. The next consumer needs current-row word2. Initial LCD startup has no
enabled scan until the first line reset. Delayed readable STAT is not the
qualification signal.

Let A be accepted T4. The maximum combined transformation writes three rows.
Source operands are the previous row's eight bytes, the row-before-previous
first word and the current first word. They are prepared before A.

| System edges after A | Raw byte-port operation |
|---|---|
| 1-2 | Write current row bytes4-5, the next object's Y/X. |
| 3-8 | Write current row bytes0-3 and6-7. |
| 9-16 | Write previous row bytes0-7. |
| 17-24 | Write row-before-previous bytes0-7. |
| 25-32 | Read current row bytes0-7 for the next event. |
| 33-34 | Read previous row bytes0-1 for the next event. |
| 35-36 | Read next row bytes0-1. |
| 37 | Capture the last registered response. |

The minimum M-cycle interval is 47 system edges. Prior writes finish before
next operands are read, preserving consecutive-event coherence. Shorter
classes write only the current row. No speculative write is authorized by
prefetch. Operands and pending results are transaction registers, not a second
authoritative store. Preparation continues when no CPU effect is sampled.

Suppress a raw PPU B-port read only when it collides with a same-pair A write;
restore the registered pair before its consuming dot. The first word2 writes
finish at edge2, allowing a fresh read at edge3 before the next T1. Preserve
the previous request's tag and validity. CPU read response/tag storage must
also be independent of raw A-port reuse.

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

Source requests are side-effect-free preparation and persist during pause.
Only a qualified T4 consumes the response. A missing promised response cancels
that edge's byte write and advancement, raises a named assertion and latches
fault; later requests and effects stay suppressed until reset. Neither reset
path clears VGA state. The arbiter supplies pre-edge source data and owns all
physical OAM writes and the held pair; the sequencer adds no backing store.

## Remaining implementation and proof

The combined CPU/DMA/corruption service schedule must preserve the previous
PPU request's response, avoid Intel mixed-port collisions, and independently
tag CPU responses while reusing the raw port. Accepted service may finish
while ticks pause; reset cancels unfinished work. LCD transitions and all
four adopted projections require composed independent checks.

Full acceptance requires original transfer/time, all corruption classes/rows,
concurrent CPU/PPU, reset/pause/HALT/STOP and deliberate actual fault fixtures
against the shared Intel store. A normal copy or pure formula alone is not
acceptance. The finite map and source hashes remain in author artifacts.

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
