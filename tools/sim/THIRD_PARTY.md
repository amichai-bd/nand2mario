# Simulation tool provenance

| Tool | Source and license | Use |
|---|---|---|
| Python | [Pinned version and PSF license](../n2m/dependencies.json) | Host commands and tests; no additional packages |
| Verilator | [Pinned tag, commit and LGPL-3.0-only OR Artistic-2.0 license](../n2m/dependencies.json); built from source by `tools verilator` into ignored `workdir/tools/verilator/v<version>`, which records its own `installation.json`, or into any operator prefix | Supported Linux simulator; no license consulted; no source or binary is committed |
| Questa | User-installed proprietary Siemens tool; executable versions and hashes recorded per run | Supported native simulator on any host holding its executables; a `vsim` runtime checkout is required, probed and recorded under the [simulator policy](../../wiki/tools/n2m/SPEC.md#questa-runtime-license) |
| Quartus | User-installed proprietary Intel/Altera tool; version and hashes recorded per build | FPGA synthesis, fit and timing checks |
| openFPGALoader | User-installed Apache-2.0 tool, not pinned or vendored here; the release is recorded per operation from its own `--Version` banner. Apache-2.0 established from the `SPDX-License-Identifier` header of every v1.1.1 source consulted, the `LICENSE` file at that tag and the installed package's own metadata | Volatile JTAG configuration where Quartus's `jtagd` cannot read the cable, under the [programming backends](../../wiki/tools/n2m/SPEC.md#programming-backends); it contributes no bytes to any artifact |

No proprietary installer or license file is redistributed. Tools are selected
from an explicit installation directory, then PATH, then the repository's own
[pinned Verilator installation](../../wiki/tools/n2m/SPEC.md#pinned-verilator-installation);
commands do not change global PATH or license settings. Actual execution is required to establish runtime
availability. Older simulator pins and completed evidence remain in repository
history and retained build artifacts; they are not current dependencies.
# Installed Intel memory model

The authoritative supported release and source hashes are in
[`tools/n2m/dependencies.json`](../n2m/dependencies.json), under `intel_memory`.
The unmodified `altera_mf.v` remains in the user's Quartus `eda/sim_lib` directory.
Its header identifies the applicable Altera software/IP agreements and limits
use to Altera devices. Preserve that installed distribution's notices; do not
copy vendor source into the repository. Compiled libraries are generated only
under ignored build tags for MAX 10 simulation. No local source changes.
