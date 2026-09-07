---
name: fpga-de10-lite
description: Build, constrain, inspect, or explicitly test nand2mario on the DE10-Lite. Use for Quartus, TimeQuest, pins, clocks, and board bring-up; do not program hardware without approval.
---

# FPGA DE10-Lite

Read the board contract and verify the exact target before changing the project.

1. Keep device, clocks, resets, pins, I/O standards, and generated IP explicit.
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
