# Memory behavior sources

Read-only references; no upstream implementation or prose is copied into RTL.

- [Pan Docs Memory Map](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Memory_Map.md), CC0-1.0: address regions, exact WRAM echo and DMG unusable-range read distinction.
- [Pan Docs VRAM/OAM access](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Accessing_VRAM_and_OAM.md), same pin/license: access restrictions and ignored blocked writes; its blocked read description alone is not proof of every transition-edge value.
- [Pan Docs OAM corruption](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/OAM_Corruption_Bug.md), same pin/license: FEA0–FEFF can trigger corruption despite having no ordinary store; #132 owns application.
- [Pan Docs MBC1](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/MBC1.md), same pin/license: disabled RAM reads are open bus, often FF but not guaranteed. It is evidence against universal constant-FF assumptions, not an MBC implementation requirement for this direct profile.
- [SameBoy memory](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/memory.c), Expat license under repository LICENSE: corroborates DMG-B accessible unusable reads as zero and ordinary blocked VRAM reads as FF. Absent RAM returns retained bus state; the bus retention implementation explicitly describes itself as approximate. No physical decay constant is inferred from that code.
- [MAX10 Embedded Memory User Guide, document683431](https://docs.altera.com/r/docs/683431/current/max-10-embedded-memory-user-guide/mixed-port-read-during-write-mode?contentId=tgpt9Z4YmYLglXJKzX1Reg), revision2025-12-15, section3.2.2: same-clock mixed-port operation supports old-data output on a read/write address collision. The section was read through the documentation service; direct HTML retrieval returned only its application shell and the old PDF URL failed. No complete-document hash is claimed. This establishes a supported primitive policy, not proof of this project's inferred netlist or timing.

CPU and PPU owner MAS contracts establish digital phase interfaces. Emulated
reference code is not a measured pin trace, and synthetic boundary fixtures
are not evidence of finished peripheral or DMA behavior.
