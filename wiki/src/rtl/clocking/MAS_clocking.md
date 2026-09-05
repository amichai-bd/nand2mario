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

`n2m_reset_control` accepts the system and pixel clocks, raw active-low board
reset, and raw PLL lock. It produces PLL reset, qualified readiness, and the two
asynchronous-assert/synchronous-release domain resets. Initialized state provides
configuration startup. A board release chain controls its qualification counter;
a separate lock sampling chain controls readiness qualification. Domain release
chains consume readiness. Their asynchronous blocks and synchronizer attributes
are specialized reset logic; synchronous register macros must not alter assertion
behavior. Counter release and consumer recovery/removal remain timed after their
respective synchronizers.

The timebase and proof counters also retain asynchronous domain assertion. They
use the documented specialized-block exception in the
[register convention](../../rtl-reference-style.md#product-register-convention);
the ordinary macros deliberately describe synchronous resets only.

The [FPGA wrapper](../../../../src/fpga/de10_lite/n2m_clocking.sv) contains the
generated ALTPLL instance. Vendor files are generated under the build attempt.
The [portable test plan](../../../../src/dv/clocking/README.md) independently
checks control behavior; it does not establish vendor PLL behavior. The shared
[FPGA builder](../../../tools/n2m/SPEC.md) owns generation, dependency tracking,
and retained report validation. Integration, frame ownership, board programming,
and physical acceptance remain separate work.
