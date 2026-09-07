# Original v0.5 acceptance

The [charter](../../project-charter.md#release-acceptance) owns the full release
criteria. This fixture uses the [v0.5 owner composition](../../rtl/system/MAS_system.md),
our software builder and original `src/sw/v05/main.asm`. It does not establish
physical execution or a later release.

## Original program and image

The program disables interrupts and the LCD, assigns SP, IF, IE, scroll and
palette explicitly, and clears all 1024 map bytes and tile 0 through CPU writes.
It creates tile 1 as eight low-plane FF/high-plane00 rows. Map address 9800 holds
a fixed marker; addresses 9900 through 9907 hold the eight input cells.
All other map entries remain tile 0. BGP is E4 and LCDC91; sprites/window are off.

Each VBlank wakes CPU HALT with IE=1 and IME=0. The program selects direction row 20,
reads/inverts/masks its low nibble, then selects action row 10 and packs that
inverted nibble into bits 4–7. Register C retains the complete pressed mask.
The eight low bits are written to eight adjacent tile-map cells in order.
It clears all IF bits before the next HALT. VBlank is therefore no longer
pending at entry; JOYP bit 4 cannot wake through IE=1. No interrupt stack entry,
STOP, timer or DMA operation occurs.

Bits 0..7 correspond to Right, Left, Up, Down, A, B, Select, Start. In a normal
frame the fixed marker covers x0..7/y0..7 at shade 1. A pressed bit i adds
shade 1 at x(8*i)..(8*i+7)/y64..71. Every other pixel is shade 0. The first enabled
frame is the PPU contract's blank frame, with every pixel shade 0.

## Frozen timing and inputs

Dots below count completed enabled ticks, not host wall time. The literal
instruction recipe includes the direct-profile NOP/JP frontend. Setup enables
LCD at C=41984 and retires the first HALT at 42008. No host pause is permitted
from RUN until the full acceptance bound completes; CPU HALT leaves ticks live.

The pinned PPU mapping puts VBlank at C+65662+n*70224. T3 captures it before
wake T4 at C+65664+n*70224. The first following LD A,20 retires eight dots later.
Each complete update contributes 76 retirements; its final HALT is 508 dots after
wake T4. All eight tile writes finish during VBlank, before the next visible fetch.

Normal frame 1 starts at completed dot 112300; pixel(x,y) occurs at
112300+456*y+x+(frame-1)*70224. Its final pixel is D=177667, well before the
60-interval limit. Check startup frame 0 as blank and every pixel of normal
frame 1. The watch interval (D,D+600*70224] then includes exactly normal frames 2
through 601, ending at 42312067. There is no omitted leading/trailing visible
portion in this interval. Every retirement from the direct entry through the
final host pause is checked, including any post-bound command latency.

For transition j=1..18, issue the UART input while running after
D+20*j*70224+20000. The accepted applied-dot reply must fall between that value
and 2000 dots later. This lies during CPU HALT, long before the next VBlank
sample. The new image first appears at normal frame 20*j+3. The frozen masks are:

| j | Mask | Expected action |
|---|---|---|
|1,2|01,00|Right press/release|
|3,4|02,00|Left press/release|
|5,6|04,00|Up press/release|
|7,8|08,00|Down press/release|
|9,10|10,00|A press/release|
|11,12|20,00|B press/release|
|13,14|40,00|Select press/release|
|15,16|80,00|Start press/release|
|17,18|11,00|Right+A press/release|

Input values in this table are hexadecimal. Apply-dot journal entries are
validated against these fixed windows and the observed public input boundary;
DUT register or pixel values never choose expectations. The final HALT command
may occur only after the bound, and must complete within 2000 additional dots,
before the next source frame begins. Observers remain live until that pause.

## Independent checks

`src/dv/v05/program.json` owns original literal bytes and instruction cycles;
`reference.py` applies the program's register/flag effects without reading DUT
instruction decode or choosing the next instruction from an actual trace.
Conditional JR takes 2M when not taken. Every full retirement field and program
write is compared, including IF, IE, input mask, HALT and event timing. PPU
VBlank and JOYP events use their reviewed A/B contracts. No missing or extra
retirement is accepted during sleep.

The source-pixel observer checks each visible pixel directly, including startup
and all intervening frames; immutable snapshots are not the every-frame oracle.
An independent active-system-edge watchdog enforces the timing contract and
rejects reset, host pause or missing progress during the acceptance window.
Full pixel/retirement traces are retained. Public waveform windows cover useful
startup/input/update boundaries without recording clocks for the entire run.

Two fresh software-build tags must produce identical complete images. The real
UART loader must read back that complete image. Actual corrupt-load and producer
pixel mutations must fail for their specified reasons with raw nonzero exits.
The new composed Intel-model and constrained-fit evidence is required. A short
measured diagnostic determines wall/storage bounds before the long run; it does
not replace the 60/600-interval acceptance. Final runtime evidence remains pending.
