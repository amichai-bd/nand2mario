DE2-115 target configurations and constraints belong here. The
[board specification](../../../wiki/src/de2-115-board.md) owns the device, the
pin data and its provenance, and the resources this board has that the other two
do not; nothing here restates them. The
[builder contract](../../../wiki/tools/n2m/SPEC.md#fpga-build) owns commands and
evidence; generated project files and databases stay under the build tag.

`de2-smoke` fits the counter in [`de2_smoke.sv`](de2_smoke.sv) on the board's red
LEDs, clocked by `CLOCK_50` and reset by a synchronized `KEY[0]`. It uses only
pins three or more independent transcriptions state, so the flow proof depends on
no contested assignment. What that provenance does and does not establish is on
the [board specification](../../../wiki/src/de2-115-board.md#pin-data); none of
it is verified against hardware. It proves the Cyclone IV E build path, not board
operation: nothing here has been programmed onto a DE2-115. Each pin declares the
standard the board's
[I/O voltage record](../../../wiki/src/de2-115-board.md#io-voltage-and-what-the-flow-proof-declares)
supplies for it, and that record also names what a programming authorization
still has to confirm physically.
`de2-invalid` deliberately uses a negative clock period and must fail, so a
passing `de2-smoke` fit is evidence rather than an absent check.

`de2-clocking` generates this board's 25 MHz system and 25.2 MHz pixel clocks and
observes them through [`de2_clocking_proof.sv`](de2_clocking_proof.sv) on virtual
ports, under [`de2_clocking.sdc`](de2_clocking.sdc). It has no wrapper of its own:
ALTPLL serves Cyclone IV E, so it instantiates the DE10-Lite's
[`n2m_clocking.sv`](../de10_lite/n2m_clocking.sv) behind the shared reset
controller, and the generation and every clocking check come from that board's
path. A copy here is not an option either way. Keeping the module name fails the
[Questa compile gate](../../../wiki/tools/n2m/SPEC.md#questa-compile-gate): it
compiles every registered source into one library in one `vlog`, warns
`vlog-2275 Existing module 'n2m_clocking' ... will be overwritten`, and fails on
any warning. Renaming forks the fitted instance hierarchy every clocking check
and constraint names, which is what the Cyclone V wrapper costs. `de2-clocking-invalid` shares its sources and names the Cyclone V Altera
PLL's system clock as a checked endpoint, which no Cyclone IV E netlist contains,
so it must fail.

`de2-vga` puts the existing pixel path on the board's ADV7123 video DAC through
[`de2_vga_proof.sv`](de2_vga_proof.sv), under [`de2_vga.sdc`](de2_vga.sdc). It
instantiates the same `u_clocking`, `u_timebase` and `u_bridge` the MAX 10
`vga_proof` fits, in the same hierarchy, so every clocking and frame-bridge check
is that board's; what this top owns is the board side. The four-to-eight bit
alignment and the values the DAC's clock, blank and sync inputs are held at, with
the vendor sources for each, are on the
[board specification](../../../wiki/src/de2-115-board.md#driving-the-vga-dac); the
[builder contract](../../../wiki/tools/n2m/SPEC.md#de2-115-video-dac) owns what
the fit checks. `de2-vga-invalid` shares every source and pin and sources the
generated DAC clock from the Cyclone V Altera PLL's output counter, which no
Cyclone IV E netlist contains, so it must fail. Neither target has been
programmed onto a board and no picture has been observed.

This board reuses what the DE10-Nano had to replace: ALTPLL serves Cyclone IV E
and `altsyncram` places M9K, so there is no `n2m_clocking_*` wrapper and no
memory branch here.

The DE10-Lite remains the qualified board; its physical verification is in
[board bring-up](../../../wiki/src/board-bring-up.md).
