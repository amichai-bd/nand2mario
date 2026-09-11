DE10-Lite target configurations and constraints belong here. The
[builder contract](../../../wiki/tools/n2m/SPEC.md#fpga-build) owns commands and
evidence; generated project files/databases stay under the build tag.

`builder-smoke` fits the original eight-bit counter fixture in `src/dv/builder/`.
Only the clock has a package pin; counter outputs are virtual. The clock pin
and nominal 20 ns period follow the [timing contract](../../../wiki/src/clocks-resets-cdc.md).
This fixture proves the tool flow, not board operation or the #79/#80 designs.
`builder-invalid` deliberately uses a negative clock period and must fail.
Neither fixture is a hardware acceptance image.

`clocking-nominal` and `clocking-upper` fit the clocking/timebase proof at the
two reference timing bounds in the shared contract. Their virtual controls and
observation counters are not board assignments. The `clocking-invalid` target
names a missing asynchronous-reset endpoint and must fail the checked SDC
collection; it cannot count as a positive fit. See the
[clocking test plan](../../dv/clocking/README.md) and
[generation/evidence rules](../../../wiki/tools/n2m/SPEC.md#generated-clocking-inputs).

The `ppu_proof` component target connects the actual PPU and VGA bridge. CPU
register and VRAM/OAM response ports are explicitly timed virtual pins; #130
owns backing stores and #132 owns DMA arbitration. These targets establish
component fit/timing, not a complete system or physical monitor result. The
[n2m proof profile](../../../wiki/tools/n2m/SPEC.md#ppu-and-lcd-control-proof-profile)
owns the additional LCD-control crossing and RGB-path evidence.

`v05` places the actual UART/CPU/memory/PPU/JOYP/interrupt/snapshot/VGA
composition. P11 supplies the 50 MHz reference to the real parallel system
25 MHz and pixel25.2 MHz PLLs. Reset bootstrap uses the reference; release is
qualified in each generated domain. UART/control observations remain virtual,
so this target must not be programmed as a board image. The scoped adapter
retains the six bridge synchronizers, exact mailbox bounds and VGA output
reports under `u_system`. Only named asynchronous first stages are excepted;
reset consumers remain timed. A diagnostic fit is not full acceptance until all composed memory,
clock, reset and CDC evidence is checked against the
[system boundary](../../../wiki/src/rtl/system/MAS_system.md).

`v05-board` uses that composition with physical UART RX D0/AB5, TX D1/AB6,
and KEY0/B8 reset. It retains the VGA pins and clocks above; remaining virtual
outputs are diagnostic observations. The builder supplies and verifies the
producing build ID, checks the UART synchronizer and leaves unused package pins
as inputs without pull-ups. A passing board fit is still not physical acceptance:
verify wiring, voltage, device and reviewed evidence before programming, then
record actual bring-up in wiki/src/board-bring-up.md and game acceptance under #88.
