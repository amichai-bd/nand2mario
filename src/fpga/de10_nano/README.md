DE10-Nano target configurations and constraints belong here. The
[board specification](../../../wiki/src/de10-nano-board.md) owns the device, the
pin data and its provenance, and the resources this board lacks against the
DE10-Lite; nothing here restates them. The
[builder contract](../../../wiki/tools/n2m/SPEC.md#fpga-build) owns commands and
evidence; generated project files and databases stay under the build tag.

`nano-smoke` fits the counter in [`nano_smoke.sv`](nano_smoke.sv) on the board
LEDs, clocked by `FPGA_CLK1_50` and reset by a synchronized `KEY[0]`. It uses
only pins three or more independent sources attest, so the flow proof depends on
no contested assignment. It proves the Cyclone V build path, not board
operation: nothing here has been programmed onto a DE10-Nano.
`nano-invalid` deliberately uses a negative clock period and must fail, so a
passing `nano-smoke` fit is evidence rather than an absent check.

This board has no pixel or system PLL target. ALTPLL does not serve Cyclone V,
and the PLL evidence in [`fpga_pll.py`](../../../tools/n2m/fpga_pll.py) and
[`fpga_lock.py`](../../../tools/n2m/fpga_lock.py) asserts ALTPLL hierarchy and
MAX 10 report fields throughout, so `nano_smoke` runs from the 50 MHz reference
directly. The DE10-Lite remains the qualified board; its physical verification
is in [board bring-up](../../../wiki/src/board-bring-up.md).
