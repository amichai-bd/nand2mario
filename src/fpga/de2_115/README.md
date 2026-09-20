DE2-115 target configurations and constraints belong here. The
[board specification](../../../wiki/src/de2-115-board.md) owns the device, the
pin data and its provenance, and the resources this board has that the other two
do not; nothing here restates them. The
[builder contract](../../../wiki/tools/n2m/SPEC.md#fpga-build) owns commands and
evidence; generated project files and databases stay under the build tag.

`de2-smoke` fits the counter in [`de2_smoke.sv`](de2_smoke.sv) on the board's red
LEDs, clocked by `CLOCK_50` and reset by a synchronized `KEY[0]`. It uses only
pins three or more independent transcriptions state, so the flow proof depends on
no contested assignment. What that provenance does and does not establish is on
the [board specification](../../../wiki/src/de2-115-board.md#pin-data); none of
it is verified against hardware. It proves the Cyclone IV E build path, not board
operation: nothing here has been programmed onto a DE2-115. Each pin declares the
standard the board's
[I/O voltage record](../../../wiki/src/de2-115-board.md#io-voltage-and-what-the-flow-proof-declares)
supplies for it, and that record also names what a programming authorization
still has to confirm physically.
`de2-invalid` deliberately uses a negative clock period and must fail, so a
passing `de2-smoke` fit is evidence rather than an absent check.

`de2-clocking` generates this board's 25 MHz system and 25.2 MHz pixel clocks and
observes them through [`de2_clocking_proof.sv`](de2_clocking_proof.sv) on virtual
ports, under [`de2_clocking.sdc`](de2_clocking.sdc). It has no wrapper of its own:
ALTPLL serves Cyclone IV E, so it instantiates the DE10-Lite's
[`n2m_clocking.sv`](../de10_lite/n2m_clocking.sv) behind the shared reset
controller, and the generation and every clocking check come from that board's
path. A copy here is not an option either way. Keeping the module name fails the
[Questa compile gate](../../../wiki/tools/n2m/SPEC.md#questa-compile-gate): it
compiles every registered source into one library in one `vlog`, warns
`vlog-2275 Existing module 'n2m_clocking' ... will be overwritten`, and fails on
any warning. Renaming forks the fitted instance hierarchy every clocking check
and constraint names, which is what the Cyclone V wrapper costs. `de2-clocking-invalid` shares its sources and names the Cyclone V Altera
PLL's system clock as a checked endpoint, which no Cyclone IV E netlist contains,
so it must fail.

`de2-vga` puts the existing pixel path on the board's ADV7123 video DAC through
[`de2_vga_proof.sv`](de2_vga_proof.sv), under [`de2_vga.sdc`](de2_vga.sdc). It
instantiates the same `u_clocking`, `u_timebase` and `u_bridge` the MAX 10
`vga_proof` fits, in the same hierarchy, so every clocking and frame-bridge check
is that board's; what this top owns is the board side. The four-to-eight bit
alignment and the values the DAC's clock, blank and sync inputs are held at, with
the vendor sources for each, are on the
[board specification](../../../wiki/src/de2-115-board.md#driving-the-vga-dac); the
[builder contract](../../../wiki/tools/n2m/SPEC.md#de2-115-video-dac) owns what
the fit checks. `de2-vga-invalid` shares every source and pin and sources the
generated DAC clock from the Cyclone V Altera PLL's output counter, which no
Cyclone IV E netlist contains, so it must fail. Neither target has been
programmed onto a board and no picture has been observed.

`de2-system` composes the whole Game Boy onto this board through
[`de2_system_proof.sv`](de2_system_proof.sv), under
[`de2_system.sdc`](de2_system.sdc), with its program carried in the bitstream and
no host connection of any kind. It instantiates `n2m_clocking` and
`n2m_v05_system` unchanged, so every clocking, memory, CPU, pixel-path and
endpoint check belongs to the module that owns it; what this top owns is the board
side — the picture on the same DAC pins `de2-vga` drives, the controls on this
board's `KEY` and `SW`, the readout on its eight seven-segment digits through
[`de2_hex_digit.sv`](de2_hex_digit.sv), and the termination of the host UART and
SDRAM this bench does not have. The readout and control scheme is on the
[board specification](../../../wiki/src/de2-115-board.md#the-on-board-readout) and
the [builder contract](../../../wiki/tools/n2m/SPEC.md#carried-rom-image) owns the
carried image. `de2-system-invalid` shares every source and every pin and understates the
readout's constrained endpoint count by one — 57 where the target places 56 digit
pins and two status outputs — so the builder's own generated collection check
fails by name inside the fitter: `Error (332000): checked endpoint count mismatch:
ports_0`, quoting the `if {[get_collection_size $ports_0] != 57} {error …}` the
builder wrote. `read_sdc` then reports `Critical Warning (332008)` and the fitter
cannot place a design it has no constraints for, so `Error (171000): Can't fit
design in device` follows; both errors belong to the control. That is a builder
check rather than a vendor diagnostic, which is what `de2-vga-invalid` has to
settle for, and it guards the figure this target can actually leave stale: add or
drop a readout pin and the count is what goes wrong. Moving a pin onto an
unrecorded package pin would refuse earlier still, but it refuses when the target's
definition resolves, and every consumer that walks the registry resolves each
definition — so the compile gate would fail on its own enumeration instead of on
the build the control exists for. That refusal is covered by mutating a definition
in the unit tests.

**What this board needed from the composition, and why.** `n2m_v05_system` was not
board-independent: it reaches `altera_onchip_flash` through `n2m_boot_copier` and
`n2m_flash_reader`, parameterized `DEVICE_FAMILY("MAX 10")` and
`PART_NAME("10M50DAF484C7G")`, so a device without that internal flash could not
synthesize it at all. And nothing on a board with no host establishes the profile,
the input source, the power-up core reset or the release of host pause, so an image
that fitted and carried its ROM would still never execute an instruction. The
composition now takes two parameters for exactly that, both defaulting to the
DE10-Lite's behaviour, and this target sets both; the
[composition contract](../../../wiki/src/rtl/system/MAS_system.md#host-free-composition)
owns them. A fit cannot see the second half, so the
`host-free-boot` simulation is what proves the core starts.

This board reuses what the DE10-Nano had to replace: ALTPLL serves Cyclone IV E
and `altsyncram` places M9K, so there is no `n2m_clocking_*` wrapper and no
memory branch here.

The DE10-Lite remains the qualified board; its physical verification is in
[board bring-up](../../../wiki/src/board-bring-up.md).
