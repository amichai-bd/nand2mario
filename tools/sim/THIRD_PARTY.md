# Simulation tool provenance

| Tool | Pin and source | License | Use |
|---|---|---|---|
| Icarus Verilog 12.0 | [4fd5291632232fbe1ba49b2c26bb6b2bf1c6c9cf](https://github.com/steveicarus/iverilog/tree/4fd5291632232fbe1ba49b2c26bb6b2bf1c6c9cf) | [GPL-2.0-or-later; component exceptions](https://github.com/steveicarus/iverilog/blob/4fd5291632232fbe1ba49b2c26bb6b2bf1c6c9cf/COPYING) | Hosted compile, elaboration, and simulation; downloaded under ignored `workdir/tools/` |
| Questa Altera Starter FPGA Edition 2025.2 | Vendor installation from Quartus Prime Lite 25.1std | Proprietary; user-provided license required | Local independent simulator; no redistribution |

CI uses Ubuntu 24.04's host C/C++ toolchain, autoconf, bison, flex, and gperf to
build the pinned Icarus source. These are provisioning dependencies, not HDL
imports. No reference RTL, external testbench, ROM, or asset is included.
The project license decision remains open in [GAP-002](../../wiki/preflight-gaps.md#gap-002-license-rom-policy-and-provenance).
