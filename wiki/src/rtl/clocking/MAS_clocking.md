# Clocking and timebase

The [shared clock/reset contract](../../clocks-resets-cdc.md) owns rates,
qualification intervals, tick arithmetic, pause/reset priority, and CDC rules.
This owner implements those rules without duplicating their constants here.

`n2m_timebase` accepts `clk_sys`, asynchronous active-high domain `reset_sys`,
synchronous `core_reset`, and synchronous `pause_request`. `gb_tick` is the
current-edge carry enable; `paused` acknowledges completed pause. Reset leaves
the core paused. Deasserting the pause request leaves pause on that edge; the
next edge is the first active accumulator edge. The host controller must hold
its pause request through acknowledgement. It owns commands and their ordering.

`n2m_reset_control` accepts the always-running reference, generated system and pixel clocks, raw active-low board
reset, and raw PLL lock. It produces PLL reset, qualified readiness, and the two
asynchronous-assert/synchronous-release domain resets. Initialized state provides
configuration startup. A board release chain controls its qualification counter;
a separate lock sampling chain controls readiness qualification. Domain release
chains consume readiness. All clocking state and proof counters use the shared
[asynchronous register macros](../../rtl-reference-style.md#product-register-convention).
The reset controller uses the initialized asynchronous forms: separate constant
`initial` assignments retain configuration values, and edge-triggered `always`
avoids the Questa `always_ff` multiple-process restriction. Declarations retain
register names and synchronizer attributes. Next-state logic preserves reset priority, terminal counter holding,
current-edge carry, pause completion and the resume edge. Counter release and
consumer recovery/removal remain timed after their respective synchronizers.

Named simulation assertions check phase range, known control state, tick masking,
readiness/reset exclusion and terminal/paused holding. The stable checks use prior
control and asynchronously invalidated history. They supplement the independent
public-boundary oracle. Assertion logic is excluded from the FPGA netlist; every
named chain endpoint and asynchronous clear pin remains subject to the existing
fit/timing audit without a topology waiver.

The [FPGA wrapper](../../../../src/fpga/de10_lite/n2m_clocking.sv) contains the
two parallel generated ALTPLL instances. Both take the same board reference;
bootstrap state runs on that reference and cannot depend on a stopped PLL output. Vendor files are generated under the build attempt.
The [portable test plan](../../../../src/dv/clocking/README.md) independently
checks control behavior; it does not establish vendor PLL behavior. The shared
[FPGA builder](../../../tools/n2m/SPEC.md) owns generation, dependency tracking,
and retained report validation. Integration, frame ownership, board programming,
and physical acceptance remain separate work.
