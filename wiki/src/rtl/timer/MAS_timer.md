# DMG timer

Status: planned in [#128](https://github.com/amichai-bd/nand2mario/issues/128).
The owner implements DIV, TIMA, TMA and TAC for the approved DMG-B digital
model. CPU, interrupt storage and peripheral clock generation remain separate
owners. The [source record](references.md) distinguishes hardware-tested
expectations from source-model phase projections. No external RTL is imported.

## Boundary and state

Use `clk_sys`, asynchronous `reset_sys`, synchronous core-reset control and
`gb_tick` from the shared timebase. CPU register writes use `io_commit`,
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

Two detailed projections require source review before affected RTL:

- A natural divider change and a DIV/TAC write can make an intermediate rise
  followed by a write-induced fall. The proposed order is natural advance,
  then write effect, with at most one increment. A simple old-to-final signal
  comparison would miss this case. Pin its T4 relation before implementation.
- Specify the reload-active interval in T enables, including a write exactly
  at each boundary. The tested CPU write phase and the four-T delay must be
  distinguished from a claim about an analog load pulse.

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
reset. Pending TIMA/reload behavior across a stopped interval must be sourced
and explicitly reviewed before that case is implemented; it must not be
silently discarded as though all timer state were reset.

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
