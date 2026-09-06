# Memory behavior sources

Read-only references; no upstream implementation or prose is copied into RTL.

- [Pan Docs Memory Map](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Memory_Map.md), CC0-1.0: address regions, exact WRAM echo and DMG unusable-range read distinction.
- [Pan Docs VRAM/OAM access](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Accessing_VRAM_and_OAM.md), same pin/license: access restrictions and ignored blocked writes; its blocked read description alone is not proof of every transition-edge value.
- [Pan Docs OAM corruption](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/OAM_Corruption_Bug.md), same pin/license: FEA0–FEFF can trigger corruption despite having no ordinary store; #132 owns application.
- [Pan Docs MBC1](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/MBC1.md), same pin/license: disabled RAM reads are open bus, often FF but not guaranteed. It is evidence against universal constant-FF assumptions, not an MBC implementation requirement for this direct profile.
- [SameBoy memory](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/memory.c), Expat license under repository LICENSE: corroborates DMG-B accessible unusable reads as zero and ordinary blocked VRAM reads as FF. Absent RAM returns retained bus state; the bus retention implementation explicitly describes itself as approximate. No physical decay constant is inferred from that code.
- At that same pin, `read_high_memory` and `write_high_memory` separate DMG registers from CGB-only addresses and the unused I/O default. `GB_IO_BANK` reads FE OR boot-finished and only permits disabling boot mapping. Retrieved `Core/memory.c` SHA-256: `fca194c0168863086a18a589048c563b094dda44bbb43b438d99c3ebcf31ec63`.
- [SameBoy APU](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/apu.c), same pin/license: `GB_apu_read` mask entries cover unused FF15, FF1F and FF27–FF2F. `GB_apu_write` has no channel operation for those holes; internal bookkeeping is not a CPU-visible backing register. Retrieved SHA-256: `4f440a1ef99f182bbc4b6f6e92b1690ea477f43459a3f74947f695f6d883e51b`.
- The pinned Pan Docs Memory Map **I/O Ranges** section identifies the DMG register ranges, CGB-only ranges and FF50 boot control. Together with the pinned reference's DMG gates and unused/audio masks, it supports the linked memory contract's exact unused-I/O table. This is a source-derived digital contract, not a new measured silicon trace.
- Intel model/device sources and the prohibited mixed-port collision boundary belong to the [shared primitive contract](../common/MAS_memory_primitives.md); the memory owner uses that explicit backend without a separate inferred-RAM policy.

CPU and PPU owner MAS contracts establish digital phase interfaces. Emulated
reference code is not a measured pin trace, and synthetic boundary fixtures
are not evidence of finished peripheral or DMA behavior.

The [memory contract](MAS_memory.md#fixed-unused-io-and-disabled-boot-mapping)
owns the exact unused-I/O/disabled-boot table. Readable-FF write-only audio
registers are behavior-owner registers, not unused addresses. This evidence
does not establish a universal absent-cartridge value. The memory MAS records
the separately approved fixed-FF digital profile approximation.
