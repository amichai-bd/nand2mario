# Timer checks

Contract: [MAS_timer](../../../wiki/src/rtl/timer/MAS_timer.md).

`timer-reload` composes the actual timer and interrupt owner. Eight original
schedules inspect every tick after DIV reset, comparing literal TIMA values,
the reload request before B, and stored IF after B. TIMA writes occur at
124/128/132/136; TMA writes at 128/132/136/140. The expectations derive from
public source instruction timing, not DUT counters or next-state values.

Actual counter and request faults leave expectations unchanged and must cause
the intended nonzero mismatch. Initial reload/counter/request runs passed their expected outcomes; exact
records are retained in [PR146](https://github.com/amichai-bd/nand2mario/pull/146).

`timer-edges` checks the full 65,536-enable DIV wrap, all four timer periods,
all TAC read bytes, nine boundary witnesses, DIV resets for every selectable
bit and all 16 enabled mux changes at two independently specified divider
positions. It then pauses immediately before a fall, holds a pending reload
through qualified STOP gating, checks DIV/TAC writes at reload, repeated TMA FF
requests through the actual IF owner, ten reset boundaries and committed reads.
The 67-case positive and intended faults passed; PR146 retains exact producing
sources, commands and independent evidence. No HALT signal enters the timer: continued
enables exercise its ongoing time, while absent enables exercise host pause
and the enclosing STOP contract. These are owner-boundary tests, not whole CPU
or analog restart execution. The actual TAC-state fault must miss an expected
edge; an invalid untimed commit must fire the named local assertion.

## Actual v0.5 timer program

`program234.py` builds an original ROM through the existing assembler, linker
and packager, checks literal instruction bytes and a declared image hash, and
writes all 26 expected retirement fields from an explicit instruction table.
It targets the actual `n2m_v05_system`, not the separate smoke composition.

DIV reads at completed dots320/348 return01/00 around its reset at336.
Disabled TIMA/TMA/TAC readbacks are3C/42/F8. The final DIV write commits at536;
its instruction retires540. TAC04 selects a1024-dot period. Overflow1560,
reload1564, next-T3 recognition/wake1568 and the five-M-cycle IRQ event1588
follow the timer and CPU contracts. HALT retires552 and produces no idle records.
The original TIMER-vector handler `3E7B EA10C0 D9` writes the RAM marker at1608
and returns at1628. TAC is disabled at1644, while its selected divider bit is
low; TIMA remains42. The program reads the marker, clears IE, enables LCDC91
at1712 and enters CPU HALT at1720.

The pixel witness uses zero-filled profile VRAM/BGP and the existing startup
source schedule: row0 first dot is LCD commit+93, row1 is+548, then456 dots per
line. It checks bounded ordered source pixels and a final public host pause,
not a complete frame, full v0.5 interval milestone or physical display.
'
`python-v05-timer` runs this original image on the actual composition through
continuous Python, current Client commands and validated Intel preloading.
Public loader commands establish the metadata and scan the full ROM CRC; this
is preloaded execution, not a wire upload/readback claim. The checker records
all retirements and consumed timer/marker bus transactions, verifies ordered
pixels through final pause, and checks early tick progress while the CPU sleeps.

`python-v05-timer-fault` forces the actual timer read route to zero without
changing expectations. The first DIV read must fail at retirement index70,
completed dot324, with A expected01 and actual00. This is a failing Python/XML
test and nonzero outer builder result; the actual simulator exit remains zero.
The failed result stays FAIL as evidence of the intended defect detection.
