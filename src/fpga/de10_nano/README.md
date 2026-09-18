DE10-Nano target configurations and constraints belong here. The
[board specification](../../../wiki/src/de10-nano-board.md) owns the device, the
pin data and its provenance, and the resources this board lacks against the
DE10-Lite; nothing here restates them. The
[builder contract](../../../wiki/tools/n2m/SPEC.md#fpga-build) owns commands and
evidence; generated project files and databases stay under the build tag.

`nano-smoke` fits the counter in [`nano_smoke.sv`](nano_smoke.sv) on the board
LEDs, clocked by `FPGA_CLK1_50` and reset by a synchronized `KEY[0]`. It uses
only pins three or more of the transcribed pin sources state, so the flow proof
depends on no contested assignment. What that provenance does and does not
establish is on the [board specification](../../../wiki/src/de10-nano-board.md#pin-data);
none of it is verified against hardware. It proves the Cyclone V build path, not board
operation: nothing here has been programmed onto a DE10-Nano.
`nano-invalid` deliberately uses a negative clock period and must fail, so a
passing `nano-smoke` fit is evidence rather than an absent check.

`nano-clocking` generates this board's system and pixel clocks. ALTPLL does not
serve Cyclone V, so
[`n2m_clocking_cyclonev.sv`](n2m_clocking_cyclonev.sv) instantiates the Altera
PLL IP instead and presents the same interface to `n2m_reset_control` as the
MAX 10 wrapper does; `nano_clocking_proof` fits it with the shared timebase on
virtual control and observation ports.
[`fpga_pll_cyclonev.py`](../../../tools/n2m/fpga_pll_cyclonev.py) and
[`fpga_lock_cyclonev.py`](../../../tools/n2m/fpga_lock_cyclonev.py) own that
family's generation and evidence, selected by
[`fpga_clocking.py`](../../../tools/n2m/fpga_clocking.py).
`nano-clocking-invalid` names a MAX 10 ALTPLL clock as a checked endpoint and
must fail. The DE10-Lite remains the qualified board; its physical verification
is in [board bring-up](../../../wiki/src/board-bring-up.md).
