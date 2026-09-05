# Simulation tool provenance

| Tool | Pin and source | License | Use |
|---|---|---|---|
| Icarus Verilog | [Shared dependency pin, source, and license](../n2m/dependencies.json) | Defined in that manifest and upstream component headers | Portable compile, elaboration, and simulation; provisioned by the [shared bootstrap](../../wiki/tools/build-system.md#bootstrap) |
| Questa Altera Starter FPGA Edition 2025.2 | Vendor installation from Quartus Prime Lite 25.1std | Proprietary; user-provided license required | Local independent simulator; no redistribution |

CI uses Ubuntu 24.04's host C/C++ toolchain, autoconf, bison, flex, and gperf to
build the pinned Icarus source. These are provisioning dependencies, not HDL
imports. No reference RTL, external testbench, ROM, or asset is included.
Original project material follows the [source policy](../../wiki/tools/provenance.md).
Local changes to these external tools: none. Quartus Prime Lite 25.1std is also
a user-installed proprietary tool; its installation retains the vendor terms
and notices. Neither vendor tool nor license material is redistributed.
