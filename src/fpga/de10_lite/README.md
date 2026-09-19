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
[`n2m_clocking.sv`](n2m_clocking.sv) is the ALTPLL wrapper, not just this board's:
ALTPLL serves Cyclone IV E too, so the DE2-115's
[clocking proof](../de2_115/README.md) instantiates this file in place. **Changing
it changes both boards.** It is instantiated rather than copied because a copy
keeping the module name fails the
[Questa compile gate](../../../wiki/tools/n2m/SPEC.md#questa-compile-gate), which
compiles every registered source into one library in one `vlog` and fails on its
`vlog-2275 ... will be overwritten` warning, and a renamed copy forks the fitted
instance hierarchy every clocking check names.

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

`v05`, `v05-board` and `v05-controls-board` also place the
[loader profile](../../../wiki/src/rtl/cartridge/MAS_loader_profile.md): the
[SDRAM controller](../../rtl/storage/n2m_sdram_ctrl.sv) on the DE10-Lite DRAM
pins with the `sdram_clk` generated clock and I/O delays of `sdram-proof`
appended to `v05.sdc` and `controls.sdc`, and KEY1/A7 as the return-to-menu
button with its checked two-flop synchronizer. The builder applies the
`sdram-proof` DRAM drive strength, pin clock exception and routed-clock
diagnostic to every image pinned to `DRAM_CLK`. The same three images place
the [boot copier](../../rtl/storage/n2m_boot_copier.sv) with the flash reader
and the On-Chip Flash IP under `u_system|u_copier|u_reader`, so they carry the
`flash-proof` IP staging, configuration mode, UFM block check and classified
strobe-clock and read-only-mode diagnostics as well
([flash library contract](../../../wiki/src/rtl/storage/MAS_flash_library.md)).
The builder names its [library image](../../../wiki/tools/n2m/SPEC.md#flash-library-image)
on that reader instance, so their `.pof` holds the library; without it the
flash reads erased and the copier skips to `DONE`.

`v05-board` uses that composition with physical UART RX D0/AB5, TX D1/AB6,
and KEY0/B8 reset. It retains the VGA pins and clocks above; remaining virtual
outputs are diagnostic observations. The builder supplies and verifies the
producing build ID, checks the UART synchronizer and leaves unused package pins
as inputs without pull-ups. A passing board fit is still not physical acceptance:
verify wiring, voltage, device and reviewed evidence before programming, then
record actual bring-up in wiki/src/board-bring-up.md and game acceptance under #88.

`sdram-proof` is the SDRAM bring-up board image: the ported
[SDRAM controller](../../rtl/storage/n2m_sdram_ctrl.sv) on the DE10-Lite DRAM
pins (Terasic pin data, 3.3-V LVTTL), the same parallel system and pixel PLLs
and reset bootstrap as `v05-board`, and the UART endpoint with only the
`SDRAM_WRITE`/`SDRAM_READ` line commands live, so `host sdram-test` can check
the device without the loader or core. `DRAM_CLK` is the inverted 25 MHz
system clock at the pin; `sdram.sdc` declares it as a generated clock and
carries the I/O delays of the [storage contract](../../../wiki/src/rtl/storage/MAS_sdram.md#clock-relationship-and-constraints).
The builder supplies and verifies the `N2M_SDRAM_BUILD_ID` identity, checks
the UART synchronizer chain and leaves unused package pins as inputs. LEDR9
shows clocking ready, LEDR8 SDRAM initialized, LEDR7 controller idle and LEDR6
toggles on every accepted line. Programming and the board memory test are
authorized per session.

`flash-proof` is the flash reader fit: the installed Intel On-Chip Flash IP
(`altera_onchip_flash`, read-only parallel data slave, incrementing burst of 4,
single compressed image mode) behind
[`n2m_flash_reader`](../../rtl/storage/n2m_flash_reader.sv) on the same
parallel system and pixel PLLs and reset bootstrap as `sdram-proof`, walked
continuously over the 736 KiB user range by
[`flash_proof`](flash_proof.sv). The builder copies the four pinned IP source
files into the attempt and sets `INTERNAL_FLASH_UPDATE_MODE "Single Comp
Image"`; the fit must place `UFM blocks : 1 / 1`. KEY0/B8 is the reset and
LEDR9-0 show clocking ready, reader ready, a toggle per pass over the user
range, the pixel-clock heartbeat and the low six bits of a running checksum
of every line read. The builder also assembles the
[flash library](../../../wiki/tools/n2m/SPEC.md#flash-library-image) from
[`library.json`](library.json), names it on `u_reader` and retains the
`design.pof` holding it; reading the flash contents on the board is the later
flash boot check under the
[flash library contract](../../../wiki/src/rtl/storage/MAS_flash_library.md#verification).
