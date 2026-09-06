# Timer checks

Contract: [MAS_timer](../../../wiki/src/rtl/timer/MAS_timer.md).

`timer-reload` composes the actual timer and interrupt owner. Eight original
schedules inspect every tick after DIV reset, comparing literal TIMA values,
the reload request before B, and stored IF after B. TIMA writes occur at
124/128/132/136; TMA writes at 128/132/136/140. The expectations derive from
public source instruction timing, not DUT counters or next-state values.

Actual counter and request faults leave expectations unchanged and must cause
the intended nonzero mismatch. First runtime remains pending. Frequency,
DIV/TAC edge, wrap, reset/pause/HALT/STOP and named assertion acceptance remain
unfinished under #128; this fixture does not claim whole timer completion.
