# DMG timer

Implementation: [timer owner](../../../../src/rtl/timer/n2m_timer.sv).
The owner implements DIV, TIMA, TMA and TAC for the approved DMG-B digital
model. CPU, interrupt storage and peripheral clock generation remain separate
owners. The [source record](references.md) distinguishes hardware-tested
expectations from source-model phase projections. No external RTL is imported.

## Boundary and state

Use `clk_sys`, asynchronous `reset_sys`, shared core-reset control and
`gb_tick` from the shared timebase. Core reset is generated in the system
domain; this owner combines it with global reset for asynchronous assertion
and immediate output cancellation, matching the shared owner convention. CPU register writes use `io_commit`,
`io_write`, `io_address` and `io_wdata` only at their accepted T4 A edge.
`io_selected` and `io_rdata` provide side-effect-free pre-edge register reads.
Numeric addresses and profile initialization come from generated interfaces.
TAC stores three bits and reads its upper five bits high. Other registers read
all eight bits. Writing DIV ignores the data and resets the complete divider.

A 16-bit divider advances once per enabled T-cycle, wrapping modulo 65536.
Visible DIV is bits 15:8. TAC selections 00/01/10/11 choose divider bits
9/3/5/7, respectively: periods 1024/16/64/256 T-cycles. The reference schematic
uses M-cycle counter units; its bit indices must not be copied directly.
TIMA advances on a falling enabled selected signal, including DMG DIV/TAC
write-induced falls. IE/IME and CPU HALT never gate the timer.

A package owns timer state and the timer request payload; ordinary registers
use shared macros. No RAM, duplicate IF register or interrupt selection cache
is needed. The request is a pulse which rises after the reload A edge and
remains through the following system edge B for the interrupt owner's edge
capture. It clears on the next system edge even while host pause withholds
new emulated enables; no emulated cycle is added.

## Overflow and register priority

An increment from FF produces 00. Four subsequent enabled T-cycles later,
TIMA reloads from TMA and requests the timer interrupt. No interrupt comes from
software writing TIMA alone. A TIMA write before reload cancels the pending
reload/request. During reload the TIMA write is ignored; a simultaneous TMA
write supplies the value loaded into TIMA. DIV/TAC writes do not cancel a
pending reload. Reload/write interactions take priority over ordinary counting.

The old-TMA sentence in the register overview conflicts with the detailed
Pan Docs circuit explanation and the hardware-verified Mooneye TMA-write test.
This owner follows the latter: the same reload-period TMA write changes TIMA.
This is a documented source resolution, not an arbitrary selectable mode.

The digital order at an enabled edge is natural divider advance, then DIV
reset/TAC replacement. Detect a falling selected signal across each step;
at most one increment occurs. This preserves a selected signal which rises
on the natural advance and falls on the following disable/reset. GateBoy's
M-unit divider advances at its A phase, before its EFG CPU write window;
this project projects that order onto accepted T4 writes without asserting
an analog intermediate waveform. TIMA writes and reload still override counting.

For a natural overflow at t=128, reload/request occurs at t=132 and its active
interval ends at t=136. TIMA writes at 124/128/132/136 give later values
80/7F/FE/7F with initial TIMA/TMA FE and a 64-T timer. TMA writes at
128/132/136/140 give 7F/7F/FE/FE. These original schedules follow the pinned
Mooneye instruction timing: after the last DIV write, LD A,H takes 4 T,
each NOP takes 4 T, and LDH write takes 12 T. The four-T active reload interval
follows the detailed circuit explanation; the tests pin its legal T4 boundaries.

## Reset, pause, HALT and STOP

Core/global reset initializes timer storage, divider and reload state from the
zero-filled direct profile and cancels a pending request. Reset overrides a
coincident write, natural edge, reload or STOP request. A CPU read has no effect.

Host pause withholds `gb_tick`; divider and reload progress then hold. HALT has
no timer input and does not suppress elapsed enables. CPU STOP supplies its
reviewed `divider_reset_request` at the execution A edge. The enclosing power
owner withholds future enables until its qualified normal wake, independently
of host pause. This timer does not invent oscillator settling time or choose
the CPU's unresolved unstable restart policy.

The divider-reset input affects the divider rather than masquerading as core
reset. Pending TIMA/reload state holds across the stopped interval and resumes on
the remaining supplied enables. SameBoy corroborates this distinction by
returning before timer progression while stopped, without resetting reload
state. Its separately marked uncertain IME0 divider-hold workaround is not
imported. The enclosing power owner remains responsible for qualified enables.

## Independent acceptance

Original public-register fixtures cover all four selections, disabled/enabled
transitions, DIV progress/wrap, DIV/TAC edge effects, normal count and overflow,
each write/reload boundary, and exact request timing. Expectations use elapsed
enables, literal schedules and independently derived tables, never private DUT
counter/next-state values. Include both reset paths, pause/resume, continued
HALT time, reviewed STOP reset/gating and no duplicate request after resume.
Compose the actual interrupt owner for the post-A/B request path.

Actual counter/edge and reload/request faults must produce intended nonzero
Questa failures. Include a named local assertion failure. Retain exact sources,
commands, tool identities, register/event CSV and public waves. External suite
execution, whole CPU execution and physical accuracy are not claimed here.
