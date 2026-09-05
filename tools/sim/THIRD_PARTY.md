# Simulation tool provenance

| Tool | Source and license | Use |
|---|---|---|
| Python | [Pinned version and PSF license](../n2m/dependencies.json) | Host commands and tests; no additional packages |
| Questa | User-installed proprietary Siemens tool; executable versions and hashes recorded per run | Sole supported simulator; licensed runtime required |
| Quartus | User-installed proprietary Intel/Altera tool; version and hashes recorded per build | FPGA synthesis, fit and timing checks |

No proprietary installer or license file is redistributed. Tools are selected
from PATH or an explicit installation directory; commands do not change global
PATH or license settings. Actual execution is required to establish runtime
availability. Older simulator pins and completed evidence remain in repository
history and retained build artifacts; they are not current dependencies.
