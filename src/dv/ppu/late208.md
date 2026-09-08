# Late OAM write qualification

The [memory contract](../../../wiki/src/rtl/memory/MAS_memory.md#direct-path-late-oam-writes)
owns the direct-path extension. Combined DMA integration remains
[#211](https://github.com/amichai-bd/nand2mario/issues/211).

The [primary LCD-on table](startup202.md) permits a write at enable+532.
The data projection additionally qualifies pinned SameBoy Core
`213a12ce93d66b105a113debd9396306066a7cfc`, `memory.c` allowed A0 write:
transform the addressed row, then apply the CPU byte. The code originated in
`4986930511f28ecfc902cabc9a0839291be75f02`, whose message reports passing
oam_bug-2. That is not a revision-specific trace for this exact write.
Neither source establishes universal silicon data values.

`late208.py` builds three original images through the normal software pipeline.
Each initializes OAM byte i to `(37*i+11)&255` with LCD off, enables LCDC81 at
dot3924, then writes81 to FE9C, FE9D or FE20 at dot4456. The write retires at
4460; HALT retires at4480 after LCD-off. Literal opcodes, whole image hashes
and all624 records of26 fields are fixed independently of the DUT.

| Target | Changed row after the write, hex |
|---|---|
| FE9C | 03 28 4D 72 81 BC E1 06 |
| FE9D | 03 28 4D 72 97 81 E1 06 |
| FE20 | 81 90 4D 72 97 BC E1 06 |

The last row remains unchanged for FE20. Every other byte is also checked.
The actual CPU witnesses observe the next ROM fetch and the live PPU pair78
capture. The Intel unit separately exercises a stronger immediate OAM-read
request; source review qualifies the identical busy, pending and address gates
in both direct paths. These are distinct pieces of evidence.

After actual UART HALT, paused state, LCD-off and idle owner are observed,
the fixture performs a read-only DV inspection through the existing typed
OAM port. It checks each registered response and all160 bytes, then releases
the force. This is not UART readback and cannot substitute for live capture
evidence. The tests use actual Intel preload with public loader adoption;
they do not claim physical hardware or full #88 acceptance.

Targets: `oam-late-write`, `oam-late-write-collision`, `ppu-vram-read`
(first and repeated late indication), and `python-oam-late-fe9c`,
`python-oam-late-fe9d`, `python-oam-late-fe20`. Each is bounded by600 seconds.
