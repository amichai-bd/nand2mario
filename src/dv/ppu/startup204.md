# Early VRAM read boundary

The original `startup204.py` program initializes8000 to00, enables LCDC81 at
dot80, executes131NOPs and accesses8000 at dot612 (enable+532). Read retirement
is616. The read expectsFF; the write stores81 and verifies it after LCD disable
at636. READ ends with142 records/HALT620; WRITE with145/HALT644. Every retirement
has all26 independently computed fields. This is Intel memory preload followed
by the existing UART metadata/adoption and continuous Python observer, not an
upload or physical proof.

The oracle is the primary Mooneye LCD-on read/write tables pinned in
[startup202](startup202.md), N131: accepted memory T4 is4*N+8 after enable;
retirement follows four dots later. Initial startup+76 permits access. Ordinary
+528/532/536 and+984/988/992 distinguish the directions. The primary reports
DMG/MGB/SGB/SGB2 without a named DMG revision.

Targets: `python-vram-read`, `python-vram-write`, `ppu-vram-read`, and
`ppu-vram-read-corrupt`. The unit covers the paired boundaries, startup,
LCD-off, VBlank, pause and reset. The fault forces the actual read permission
at a preceding negative edge; expected0/1 must become actual1/1.

The original baseline at baae702 fails with accepted bus612 read00 instead ofFF,
while retaining the complete retirement616 before asserting. It remains failed
evidence. Late OAM writes/corruption/arbitration remain[#208](https://github.com/amichai-bd/nand2mario/issues/208),
and raw startup cadence remains[#205](https://github.com/amichai-bd/nand2mario/issues/205).
Neither this test nor its correction completes[#88](https://github.com/amichai-bd/nand2mario/issues/88).
