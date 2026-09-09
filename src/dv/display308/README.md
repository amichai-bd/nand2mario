# Original DMA and HUD sequence

This diagnostic owns the scoped #308 proof. It does not change gameplay or
claim physical VGA acceptance. The planned alignment owner is
[the SML1 contract](../../../wiki/src/sw/springtrail/sml1-alignment.md).

## Frozen stimulus and image

Use the existing 25 MHz composed system, normal five/six system edges per DMG
dot and actual Intel RAM preload. Original 32 KiB code initializes the LCD-off
scene, a C000-aligned 160-byte shadow OAM page and an HRAM routine. LCDC is 93:
LCD/BG/OBJ enabled, unsigned tiles, 9800 map, 8x8 objects, window disabled.
BGP/OBP0/OBP1 are E4. Map cell (column,row) is (column+row) modulo4;
tiles0..3 contain their literal constant shade. Initialize all map cells fetched
by the first32 lines, including the eight-pixel scroll margin.

Normal-frame rows0..15 use SCX=SCY=0. Rows16..31 use SCX=SCY=8.
Thus the background shade is ((x//8)+(y//8)) modulo4 above the split and
((x//8)+(y//8)+2) modulo4 below it. These coordinates are fixed before
execution; observed interrupt or CRC values never select an expected row.

Tile4 has low/high bytes AA/00 on every row. Tile5 is00/FF. Tile6 has
low byte80 on rows0..2 and00 otherwise, with high byteFF. The five literal(Y,X,tile,flags)
entries are (36,24,4,0), (36,28,5,0), (36,28,6,0), (36,40,5,80),
(36,64,6,60), with flags written in hexadecimal. This covers overlapping objects with lower-X and equal-X
OAM-index priority, transparent color0, BG-priority and X/Y reflection; odd tile
indices distinguish the selected8x8 mode. Remaining entries have Y=0. No object
intersects line15, keeping the HUD-boundary timing independent of object stalls.

## Service order and bounds

Only VBlank and LYC STAT interrupts are enabled (IE3, STAT40, LYC15).
Clear IF explicitly during setup; enable IME and idle in HALT. Expected service
order is first-frame STAT, first VBlank, then next-frame STAT. VBlank cannot be
pending at either line15 request: its prior service must have completed in
VBlank, and the next request is at line144. Check that ordering rather than
assuming priority cannot interfere.

The STAT handler saves AF, polls readable mode until HBlank, commits SCX8 then
SCY8, restores AF and RETI. The selected line15 has no window/fine-scroll/object
stalls before the split. Let B be its normal line start. The independent bound
for the two scroll commits is B+280..B+352, after all160 line15 pixels and before
the line16 mode2/map-fetch boundary. The frozen polling tail is `LDH A,[FF41]` (12), `AND A,3` (8),
`JR NZ,wait` (12 taken/8 untaken), `LD A,8` (8), `LDH [FF43],A` (12),
`LDH [FF42],A` (12). Parentheses are instruction dots. Between consecutive
mode-read T4 commits there are32dots. From the final read T4 to SCX T4
there are36dots and to SCY T4 there are48dots (A remains8).

For B = LCD-enable T4 + frame*70224 +15*456, the selected LY/comparison
projection requests LYC15 at B-1. A request generated at T3 cannot be consumed
by that same pre-T3 snapshot. HALT wake is no later than B+4; five-M-cycle
entry ends by B+24, vector JP costs16 and PUSH AF16. The first mode-read T4
is therefore by B+68, well after the early mode2 transition and before mode3
ends. No active instruction completion adds latency because the main loop is
already halted; the checker must confirm it.

The unstalled line emits its160 pixels at B+92..B+251. The selected readable
HBlank transition is conservatively bounded B+248..B+256, allowing its one-M-cycle visibility
projection rather than equating raster LY and readable mode. The qualified
`src/dv/ppu/tb_ppu_access.sv` brackets mode3 at elapsed704 and mode0 at708
on line1 (nominal B456); the enlarged bracket includes commit numbering. One missed poll
adds at most32dots: latest SCY = B+256+32+48 = B+336. The declared broader
B+280..B+352 check encloses both writes, and is104dots before the next line
start (its first map/Y sample is later, after mode2). This projection and the
actual encoded tail require independent pre-run review; no observed timing
will be used to move the row split. The checker will retain request, vector entry, readable
mode polling, both writes and RETI, not merely the final picture.

VBlank resets both scroll registers to0 and calls the copied HRAM routine.
FF46=C0 starts one transfer: bytes0..159 at trigger+8+4*i, physical stores follow
the existing edge13 projection. HRAM code waits at least644dots after trigger
before returning to ROM; all instruction fetches during ownership are HRAM and
stack accesses remain HRAM. Check all160 source/data/destination transactions,
physical writes and CPU resume, using #239's qualified owner observations.

## Finite acceptance

1. Pure host anchors check literal tiles/OAM priorities and the row15/16 split;
   verify assembly bytes and static instruction/service bounds independently.
2. Short complete harness: preload/adopt, RUN, startup observations, actual final
   HALT, settled no-progress and completed XML. Stop before the first IRQ.
3. Positive: every startup blank pixel plus every pixel of normal rows0..31,
   one complete DMA, both STAT services and ROM resume, then real host HALT.
4. One actual LYC15-to16 fault at the accepted PPU write, unchanged checker:
   require the named missing/late STAT boundary mismatch. No expected-state edit.

Target120s per simulation and300s aggregate (forecast short25, positive120,
fault35 plus host checks). Hard300s each including prep/check/12s cleanup;
30ms simulated watchdog and flushed progress. Freeze exact program dot bounds
before launch and use short measured throughput to assess the positive. No
historical Tcl path, timing bypass, memory replacement or automatic hardware run.
