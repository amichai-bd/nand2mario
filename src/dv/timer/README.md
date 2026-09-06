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
