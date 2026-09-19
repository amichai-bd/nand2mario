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

This board reuses what the DE10-Nano had to replace: ALTPLL serves Cyclone IV E
and `altsyncram` places M9K, so there is no `n2m_clocking_*` wrapper and no
memory branch here. No target generates a clock yet; the flow proof runs from the
50 MHz reference directly, as `nano-smoke` does.

The DE10-Lite remains the qualified board; its physical verification is in
[board bring-up](../../../wiki/src/board-bring-up.md).
