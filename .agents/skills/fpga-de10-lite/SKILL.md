---
name: fpga-de10-lite
description: Build, constrain, inspect, or explicitly test nand2mario on the DE10-Lite. Use for Quartus, TimeQuest, pins, clocks, and board bring-up; do not program hardware without approval.
---

# FPGA DE10-Lite

Read the board contract and verify the exact target before changing the project.

1. Keep device, clocks, resets, pins, I/O standards, and generated IP explicit.
   Inspect the selected target and generated QSF for physical versus virtual
   ports before choosing a SOF; a diagnostic fit is not a programming image.
2. Constrain every clock and reviewed timing exception.
3. Treat unconstrained paths and unexplained warnings as failures.
4. Record Quartus version, commit, resource use, timing, and artifact hashes.
5. Program or drive physical I/O only with explicit approval and an exclusive
   board lock.

Use [the run record](templates/hardware-run.md) for physical evidence. Read
[the scenarios](examples/scenarios.md) before hardware access. Stop on device,
voltage, wiring, pin, clock, or permission uncertainty.

Follow the [authorized hardware preference](../../../wiki/agents/bootstrap-plan.md#verification-and-hardware-authorization)
for bounded original-game checks. Standing authorization covers routine work
within that scope; verify the documented setup and build before physical access.
Update [verified procedures and pitfalls](examples/scenarios.md#verified-procedures)
from actual tool/CLI/debug results. Record exact commands and tool versions;
distinguish tested procedures from assumptions and link technical board contracts
instead of duplicating them. Correct this skill when verified evidence disagrees.
