# DE2-115 board

This page owns the DE2-115 board data: its device, the JTAG chain that reaches
it, the resources it has that the other two boards do not, and every pin
assignment this repository uses with its provenance. It is the single source of
that data; [`src/fpga/de2_115/`](../../src/fpga/de2_115/README.md) links here
instead of restating it, as [board bring-up](board-bring-up.md) does for the
DE10-Lite and the [DE10-Nano board](de10-nano-board.md) page does for the Nano.

The DE10-Lite stays the qualified board. Nothing on this page is a physical
DE2-115 result: no image has been programmed onto it, and the only checks behind
it are a read-only JTAG chain detect and a Quartus fit.

## Device

Terasic DE2-115, Intel Cyclone IV E `EP4CE115F29C7`. It is a commercial `C7`
part, so Quartus analyses it at 1.20 V nominal core voltage over a 0 °C to 85 °C
junction range, and its three analysed timing corners are the same three the
DE10-Lite declares. The [`de2-smoke` fit](#targets) reports the device capacity:

| Resource | DE2-115 (`EP4CE115F29C7`) | DE10-Lite (`10M50DAF484C7G`) | DE10-Nano (`5CSEBA6U23I7`) |
|---|---|---|---|
| Logic | 114,480 logic elements | 49,760 logic elements | 41,910 ALMs |
| Block memory | 3,981,312 bits | 1,677,312 bits | 5,662,720 bits |
| Multipliers | 532 9-bit embedded multipliers | 288 9-bit embedded multipliers | 112 DSP blocks |
| PLLs | 4 | 4 | 6 |
| User I/O in this package | 529 | 360 | 314 |
| Internal flash | none | 1 UFM block | none |
| Analog input | none on the FPGA | 2 ADC blocks | none on the FPGA |

Every DE2-115 row comes from the `Fitter Status : Successful` summary of the
local `de2-smoke` fit; the other two columns come from the same summary of
`builder-smoke` and `nano-smoke`, all on Quartus Prime Lite 25.1std.0 Build 1129.

### What this board reuses instead of replacing

This is why the board costs pins and a record rather than a third family
implementation:

- **ALTPLL serves Cyclone IV E.** `qmegawiz -silent module=altpll` with
  `INTENDED_DEVICE_FAMILY="Cyclone IV E"` generates successfully and writes
  `intended_device_family = "Cyclone IV E"` with `lpm_type = "altpll"`, from the
  same generator [`fpga_pll.py`](../../tools/n2m/fpga_pll.py) drives for the
  DE10-Lite. Cyclone V refuses outright — `Wizard ALTPLL supports the following
  list of device families only : MAX 10` — which is why that board needs
  [its own clocking implementation](de10-nano-board.md#resources-this-board-lacks-against-the-de10-lite).
  No target on this board generates a clock yet; the flow proof runs from the
  50 MHz reference directly.
- **M9K serves Cyclone IV E.** `quartus_map` accepts
  [`n2m_intel_ram.sv`](../../src/rtl/common/n2m_intel_ram.sv) unchanged for
  `EP4CE115F29C7`, reporting `Parameter "ram_block_type" = "M9K"` with 0 errors,
  where Cyclone V needed the `N2M_RAM_CYCLONEV` branch for M10K. The wrapper's
  unselected default text also carries
  `intended_device_family = "MAX 10"`, which `quartus_map` accepts as the hint it
  is. No target on this board instantiates the wrapper, so nothing depends on
  that string yet; the first one that does owns whether it should name this
  family.

### Resources this board has that the others do not

Read against the [pin groups](#pin-groups) below, this board carries three things
the DE10-Nano lacks and the DE10-Lite has only in a reduced form:

- A VGA connector driven by an Analog Devices ADV7123 video DAC, with `VGA_R`,
  `VGA_G` and `VGA_B` eight bits wide each, against the DE10-Lite's four-bit
  resistor ladder. The DE10-Nano has no VGA connector at all.
- FPGA-side SDRAM: 128 MB as 32M x 32 bit over two devices, so `DRAM_DQ` is 32
  bits wide, where the DE10-Lite's is 16 bits and the DE10-Nano has none on the
  fabric side.
- An onboard RS-232 port with hardware flow control (`UART_RXD`, `UART_TXD`,
  `UART_CTS`, `UART_RTS`), where the DE10-Nano's UART endpoint has to leave
  through GPIO flying leads.

It also carries about 2.4 times the DE10-Lite's block memory and 2.3 times its logic,
two Gigabit Ethernet PHYs, SRAM, parallel flash, an HSMC connector and the rest
of the [groups below](#pin-groups). Nothing places any of them: this issue's
scope is the flow proof, and a later system image is a separate decision.

## JTAG chain

The chain has **one** device and the FPGA is at **index 0**:

| Index | IDCODE | Device |
|---|---|---|
| 0 | `0x20f70dd` | Cyclone III/IV/10 LP, `EP3C120`/`EP4CE115`/`10CL120` |

`0x20f70dd` is shared across those three parts, so the IDCODE alone narrows the
board to a `EP4CE115`-class device rather than naming the exact ordering code.
The detect was read-only; nothing was programmed.

The onboard USB-Blaster enumerates directly as `09fb:6001` and needs no firmware
load, unlike the DE10-Nano's USB-Blaster II, which is unusable until
`blaster_6810.hex` reaches cable RAM and reverts on every replug.

## Pin data

Every assignment on this page was taken from public Quartus settings files whose
`DEVICE` is `EP4CE115F29C7` and whose `FAMILY` is `Cyclone IV E`, parsed for
`set_location_assignment PIN_<pin> -to <signal>`, and compared against each other
and against the [vendor pin table](#vendor-pin-table).

**What this establishes, and what it does not.** None of these projects measured
the board. Every one of them transcribes Terasic's published pin table, so
agreement between them is strong evidence against a transcription error and no
evidence at all of independent measurement. The pins are unverified against
hardware until something is programmed onto a DE2-115 and observed. Read a source
count as "this many independent transcriptions state it the same way and built
successfully against it", not as "this many measurements agree".

### Source independence

Counting files would overstate the evidence. Seven of the twenty files below are
the same Terasic template `.qsf`, copied into seven unrelated projects: each
assigns the full board — over 490 signals including the HSMC, Ethernet, SRAM and
USB pins no single one of those designs uses — and they agree pairwise on 85% to
100% of their assignments. Two pairs among them are identical over all 525
assignments. They are one transcription, counted once, as group `T`.

The remaining files each assign only the signals their own design drives, in
their own order and formatting, so their overlap is shared board coverage rather
than a shared file. Two files by one author are counted once, as group `E`.

| Group | Repository | File | Commit | Licence | Board signals stated |
|---|---|---|---|---|---|
| `T` | MIPSfpga/mipsfpga-plus | [`boards/de2_115/de2_115.qsf`](https://github.com/MIPSfpga/mipsfpga-plus/blob/98653bb43656542ec92e40068fb85b5e1c741d40/boards/de2_115/de2_115.qsf) | `98653bb` | none stated | 510 |
| `T` | travisg/2stage | [`rtl/de2-115/top.qsf`](https://github.com/travisg/2stage/blob/3e32c7af76226d491eb6fd6f234db6629a6a3145/rtl/de2-115/top.qsf) | `3e32c7a` | MIT | 517 |
| `T` | imr/Mandelbrot-VHDL | [`src/Fractal.qsf`](https://github.com/imr/Mandelbrot-VHDL/blob/d4274bd40391ec29bd9821d7d986d1d366db71fe/src/Fractal.qsf) | `d4274bd` | not recognized | 517 |
| `T` | Rutgers-FPGA-Projects/Camera-Tracking | [`CameraTracking.qsf`](https://github.com/Rutgers-FPGA-Projects/Camera-Tracking/blob/e3b94505a4680b753471a2debf9b4521426dc89b/CameraTracking.qsf) | `e3b9450` | none stated | 516 |
| `T` | evantandersen/fpga-gpu | [`GPU.qsf`](https://github.com/evantandersen/fpga-gpu/blob/f0a4ad610becc3d8e7549eb1e4685a64a64f67f2/GPU.qsf) | `f0a4ad6` | none stated | 501 |
| `T` | anitazha/team_psx | [`psx/system/system_top.qsf`](https://github.com/anitazha/team_psx/blob/11d340cbec4873ca8c2fbde5dc6c1e6b95107795/psx/system/system_top.qsf) | `11d340c` | none stated | 501 |
| `T` | A46006/ZX-Fusion | [`project/ZX_FUSION.qsf`](https://github.com/A46006/ZX-Fusion/blob/7bf286bfa19f3ac1eb8a6f03282a00c0dbebabec/project/ZX_FUSION.qsf) | `7bf286b` | MIT | 491 |
| `B` | marqs85/de2-vd | [`videoproc.qsf`](https://github.com/marqs85/de2-vd/blob/fb4ee132399e0ee52b6771c481430451d15b0535/videoproc.qsf) | `fb4ee13` | GPL-3.0 | 104 |
| `C` | alfikpl/ao486 | [`syn/soc/soc.qsf`](https://github.com/alfikpl/ao486/blob/df6eba123654fdf3e3058c6129d605ce1393e0db/syn/soc/soc.qsf) | `df6eba1` | not recognized | 149 |
| `D` | zzemu-cn/LASER310_FPGA | [`prj_de2_115/DE2_115.qsf`](https://github.com/zzemu-cn/LASER310_FPGA/blob/1fcdae9627867c5d971db10e9d56f6bc3ef572b7/prj_de2_115/DE2_115.qsf) | `1fcdae9` | GPL-3.0 | 19 |
| `E` | filipamator/adpll | [`adpll.qsf`](https://github.com/filipamator/adpll/blob/9255b914d2895b4a55bad84b485f1fbe7aedc527/adpll.qsf) | `9255b91` | none stated | 35 |
| `E` | filipamator/vu_meter | [`vu_meter.qsf`](https://github.com/filipamator/vu_meter/blob/7e3d999194df4be0382b78828b3b8cd72ece5d53/vu_meter.qsf) | `7e3d999` | none stated | 35 |
| `F` | menotti/fpga | [`labs/DE2_115.qsf`](https://github.com/menotti/fpga/blob/2e8a2ec0bb17b451bc37f11330436446b0955d3d/labs/DE2_115.qsf) | `2e8a2ec` | Unlicense | 112 |
| `G` | AmeerAbdelhadi/Dynamic-Frequency-Phase-Sweeping | [`FreqPhaseSweeping.qsf`](https://github.com/AmeerAbdelhadi/Dynamic-Frequency-Phase-Sweeping/blob/dbf2c9905f3173717dbab149023af827a1a8f8ef/FreqPhaseSweeping.qsf) | `dbf2c99` | not recognized | 108 |
| `H` | teknohog/rautanoppa | [`DE2-115/hwrandom.qsf`](https://github.com/teknohog/rautanoppa/blob/2529220500a1836a4b359af5537e818678d66ca6/DE2-115/hwrandom.qsf) | `2529220` | GPL-3.0 | 0 |
| `I` | srodriguez1850/JSInth | [`JSInth.qsf`](https://github.com/srodriguez1850/JSInth/blob/e0defa047ebf92ab58191889ac7a7547ce58417f/JSInth.qsf) | `e0defa0` | MIT | 8 |
| `J` | parallaxinc/Propeller_1_Design | [`P8X32A_DE2_115/top.qsf`](https://github.com/parallaxinc/Propeller_1_Design/blob/f1a65b463d1d0a6b111f633d194d6f5b032eecd6/P8X32A_DE2_115/top.qsf) | `f1a65b4` | none stated | 0 |
| `K` | John-Leitch/fpga-md5-cracker | [`Hardware/DE2_115.qsf`](https://github.com/John-Leitch/fpga-md5-cracker/blob/0d574875dc880c692dfd7b60b946fc00183dd2ec/Hardware/DE2_115.qsf) | `0d57487` | none stated | 23 |
| `L` | coldnew-examples/DE2-115-Led-Blink | [`blink.qsf`](https://github.com/coldnew-examples/DE2-115-Led-Blink/blob/beddc4b5ba67be28028dbbbb873390afc829d923/blink.qsf) | `beddc4b` | none stated | 0 |
| `M` | FPGA-Energy/game-of-live | [`quartus/gol.qsf`](https://github.com/FPGA-Energy/game-of-live/blob/e3dd8072169cec31b4acc00184462e2bc7e3c68b/quartus/gol.qsf) | `e3dd807` | none stated | 0 |

`Board signals stated` counts how many of the vendor table's 517 signal names
that file assigns. The four files that state none of them name only their own
design ports; they support the no-conflict statement without attesting any board
signal, and four of them place a design port on a pin the tables below also name
(`osc_clk`, `clock_50`, `reset_button` and `ledg[n]` among them), which
corroborates the pin without naming the signal.

Only the pin numbers are taken, and a package pin number is a fact about the
board, not an expression any of these projects owns. No source file is copied
into this repository.

One name disagreement exists across all twenty files: ZX-Fusion swaps
`UART_CTS` and `UART_RTS` against every other source and against the vendor
table, which settles it as `UART_CTS` on `PIN_G14`. No other signal name
resolves to two pins anywhere.

**Signals a daughter card defines are not on these tables.** Several sources
assign `HDMI_TX_*`, `D5M_*`, `ADA_*`, `ADB_*`, `AIC_*`, `DA`, `DB`, `NES_*`,
`TFT_*` and `KEYB_*`. Those are Terasic HSMC add-on cards and expansion-header
wiring, not DE2-115 resources, and naming them as board pins would misrepresent
the board. Every one of them resolves to a pin already named below: for example
`HDMI_TX_RD[0]` is `PIN_K22`, which is `HSMC_TX_D_N[6]`, and `NES_CLK_1` is
`PIN_AG23`, which is `GPIO[31]`.

### Vendor pin table

The [DE2-115 user manual](#references) is the published table every source above
transcribes, so it is the primary source rather than a twenty-first
transcription. Its Tables 4-1 to 4-5 and the peripheral tables through section
4.19 give the package pins and, unlike any settings file, the per-signal I/O
standard.

Read row by row against the sources, it states **517** signals and agrees with
the sources on **every one**: 517 agreements, zero disagreements, and no signal
it names is absent from the sources. That is a stronger match than the DE10-Nano
has, and it is still the vendor's published table and not a measurement, so the
caveat above is unchanged: no pin here is verified against hardware.

Terasic's own host could not be reached from the host this page was written on —
`www.terasic.com.tw` fails TLS certificate verification — so the copy read was a
mirrored PDF of the same document, recorded in the [references](#references) with
its digest. Its appendix states version V1.02 and a 2010 copyright.

### I/O voltage, and what the flow proof declares

This is the one place the DE2-115 differs materially from both existing boards,
and it is why each pin's I/O standard is a per-board record rather than a
constant.

The DE10-Lite and DE10-Nano put every pin this repository uses on 3.3 V. The
DE2-115 does not, and the vendor table states it per signal:

| Group | Vendor I/O standard | FPGA bank |
|---|---|---|
| `CLOCK_50`, `CLOCK2_50`, `SMA_CLKIN` | 3.3 V | 2 |
| `LEDR`, `LEDG` | 2.5 V | 7 |
| `KEY`, `SW` | set by header JP7, default 2.5 V | 5, 6 |
| `GPIO` expansion header, `CLOCK3_50`, `SMA_CLKOUT` | set by header JP6, default 3.3 V | 4 |
| RS-232, VGA, SDRAM, SRAM, flash, audio, I2C, PS/2, SD card, USB, `EX_IO` | 3.3 V | various |

JP7 supplies VCCIO5 and VCCIO6 and its default position is 2.5 V; JP6 supplies
VCCIO4 and its default position is 3.3 V. Both are jumper positions read from the
user manual, not readings of this board. So of `de2-smoke`'s ten pins, only
`CLOCK_50` is a 3.3 V pin: `KEY[0]` sits in a bank JP7 powers at 2.5 V in that
default position, and `LEDR[7:0]` sit in a bank the vendor table fixes at 2.5 V.

[`src/fpga/de2_115/targets.json`](../../src/fpga/de2_115/targets.json) records
exactly that, grouping this board's package pins by the standard it supplies, and
[`fpga.py`](../../tools/n2m/fpga.py) takes each assignment from that record, so
`de2-smoke` declares `2.5 V` on those nine pins and `3.3-V LVTTL` only on
`CLOCK_50`. A pin no board record names refuses the build and names itself;
nothing defaults.

The [fit](#targets) reports those banks accordingly: `I/O Bank Usage` gives bank
2 at 3.3 V for `CLOCK_50`, bank 6 at 2.5 V for `KEY[0]` and bank 7 at 2.5 V for
`LEDR[7:0]`, and its per-pin tables give `2.5 V` on all nine.

**What that settles, and what it does not.** The project file now states the
board's documented voltage instead of one the board does not supply. It remains a
Cyclone IV E build-path result and not a board image. The 2.5 V on `KEY[0]` is
JP7's documented default position, so reading JP7 on this board belongs to the
programming authorization along with the rest of physical verification. Nothing
has been programmed onto a DE2-115.

## Pin groups

All 517 signals the vendor table states, with how many independent
transcriptions above state each. A group's range covers its weakest and strongest
signal. Only the groups the flow proof uses are enumerated below; nothing places
the rest, and a target that needs one records its rows here first.

| Group | Signals | Independent sources | Vendor I/O standard |
|---|---|---|---|
| Clocks and SMA | 5 | 1 to 6 | 3.3 V, or JP6 |
| Push buttons `KEY` | 4 | 5 | JP7 |
| Slide switches `SW` | 18 | 5 | JP7 |
| Red LEDs `LEDR` | 18 | 3 | 2.5 V |
| Green LEDs `LEDG` | 9 | 2 | 2.5 V |
| Seven-segment `HEX0` to `HEX7` | 56 | 3 to 4 | 2.5 V, 3.3 V, JP6 or JP7 |
| LCD module | 13 | 2 to 3 | 3.3 V |
| RS-232 `UART_*` | 4 | 3 | 3.3 V |
| IrDA | 1 | 1 | 3.3 V |
| SDRAM `DRAM_*` | 57 | 2 | 3.3 V |
| SRAM `SRAM_*` | 41 | 1 | 3.3 V |
| Flash `FL_*` | 37 | 1 to 2 | 3.3 V |
| EEPROM `EEP_*` | 2 | 1 | 3.3 V |
| Gigabit Ethernet `ENET0_*`, `ENET1_*` | 45 | 1 to 2 | 2.5 V, 3.3 V |
| VGA `VGA_*` | 29 | 4 to 5 | 3.3 V |
| Audio CODEC `AUD_*` | 6 | 5 | 3.3 V |
| TV decoder `TD_*` | 4 | 1 | 3.3 V |
| I2C bus `I2C_*` | 2 | 5 | 3.3 V |
| PS/2 `PS2_*` | 4 | 2 | 3.3 V |
| SD card `SD_*` | 7 | 3 | 3.3 V |
| USB OTG `OTG_*` | 30 | 1 | 3.3 V |
| Expansion header `GPIO` | 36 | 1 | JP6 |
| HSMC connector `HSMC_*` | 82 | 1 | JP7 |
| 14-pin `EX_IO` | 7 | 2 | 3.3 V |

### Clocks

| Signal | Pin | Sources | Attesting groups |
|---|---|---|---|
| `CLOCK_50` | `PIN_Y2` | 6 | `T`, `C`, `E`, `F`, `G`, `K` |
| `CLOCK2_50` | `PIN_AG14` | 3 | `T`, `G`, `K` |
| `CLOCK3_50` | `PIN_AG15` | 3 | `T`, `G`, `K` |
| `SMA_CLKIN` | `PIN_AH14` | 1 | `T` |
| `SMA_CLKOUT` | `PIN_AE23` | 1 | `T` |

### Push buttons

| Signal | Pin | Sources | Attesting groups |
|---|---|---|---|
| `KEY[0]` | `PIN_M23` | 5 | `T`, `C`, `E`, `F`, `G` |
| `KEY[1]` | `PIN_M21` | 5 | `T`, `C`, `E`, `F`, `G` |
| `KEY[2]` | `PIN_N21` | 5 | `T`, `C`, `E`, `F`, `G` |
| `KEY[3]` | `PIN_R24` | 5 | `T`, `C`, `E`, `F`, `G` |

### Red LEDs

Every `LEDR` row is stated by groups `T`, `F` and `G`, so all eighteen carry
three independent transcriptions. `LEDG` carries only two (`T` and `G`), which is
why the flow proof drives `LEDR[7:0]` and not the green bank.

| Signal | Pin | Signal | Pin | Signal | Pin |
|---|---|---|---|---|---|
| `LEDR[0]` | `PIN_G19` | `LEDR[6]` | `PIN_J19` | `LEDR[12]` | `PIN_J16` |
| `LEDR[1]` | `PIN_F19` | `LEDR[7]` | `PIN_H19` | `LEDR[13]` | `PIN_H17` |
| `LEDR[2]` | `PIN_E19` | `LEDR[8]` | `PIN_J17` | `LEDR[14]` | `PIN_F15` |
| `LEDR[3]` | `PIN_F21` | `LEDR[9]` | `PIN_G17` | `LEDR[15]` | `PIN_G15` |
| `LEDR[4]` | `PIN_F18` | `LEDR[10]` | `PIN_J15` | `LEDR[16]` | `PIN_G16` |
| `LEDR[5]` | `PIN_E18` | `LEDR[11]` | `PIN_H16` | `LEDR[17]` | `PIN_H15` |

## Targets

[`src/fpga/de2_115/targets.json`](../../src/fpga/de2_115/targets.json) registers
this board. The registry names the device, the family, the analysed timing
corners, the [I/O standard each package pin is supplied at](#io-voltage-and-what-the-flow-proof-declares)
and this page; the [builder contract](../tools/n2m/SPEC.md#fpga-build) owns that
schema.

`de2-smoke` is the flow proof: the counter in
[`de2_smoke.sv`](../../src/fpga/de2_115/de2_smoke.sv) driving `LEDR[7:0]` from
`CLOCK_50`, with `KEY[0]` synchronized through two flops into an active-high
reset. It uses ten pins, each stated by three or more independent transcriptions:
`CLOCK_50`, `KEY[0]` and `LEDR[7:0]`. It has no PLL and no vendor IP.
`de2-invalid` shares that source and deliberately declares a negative clock
period, so it must fail. The registry states a target's own pin numbers because
the builder needs them as machine-readable assignments; every pin's provenance is
stated only in the tables above.

Quartus analyses this commercial device at three corners, `Slow 1200mV 85C`,
`Slow 1200mV 0C` and `Fast 1200mV 0C`, and the builder requires setup, hold and
minimum-pulse-width slack at each. It also requires a drive strength and a slew
rate on each of this target's 2.5 V LED pins, because the Cyclone IV E fitter
reports a 2.5 V output pin without both as an incomplete I/O assignment, where
the same fitter wants only the drive strength on 3.3-V LVTTL. That requirement
follows the family and the declared standard together, not the board, so the
[builder contract](../tools/n2m/SPEC.md#fpga-build) holds it there.

The fit places 34 logic elements, 42 registers and ten pins, with positive slack
at all three corners, no unconstrained path, no ignored constraint and no
structural timing problem. Two diagnostics are classified rather than hidden: the
fitter's AN 447 caution that one pin — `clk_reference`, the only 3.3-V LVTTL pin
this target places — must meet the 3.3/3.0/2.5-V interface requirements, and the
LogicLock subscription notice every board's fit carries. The DE10-Lite fit
carries the same AN 447 caution with `MAX 10` in the application note's title.

A passing fit is evidence of the build path, placement and timing only. Nothing
has been programmed onto a DE2-115, and the
[declared I/O voltage](#io-voltage-and-what-the-flow-proof-declares) means this
image must not be.

## Verification

- [`tools/n2m/fpga.py`](../../tools/n2m/fpga.py) resolves a target against its
  board registry and derives every device-dependent assignment and evidence check
  from it.
- [`tools/n2m/tests/test_fpga.py`](../../tools/n2m/tests/test_fpga.py) covers the
  registry schema, the per-board device and family in the generated project
  files, the I/O standard each pin declares against its board's record, the
  refusal of a pin with no recorded standard, and that each family and standard
  states only the output settings its own fitter needs.
- `python3 tools/build.py fpga build de2-smoke` must PASS with its fit, timing and
  assembly reports retained; `de2-invalid` must FAIL. Both are recorded in the
  [builder contract](../tools/n2m/SPEC.md#fpga-build).
- The Questa compile gate elaborates `de2_smoke` with every other registered top.

Physical verification of this board is not done. It needs explicit hardware
authorization, and it is not part of the flow proof.

## References

- DE2-115 user manual, Terasic. Tables 4-1 to 4-5 and the peripheral tables of
  sections 4.6 to 4.19 are the [vendor pin table](#vendor-pin-table); sections
  4.7 and 4.8 are the source of the JP6 and JP7 facts in
  [I/O voltage](#io-voltage-and-what-the-flow-proof-declares). The copy read
  states version V1.02 with a 2010 Terasic copyright. Terasic's own host
  `www.terasic.com.tw` fails TLS certificate verification from the host this page
  was written on, so the copy read was the mirror at
  `people.duke.edu/~tkb13/courses/ece550-2016fa/resources/DE2_115_User_Manual.pdf`,
  which hashed to SHA-256
  `5e2eaa4745f6d1133b91cc46487847bef662d89161ec03b8ba6179e044f97972`. That is a
  record of what was read rather than a second reader's confirmation, and a
  mirror is not the vendor's own copy. Vendor documentation is a reference, not
  redistributed source, and no copy is committed.
- [Cyclone IV device handbook](https://www.intel.com/content/www/us/en/docs/programmable/683375/current/device-datasheet-for-devices.html),
  Intel document `CYIV-53001`. Vendor documentation is a reference, not
  redistributed source.
- [Board bring-up](board-bring-up.md): the qualified DE10-Lite path.
- [DE10-Nano board](de10-nano-board.md): the second board, and the family that
  had to replace ALTPLL and M9K rather than reuse them.
- [Builder FPGA build contract](../tools/n2m/SPEC.md#fpga-build)
