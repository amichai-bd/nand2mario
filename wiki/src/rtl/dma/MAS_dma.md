# OAM DMA and access arbitration

Status: contract preparation for [#132](https://github.com/amichai-bd/nand2mario/issues/132).
The complete arbitration contract is not frozen. No implementation or runtime
acceptance is claimed.

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

## Remaining contract gates

- Exact startup, source sampling, destination write and finish T-edges.
- CPU region conflict values and write effects, including FF46 exceptions;
  HRAM-only programming advice does not define a complete bus truth table.
- DMA versus corruption priority and invalidation of prefetched operands.
- DMA data presented to the PPU during phase2 fetch, with primitive collision
  avoidance and exact prior-request response semantics.
- The combined CPU/DMA/corruption service schedule, pause after acceptance,
  reset cancellation and LCD transition cases.
- HALT-specific DMA progression: continuous PPU ticks and CPU phase do not
  prove continuous transfer. The pinned gate model qualifies DMA clocks with
  CPU clock request; the corroborating emulator stops DMA while halted.

Phase research uses [GateBoy DMA](https://github.com/aappleby/metroboy/blob/36797ad4cf77b3e04ffe45716218a79b5280076a/src/GateBoyLib/GateBoyDMA.cpp)
and its [OAM bus](https://github.com/aappleby/metroboy/blob/36797ad4cf77b3e04ffe45716218a79b5280076a/src/GateBoyLib/GateBoyOamBus.cpp).
These are research references, not imported code or measured silicon traces.
The CPU clock-request gating must be mapped explicitly before using any
emulator's elapsed-cycle shortcut.

No affected RTL begins before these gates are reconciled. The finite issue
acceptance map and exact source hashes are retained with the author artifacts.
Full acceptance requires original independent transfer/time, all corruption
classes/rows, concurrent CPU/PPU, reset/pause/HALT/STOP and deliberate actual
fault fixtures against the shared Intel store. A normal copy alone is not
acceptance.
