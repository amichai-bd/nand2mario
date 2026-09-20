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
  So [`de2-clocking`](#targets) fits the DE10-Lite's own wrapper
  [`n2m_clocking.sv`](../../src/fpga/de10_lite/n2m_clocking.sv) in place, and the
  generated HDL differs from the DE10-Lite's in the family string alone. Neither
  kind of copy is available: a copy keeping the module name fails the
  [Questa compile gate](../tools/n2m/SPEC.md#questa-compile-gate), which compiles
  every registered source into one library in a single `vlog` and warns
  `vlog-2275 Existing module 'n2m_clocking' ... will be overwritten`, and the gate
  fails on any warning; a renamed copy instead forks the fitted instance
  hierarchy every clocking check and constraint names, which is what the
  Cyclone V wrapper costs. The clocks, the solved counters and every check are the
  same; what this family changes is listed in the
  [builder contract](../tools/n2m/SPEC.md#cyclone-iv-e-altpll).
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
  [`de2-vga`](#targets) places the existing pixel path on it; how four bits of
  shade reach eight DAC bits, and what the DAC's own controls are held at, is
  [below](#driving-the-vga-dac).
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
nothing defaults. The [29 VGA pins](#vga) are the other entry: the vendor table
gives the whole group 3.3 V, so [`de2-vga`](#targets) declares `3.3-V LVTTL` on
every one of them and its fit needs no 2.5 V bank.

The [fit](#targets) reports those banks accordingly: `I/O Bank Usage` gives bank
2 at 3.3 V for `CLOCK_50`, bank 6 at 2.5 V for `KEY[0]` and bank 7 at 2.5 V for
`LEDR[7:0]`, and its per-pin tables give `2.5 V` on all nine.

The [seven-segment group](#seven-segment-displays) is the harder entry, and it is
where declaring a voltage stops being bookkeeping. Of its 56 pins the vendor
fixes only four — three at 2.5 V and one at 3.3 V — and leaves 52 to a jumper: 20
to JP7, whose default supplies 2.5 V, and 32 to JP6, whose default supplies
3.3 V. A design that uses all eight digits therefore declares two different
standards inside one group, with the boundaries falling mid-digit, and for 52 of
the 56 what it declares is a documented default position rather than a measured
supply. The registry records `2.5 V` on the three fixed 2.5 V pins together with
all 20 JP7 pins, and `3.3-V LVTTL` on the 32 JP6 pins together with the one fixed
3.3 V pin, which is the same rule the [switches](#slide-switches) and `KEY` follow
and the same caveat: **JP6 and JP7 must be read on the board before anything that
drives these pins is programmed onto it.** The 11 switch and 2 extra push-button
pins the same image places are all JP7, so they take `2.5 V` with the rest.

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

### Slide switches

All eighteen, from [Table 4-1](#references) and the sources that agree with it.
Every row carries five independent transcriptions (`C`, `E`, `F`, `G`, `T`) and
none disagrees with the vendor table or with another source. The whole group's
vendor I/O standard is `Depending on JP7`, uniformly: no switch has a fixed
standard, and JP7's default position supplies 2.5 V.

| Signal | Pin | Signal | Pin |
|---|---|---|---|
| `SW[0]` | `PIN_AB28` | `SW[9]` | `PIN_AB25` |
| `SW[1]` | `PIN_AC28` | `SW[10]` | `PIN_AC24` |
| `SW[2]` | `PIN_AC27` | `SW[11]` | `PIN_AB24` |
| `SW[3]` | `PIN_AD27` | `SW[12]` | `PIN_AB23` |
| `SW[4]` | `PIN_AB27` | `SW[13]` | `PIN_AA24` |
| `SW[5]` | `PIN_AC26` | `SW[14]` | `PIN_AA23` |
| `SW[6]` | `PIN_AD26` | `SW[15]` | `PIN_AA22` |
| `SW[7]` | `PIN_AB26` | `SW[16]` | `PIN_Y24` |
| `SW[8]` | `PIN_AC25` | `SW[17]` | `PIN_Y23` |

The vendor states the sense and the debouncing, and both matter to anything that
reads them: "When the switch is in the DOWN position (closest to the edge of the
board), it provides a low logic level to the FPGA, and when the switch is in the
UP position it provides a high logic level", and "These switches are not
debounced". A switch away from the board edge reads 1, and the FPGA pin is the
contact, so whatever reads a switch owns its bounce. The push-buttons are the
other way on both counts: each "provides a high logic level when it is not
pressed, and provides a low logic level when depressed", through an onboard
Schmitt-trigger debouncing circuit.

Three sources put their own design ports on these pins under other names —
`switch[n]` (`B`, all eighteen positional), `SWITCH[n]` (`D`, the low ten
positional) and `keys[n]` with a one-position offset (`I`) — and one puts a
single port on `SW[17]` (`H`). They corroborate the pin set; none names a vendor
signal, so none is counted above.

### Seven-segment displays

All 56 signals of the eight digits, from [Table 4-4](#references) and the sources
that agree with it. `HEX0` through `HEX5` carry four independent transcriptions
and `HEX6` and `HEX7` carry three, because `F` assigns only the first six digits.
No source disagrees with the vendor table or with another source, and the seven
`T` files agree with each other on all 56.

**This group is the one place on this board where the vendor states four
different I/O standards inside one group, and the boundaries fall mid-digit.**
Three pins are fixed at 2.5 V, twenty depend on JP7, thirty two depend on JP6,
and one — `HEX7[6]` — is fixed at 3.3 V among six JP6 siblings. `HEX0` splits 3/4
between fixed 2.5 V and JP7, `HEX3` splits 2/5 between JP7 and JP6, and `HEX7`
splits 6/1 between JP6 and fixed 3.3 V. Each row below carries the manual's own
string, and nothing is reconciled with its neighbours.

| Signal | Pin | Sources | Attesting groups | Vendor I/O standard |
|---|---|---|---|---|
| `HEX0[0]` | `PIN_G18` | 4 | `B`, `F`, `G`, `T` | 2.5V |
| `HEX0[1]` | `PIN_F22` | 4 | `B`, `F`, `G`, `T` | 2.5V |
| `HEX0[2]` | `PIN_E17` | 4 | `B`, `F`, `G`, `T` | 2.5V |
| `HEX0[3]` | `PIN_L26` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX0[4]` | `PIN_L25` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX0[5]` | `PIN_J22` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX0[6]` | `PIN_H22` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX1[0]` | `PIN_M24` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX1[1]` | `PIN_Y22` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX1[2]` | `PIN_W21` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX1[3]` | `PIN_W22` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX1[4]` | `PIN_W25` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX1[5]` | `PIN_U23` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX1[6]` | `PIN_U24` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX2[0]` | `PIN_AA25` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX2[1]` | `PIN_AA26` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX2[2]` | `PIN_Y25` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX2[3]` | `PIN_W26` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX2[4]` | `PIN_Y26` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX2[5]` | `PIN_W27` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX2[6]` | `PIN_W28` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX3[0]` | `PIN_V21` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX3[1]` | `PIN_U21` | 4 | `B`, `F`, `G`, `T` | Depending on JP7 |
| `HEX3[2]` | `PIN_AB20` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX3[3]` | `PIN_AA21` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX3[4]` | `PIN_AD24` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX3[5]` | `PIN_AF23` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX3[6]` | `PIN_Y19` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX4[0]` | `PIN_AB19` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX4[1]` | `PIN_AA19` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX4[2]` | `PIN_AG21` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX4[3]` | `PIN_AH21` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX4[4]` | `PIN_AE19` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX4[5]` | `PIN_AF19` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX4[6]` | `PIN_AE18` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX5[0]` | `PIN_AD18` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX5[1]` | `PIN_AC18` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX5[2]` | `PIN_AB18` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX5[3]` | `PIN_AH19` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX5[4]` | `PIN_AG19` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX5[5]` | `PIN_AF18` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX5[6]` | `PIN_AH18` | 4 | `B`, `F`, `G`, `T` | Depending on JP6 |
| `HEX6[0]` | `PIN_AA17` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX6[1]` | `PIN_AB16` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX6[2]` | `PIN_AA16` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX6[3]` | `PIN_AB17` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX6[4]` | `PIN_AB15` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX6[5]` | `PIN_AA15` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX6[6]` | `PIN_AC17` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX7[0]` | `PIN_AD17` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX7[1]` | `PIN_AE17` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX7[2]` | `PIN_AG17` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX7[3]` | `PIN_AH17` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX7[4]` | `PIN_AF17` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX7[5]` | `PIN_AG18` | 3 | `B`, `G`, `T` | Depending on JP6 |
| `HEX7[6]` | `PIN_AA14` | 3 | `B`, `G`, `T` | 3.3V |

`H` assigns a flat 56-bit bus onto exactly these 56 pins, grouped seven per
digit, but with the bit order reversed inside each digit and no vendor signal
named, so it corroborates the pin set and the grouping and attests no per-signal
assignment; it is not counted above.

**A segment lights on a low level.** Section 4.4 states it directly: "the seven
segments (common anode) are connected to pins on Cyclone IV E FPGA. Applying a
low logic level to a segment will light it up and applying a high logic level
turns it off." That is the opposite of this board's LEDs, which section 4.3
states as "driving its associated pin to a high logic level turns the LED on", so
the inversion between the two is the vendor's and not an assumption.

**Bit `n` of `HEXd` is segment `n` of the digit**, indexed 0 to 6: section 4.4
says "Each segment in a display is identified by an index from 0 to 6, with the
positions given in Figure 4-10", and that figure prints an index beside each
segment. Read off it, 1 is upper right, 2 is lower right, 3 is the bottom bar, 4
is lower left, 5 is upper left and 6 is the middle bar — the conventional
clockwise `a` to `g` order. Index 0 is the top bar by elimination from the
manual's own statements rather than by reading the figure: the numeral beside the
top bar does not render legibly at any resolution extracted, and the top bar is
the only position the other six indices leave. The decimal point is labelled in
the same figure, carries no index, appears nowhere in Table 4-4 and is not
wired — section 3.2: "the dots of the 7-SEGs are not enabled on DE2-115 board."

**Which physical digit is `HEX0` and which is `HEX7` is not established.** The
manual never says which end of the board either sits at. Section 4.4 gives the
grouping only — "These displays are arranged into two pairs and a group of
four" — Figure 4-10 shows one digit in isolation, and Figure 2-1's board photo
labels the block without labelling a digit, with silkscreen below the embedded
photo's resolution. The chapter 6 demo tables do put the more significant byte on
the higher index, which is suggestive and is not a statement; it is recorded here
as not evidence. So a design that spreads one number across the eight digits
fixes which digit is most significant, and reading them in the right order across
the board is a bring-up observation.

**Polarity and the segment index rest on the vendor manual alone.** None of the
twenty settings files says anything about either: a `.qsf` carries only `set_*`
assignments and comments, and the only seven-segment comments in any of them are
four bare section headers. That is weaker than the pin numbers, which carry three
to five independent transcriptions as well as the manual.

### VGA

All 29 signals of the board's video path, from the
[vendor pin table](#vendor-pin-table) and the sources that agree with it. Twenty
seven carry four independent transcriptions and the two sync pins carry five;
none disagrees with the vendor table or with another source. The whole group is
3.3 V.

| Signal | Pin | Sources | Attesting groups | Signal | Pin | Sources | Attesting groups |
|---|---|---|---|---|---|---|---|
| `VGA_R[0]` | `PIN_E12` | 4 | `T`, `B`, `C`, `F` | `VGA_B[0]` | `PIN_B10` | 4 | `T`, `B`, `C`, `F` |
| `VGA_R[1]` | `PIN_E11` | 4 | `T`, `B`, `C`, `F` | `VGA_B[1]` | `PIN_A10` | 4 | `T`, `B`, `C`, `F` |
| `VGA_R[2]` | `PIN_D10` | 4 | `T`, `B`, `C`, `F` | `VGA_B[2]` | `PIN_C11` | 4 | `T`, `B`, `C`, `F` |
| `VGA_R[3]` | `PIN_F12` | 4 | `T`, `B`, `C`, `F` | `VGA_B[3]` | `PIN_B11` | 4 | `T`, `B`, `C`, `F` |
| `VGA_R[4]` | `PIN_G10` | 4 | `T`, `B`, `C`, `F` | `VGA_B[4]` | `PIN_A11` | 4 | `T`, `B`, `C`, `F` |
| `VGA_R[5]` | `PIN_J12` | 4 | `T`, `B`, `C`, `F` | `VGA_B[5]` | `PIN_C12` | 4 | `T`, `B`, `C`, `F` |
| `VGA_R[6]` | `PIN_H8` | 4 | `T`, `B`, `C`, `F` | `VGA_B[6]` | `PIN_D11` | 4 | `T`, `B`, `C`, `F` |
| `VGA_R[7]` | `PIN_H10` | 4 | `T`, `B`, `C`, `F` | `VGA_B[7]` | `PIN_D12` | 4 | `T`, `B`, `C`, `F` |
| `VGA_G[0]` | `PIN_G8` | 4 | `T`, `B`, `C`, `F` | `VGA_CLK` | `PIN_A12` | 4 | `T`, `B`, `C`, `F` |
| `VGA_G[1]` | `PIN_G11` | 4 | `T`, `B`, `C`, `F` | `VGA_BLANK_N` | `PIN_F11` | 4 | `T`, `B`, `C`, `F` |
| `VGA_G[2]` | `PIN_F8` | 4 | `T`, `B`, `C`, `F` | `VGA_SYNC_N` | `PIN_C10` | 4 | `T`, `B`, `C`, `F` |
| `VGA_G[3]` | `PIN_H12` | 4 | `T`, `B`, `C`, `F` | `VGA_HS` | `PIN_G13` | 5 | `T`, `B`, `C`, `D`, `F` |
| `VGA_G[4]` | `PIN_C8` | 4 | `T`, `B`, `C`, `F` | `VGA_VS` | `PIN_C13` | 5 | `T`, `B`, `C`, `D`, `F` |
| `VGA_G[5]` | `PIN_B8` | 4 | `T`, `B`, `C`, `F` | | | | |
| `VGA_G[6]` | `PIN_F10` | 4 | `T`, `B`, `C`, `F` | | | | |
| `VGA_G[7]` | `PIN_C9` | 4 | `T`, `B`, `C`, `F` | | | | |

`VGA_R[0]` is the least significant of the eight bits the board wires, and the
ADV7123's own `R0` is the least significant of its ten; the manual states that
only the higher eight of those ten are used, so the wired eight are the DAC's
eight most significant bits. What the remaining two are fixed at on the board is
not stated in the manual's text, and no source here establishes it.

The [flow proof's caveat](#pin-data) is unchanged: four transcriptions agreeing
with the vendor table is strong evidence against a transcription error and no
evidence of measurement. No pin in this group is verified against hardware.

## Driving the VGA DAC

The pixel path is board-independent: [`n2m_vga_scan`](../../src/rtl/vga/n2m_vga_scan.sv)
produces four bits per channel plus active-low horizontal and vertical sync, and
the [frame bridge contract](rtl/vga/MAS_vga.md) owns its geometry, its shades and
its timing. Nothing on this board changes any of that. What this board decides is
how those four bits reach eight DAC bits, and what the DAC's own control inputs
are held at. [`de2_vga_proof.sv`](../../src/fpga/de2_115/de2_vga_proof.sv) is
where both decisions are implemented, and this section is why they are those.

### Four bits of shade on eight DAC bits

**The byte is the nibble repeated: `vga_r = {red, red}`.** So `4'h0` becomes
`8'h00` and `4'hf` becomes `8'hff`.

That is the only alignment that meets all three requirements at once, and it is
forced rather than chosen:

- Black must be zero: `b(0) = 0`.
- Full range must reach full range: `b(15) = 255`, so the brightest shade the
  pixel path can express drives every wired DAC bit.
- Equal steps must stay equal, or a mid shade lands at the wrong voltage: `b` is
  linear.

A linear map through `(0, 0)` and `(15, 255)` is `b(v) = 255v/15 = 17v`, and
`17v = 16v + v`, which is `v` in the high nibble plus `v` in the low nibble —
`{v, v}`. Because 255/15 is exactly 17, the map is exact for all sixteen
four-bit codes; there is no rounding term to argue about.

It is also the same rule one level down. The scan builds each four-bit channel by
repeating the two-bit shade pair, so `{red, red}` makes the byte that pair
repeated four times, and the four DMG shades reach the DAC as:

| Shade | Scan's four bits | DAC byte | Share of the wired range |
|---|---|---|---|
| 0, lightest | `4'hf` | `8'hff` | 255/255 |
| 1 | `4'ha` | `8'haa` | 170/255 |
| 2 | `4'h5` | `8'h55` | 85/255 |
| 3, darkest | `4'h0` | `8'h00` | 0/255 |

Those are exact thirds of full scale, which is what the four-level ladder was
already producing on the DE10-Lite: this board reproduces the same picture at a
finer code resolution it does not need, not a different one.

The near alternatives are defects, which is why the choice is stated here rather
than left to the reader of the RTL:

- Left-shift and zero-fill, `{v, 4'h0}`: white becomes `8'hf0`, 94.1% of the
  range, so nothing on screen is ever white and every shade is 16/17 of its
  value. This is the common mistake, and a fit accepts it silently.
- Right-align, `{4'h0, v}`: white becomes `8'h0f`, 5.9%, and the whole picture
  is nearly black.
- Any constant low fill other than a copy of the value, such as `{v, 4'hf}`,
  moves black off zero.

**What "full range" means on this board.** `8'hff` drives the eight bits the
board wires to all ones, which is the maximum this board can present. The DAC has
two further low bits the board fixes, so what appears at the connector also
depends on their level, which the [pin table](#vga) records as not established
from a citable source. Nothing here has been measured on a monitor; that is a
bring-up result, not a fit result.

### The DAC's clock, blank and sync inputs

Three signals are the DAC's own controls rather than picture data. Each value
below comes from the [ADV7123 data sheet](#references), which the DE2-115 manual
itself defers to for the DAC ("Detailed information for using the ADV7123 video
DAC is available in its datasheet", section 4.10).

| Signal | Held at | Source |
|---|---|---|
| `VGA_BLANK_N` | `1'b1` | "A Logic 0 on this control input drives the analog outputs, IOR, IOB, and IOG, to the blanking level ... While BLANK is a Logic 0, the R0 to R9, G0 to G9, and B0 to B9 pixel inputs are ignored." |
| `VGA_SYNC_N` | `1'b0` | "If sync information is not required on the green channel, the SYNC input should be tied to Logic 0." |
| `VGA_CLK` | `~clk_pix` | "The rising edge of CLOCK latches the R0 to R9, G0 to G9, B0 to B9, SYNC, and BLANK pixel and control inputs. It is typically the pixel clock rate of the video system." |

**SYNC is tied low, and that is not merely permitted.** This board sends
horizontal and vertical sync to the connector on their own pins, so no sync has
to be encoded on green. The data sheet's own `RSET` relations say what tying SYNC
low buys: `IOG = 11,445 x VREF/RSET` while SYNC is asserted and
`IOR, IOB = 7989.6 x VREF/RSET`, and "The equation for IOG is the same as that
for IOR and IOB when SYNC is not being used, that is, SYNC tied permanently
low." Those are the `Rev. D` figures and wording, from the copy this page
records; `Rev. A` and `Rev. B` state the same relation with `12,081` and `8,627`
and the older phrasing. Held high instead, green would carry a 40 IRE pedestal that red and blue do
not, so equal codes on the three channels would not produce equal light and grey
would not be grey. Tying it low is what keeps the shade table above true of all
three channels.

**BLANK is held high, and the scan does the blanking.** A Logic 0 makes the DAC
ignore the pixel inputs, so it has to be high for any picture at all. The data
sheet's output truth table settles whether it also has to fall during the
blanking interval: with SYNC already low, `BLACK to BLANK` (SYNC 0, BLANK 1, data
`0x000`) and `SYNC Level` (SYNC 0, BLANK 0, data don't care) both put all three
outputs at the same current, 0 mA on IOG and IOR/IOB. The scan already drives all
three channels to zero outside its active window, so asserting BLANK would
reproduce a level the pixel data already produces. Holding it high keeps the
board side a pure mapping with no second source of blanking to keep in step with
the qualified scan. Driving it from the scan's active region is the alternative,
and it would be a change to what the pixel path exports rather than a board
mapping.

**CLOCK is the pixel clock inverted.** The DAC latches data and both controls on
the rising edge of CLOCK, and the fabric drives that data on the rising edge of
`clk_pix`. Sending `clk_pix` itself would ask the DAC to sample exactly when the
data changes. Inverting it puts the DAC's sampling edge half a pixel period
later, 19.841 ns at 25.2 MHz, before either pin's own delay. The part asks for
0.5 ns of setup and 1.5 ns of hold at 5 V, 0.2 ns and 1.5 ns at 3.3 V (`t1`,
`t2`, Rev. D; Rev. A states the older 1.5 ns and 2.5 ns, which the same margin
also covers).

Write `d_data` for a data pin's clock-to-out and `d_clk` for the clock pin's, and
the two sides are not symmetric:

- setup at the DAC is `19.841 + d_clk − d_data`. `d_clk` is never negative, so
  bounding `d_data` bounds setup from below and nothing else is needed.
- hold is `19.841 + d_data − d_clk`, which needs `d_clk` bounded from above.

Only the first is bounded here. The
[VGA proof profile](../tools/n2m/SPEC.md#vga-proof-profile) bounds every data and
sync pin's delay to 10 ns and their spread to 2 ns whatever the fit does, so setup
is at least 19.841 − 10 = 9.8 ns by constraint, and the
[`de2-vga` fit](#targets) measures `d_data` between 1.507 ns and 2.732 ns across
all three corners, so this fit presents at least 17.1 ns. `VGA_CLK` carries a
clock rather than data and is deliberately the one output with no output delay, so
no retained report bounds `d_clk` and the hold side is a measurement of this fit
rather than a bound on every fit: around 18 ns once a few nanoseconds of clock-pin
delay are subtracted from 21.3. Either way both sides stay an order of magnitude
above what the part asks for, and neither number is an observation of a picture.

`de2_vga.sdc` declares that inversion to the Timing Analyzer as a generated clock
on the pin, `vga_dac_clk`, sourced from the pixel PLL's `clk[0]` with `-invert`,
the same way the [SDRAM contract](rtl/storage/MAS_sdram.md#clock-relationship-and-constraints)
declares its inverted pin clock. So the relationship the paragraph above reasons
about is a checked clock in the analysis rather than a claim about the RTL, and
the [builder contract](../tools/n2m/SPEC.md#fpga-build) states what it requires
of that row.

Also 25.2 MHz is inside the part's clock range whichever speed grade the board
carries: `fCLK` is 0.5 MHz to 50 MHz on the slowest grade, and the manual's
"bandwidth of 100MHz" puts this board above that. A 50% duty 25.2 MHz clock holds
CLOCK high and low for 19.84 ns each, against the 8.0 ns minimum pulse width the
slowest grade states.

**None of this has been observed.** These are the documented values and the
analysis that supports them. No image has been programmed onto a DE2-115 and no
monitor has been connected; that belongs to a bring-up record with its own
authorization.

## The on-board readout

This board has no host link on this bench — [no UART cable and no HPS](board-bring-up.md),
and its JTAG programs rather than talks — so the two things a host would be asked,
which image is running and whether its ROM is the intended one, are answered on
the board itself. The eight [seven-segment digits](#seven-segment-displays) carry
32 bits of hexadecimal, and the [switches](#slide-switches) choose which 32 bits.

`HEX7` carries the most significant nibble and `HEX0` the least. Which physical
digit each of those is is [not established](#seven-segment-displays) from the
vendor manual, so which end of the block to start reading from is a bring-up
observation rather than a documented fact.

`SW[10:8]` select the view. All eight selections are defined, so no switch
position leaves the digits stating something undefined:

| `SW[10:8]` | Digits show |
|---|---|
| `000` | build identity, bits 127 to 96 |
| `001` | build identity, bits 95 to 64 |
| `010` | build identity, bits 63 to 32 |
| `011` | build identity, bits 31 to 0 |
| `100` | CRC-32 of the ROM the build carried into the bitstream |
| `101` | emulated dots elapsed, low 32 bits |
| `110` | core epoch |
| `111` | `{fault, paused, input source, effective button mask}` |

The build identity is the same 128-bit constant the DE10-Lite's composed images
publish over UART, so the four identity views answer exactly what a host `ping`
answers. Reading it takes four switch positions because eight digits hold a
quarter of it at a time.

The CRC view is the packager's own CRC-32 of the image it wrote, reaching the
design as one compiled 32-bit constant, so the number on the digits and the number
in the build record come from the same packaged bytes. It identifies the carried
ROM; that the bitstream actually holds those bytes is a separate and stronger
result, read out of the fitted memory blocks by the
[builder](../tools/n2m/SPEC.md#carried-rom-image).

Views `101` and `110` are the composition's own system-domain counters rather
than the frame bridge's pixel-domain ones, because the digits are clocked in the
system domain: sampling a 32-bit pixel-domain counter into them would be an
unsynchronized crossing between two unrelated clocks, which tears the number and
adds a path the analysis cannot meet. A moving dot count is what says the core is
running whatever the monitor shows.

That the core runs at all on a board with no host is not something the fit shows;
the [host-free execution check](rtl/system/MAS_system.md#host-free-composition) is
what establishes it.

The controls are this board's own. `KEY[0]` is the board reset. `SW[7:0]` hold the
eight DMG buttons in the order the shared button mask uses — right, left, up,
down, A, B, select, start — and `KEY[3]` and `KEY[2]` add momentary A and B,
because a platformer's jump is a press rather than a position. Two slide switches
can assert both of an opposing pair where a d-pad cannot, so both are dropped when
they are, which is the rule the physical control producer already asserts. Every
one of these thirteen inputs passes the shared button filter's two forced
synchronizer stages and its 5 ms stable window before it reaches the composition,
because the vendor states these switches are not debounced.

A switch left up when the board is powered on is delivered, and the stable window
is why. This image issues one core reset, from the host-free start path, two
`clk_sys` cycles after the global reset releases, and the filter cannot accept
anything for 125000 cycles after that same release. So the held switch arrives on
the ordinary commit that follows the reset, not across it. A core reset with a mask
already published is the case the
[input owner](rtl/input/MAS_input.md#reset-and-power) re-offers the mask on, and this
board issues no second one: the start path's reset is a one-shot, and the only other
source is the loader engine's swap request, which this image cannot raise because it
carries no flash library and reports its SDRAM uninitialized.

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

`de2-clocking` is the clocking proof: the 25 MHz system and 25.2 MHz pixel clocks
of the [clock contract](clocks-resets-cdc.md) generated from `CLOCK_50` by two
ALTPLL instances, behind the shared
[`n2m_reset_control.sv`](../../src/rtl/clocking/n2m_reset_control.sv) and
[`n2m_timebase.sv`](../../src/rtl/clocking/n2m_timebase.sv), observed on virtual
ports by [`de2_clocking_proof.sv`](../../src/fpga/de2_115/de2_clocking_proof.sv).
It uses one pin, `CLOCK_50` on `PIN_Y2`, and instantiates the DE10-Lite's ALTPLL
wrapper unchanged, so the fitted hierarchy, the checked clock names and the whole
lock, metastability, reset-chain and clock-transfer evidence are that board's.
The fit reports both clocks at their documented rates — the system PLL at
`M=104, N=8, C=26` from a 650 MHz VCO for 25.0 MHz, the pixel PLL at
`M=63, N=5, C=25` from a 630 MHz VCO for 25.2 MHz, both compensating `clock0` at
50% duty and zero phase from a dedicated pin — with 120 logic elements, 77
registers, 2 of 4 PLLs, one pin and 21 virtual pins, and positive slack for
setup, hold, recovery, removal and minimum pulse width on all three clocks at all
three corners. Its worst slack is 0.181 ns, on `clk_reference` hold at
`Fast 1200mV 0C`.

Three diagnostics are classified rather than hidden: the LogicLock notice and the
AN 447 caution the flow proof also carries, and one
`Critical Warning (176598)` stating that a PLL's input clock is not fully
compensated because it is fed by a remote clock pin. That one follows from the
clock contract, not from a shortage of clock pins: this board has four dedicated
clock inputs ([above](#clocks)), but
[both PLLs take the same reference](rtl/clocking/MAS_clocking.md), and only one
PLL location on this device reaches `CLOCK_50` locally, so the Fitter places the
other where that pin arrives over the remote dedicated path. Both PLLs still take
the pin directly and nothing in this composition times a path against the
reference pin, so the caution is recorded with that reason; the
[builder contract](../tools/n2m/SPEC.md#cyclone-iv-e-altpll) states exactly what
it accepts.

`de2-clocking-invalid` is that pair's negative control. It shares every source and
constraint and names the Cyclone V Altera PLL's system clock as the checked
output-delay clock instead of ALTPLL's, so `read_sdc` finds no such clock, reports
`Error (332000): checked endpoint count mismatch: clock_0` with the offending SDC
line, and the Fitter exits nonzero. A passing `de2-clocking` fit is therefore
evidence rather than an absent check.

`de2-vga` puts the existing pixel path on the video DAC:
[`de2_vga_proof.sv`](../../src/fpga/de2_115/de2_vga_proof.sv) instantiates the
same `u_clocking`, `u_timebase` and `u_bridge` the MAX 10 `vga_proof` fits, in the
same hierarchy, with the [alignment and control values above](#driving-the-vga-dac)
on the board side and everything else on virtual ports. It uses 30 pins:
`CLOCK_50` and all 29 [`VGA_*` signals](#vga). The fit places 1,048 logic
elements, 707 registers, 138,240 memory bits in 18 M9K blocks as the frame
bridge's three dual-clock banks, 2 of 4 PLLs, those 30 pins and 309 virtual pins,
with positive slack for setup, hold, recovery, removal and minimum pulse width on
all four analysed clocks at all three corners. Its worst slack is 0.181 ns, on
`clk_reference` hold at `Fast 1200mV 0C`, the same path and value
[`de2-clocking`](#targets) reports. `I/O Bank Usage` gives bank 8 at 3.3 V for the
29 VGA pins and bank 2 at 3.3 V for `CLOCK_50`, and the per-pin table gives
`3.3-V LVTTL` with `8mA` on every one of the 29.

The fourth analysed clock is the DAC's: `vga_dac_clk`, the pixel clock inverted at
`VGA_CLK`, which the fit reports as a generated clock of period 39.682 ns at unit
ratio from the pixel PLL, inverted, targeting that port. The retained per-corner
output reports bound every DAC data and sync pin's delay to 2.732 ns at worst
(`Slow 1200mV 85C`) and 1.507 ns at best (`Fast 1200mV 0C`), with at most 0.250 ns
of skew across the group. Half a pixel period is 19.841 ns, so the DAC sees at
least 19.841 − 2.732 = 17.1 ns of setup, against the 0.5 ns the part asks for.
The hold side carries no "at least": `VGA_CLK` is the one output with no output
delay, so no retained report bounds its own delay, and
[the derivation above](#the-dacs-clock-blank-and-sync-inputs) explains why that
makes the roughly 18 ns of hold a measurement of this fit rather than a bound. The checked netlist shows
`VGA_CLK`'s output buffer taking the complement of the fitted pixel clock net, and
`VGA_BLANK_N` and `VGA_SYNC_N` taking `vcc` and `gnd`, so the documented values
reached their pins.

Two diagnostics are this target's own and are classified with their reason: the
`Warning (13024)` heading with one `Warning (13410)` line per deliberately
constant control pin, and one `Warning (15064)` for the pixel clock reaching
`VGA_CLK` through the fabric rather than a dedicated PLL output pin. It also
carries the same LogicLock notice, AN 447 caution, 176127 merge refusal and
176598 compensation caution `de2-clocking` does.

`de2-vga-invalid` is that pair's negative control. It shares every source and pin
and sources the generated DAC clock from the Cyclone V Altera PLL's output
counter, which no Cyclone IV E netlist contains, so the Fitter reports
`Warning (332174): Ignored filter at de2_vga_invalid.sdc(9):
u_clocking|u_pll|altera_pll_i|cyclonev_pll|counter[0].output_counter|divclk could
not be matched with a pin` and the build fails on it. A passing `de2-vga` fit is
therefore evidence rather than an absent check.

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
- `python3 tools/build.py fpga build de2-clocking` must PASS with its generated
  HDL, fit, timing, lock, metastability, reset-chain and clock-transfer evidence
  retained; `de2-clocking-invalid` must FAIL. Both are recorded in the
  [builder contract](../tools/n2m/SPEC.md#fpga-build).
- `python3 tools/build.py fpga build de2-vga` must PASS with the whole
  [VGA proof profile](../tools/n2m/SPEC.md#vga-proof-profile)'s evidence on this
  board's eight-bit profile, the DAC's pin clock and control levels checked in the
  fitted netlist, and positive slack at all three corners; `de2-vga-invalid` must
  FAIL. Both are recorded in the
  [builder contract](../tools/n2m/SPEC.md#de2-115-video-dac).
- `python3 tools/build.py fpga build de2-system` must PASS with the fit, timing at
  all three corners, the carried image's fitted contents, the readout's identity
  and CRC constants, the DAC's pin levels and every control chain's per-corner
  reports retained; `de2-system-invalid` must FAIL. The
  [builder contract](../tools/n2m/SPEC.md#de2-115-system-image) records both.
- `python3 tools/build.py sim test host-free-boot --sim verilator` must PASS. It is
  the one check a fit cannot stand in for: this image's core starts only because the
  composition issues its own power-up reset and releases host pause, and a fit shows
  neither. The [integration specification](../src/dv/integration/SPEC.md#host-free-start)
  owns it.
- [`test_fpga_de2_system.py`](../../tools/n2m/tests/test_fpga_de2_system.py) covers
  the seven-segment decode against the polarity and segment index above, every
  switch position selecting a defined view, each absent interface driven to its
  inactive value, the two I/O standards this readout declares and the settings each
  needs, and the carried image's CRC in the project and as compiled.
- [`test_fpga_cycloneive.py`](../../tools/n2m/tests/test_fpga_cycloneive.py) covers
  what this family changes against MAX 10 and what it still refuses.
- [`test_fpga_vga_dac.py`](../../tools/n2m/tests/test_fpga_vga_dac.py) covers the
  bit alignment against the RTL, the output profile's register-to-pin map, the DAC
  control levels in a netlist fixture, and the bounds of both DAC diagnostics.
- The Questa compile gate elaborates `de2_smoke`, `de2_clocking_proof`,
  `de2_vga_proof` and `de2_system_proof` with every other registered top.

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
- ADV7123 data sheet, Analog Devices: the source of every
  [DAC control value](#the-dacs-clock-blank-and-sync-inputs), its output truth
  table and its `t1`/`t2` setup and hold figures. The DE2-115 manual defers to it
  for the DAC rather than restating any of this. Analog Devices' own host
  `www.analog.com` could not be reached from the host this page was written on:
  `curl` to
  `www.analog.com/media/en/technical-documentation/data-sheets/adv7123.pdf`
  returned zero bytes in 180 seconds and a page-fetching tool timed out as well.
  The copy read is that same vendor URL retrieved through the Internet Archive,
  `Rev. D`, SHA-256
  `f59c27bf7a0ed5a57da53955d50458714b67376412ff407cd4f75f93a7dfbfb2`. Two
  third-party mirrors of the earlier `Rev. A` were read as a cross-check and hash
  identically to each other,
  `85271b8635a7476cb2ca1ffc595f37c4e96c2a9b14b4eebe1595289d8fe64e7c`
  (`eecg.utoronto.ca/~tm4/ADV7123_a.pdf` and
  `cs.columbia.edu/~sedwards/classes/2009/4840/Analog-Devices-ADV7123-video-DAC.pdf`),
  and so does Digi-Key's `Rev. B`,
  `7fec6a41419c95a1a76f8972f45f523ece135c263f37889a591789da5ad93bb4`, whose host
  returns `403` to a second reader, so that one digest rests on this reader alone
  while the archived `Rev. D` and both `Rev. A` mirrors have been re-fetched
  independently. All three revisions state the same BLANK, SYNC and CLOCK pin
  descriptions and the same SYNC/BLANK columns of the output truth table;
  `Rev. B` and `Rev. D` agree on `t1` and `t2`, and `Rev. A` states the older,
  looser 1.5 ns and 2.5 ns. `Rev. D` restates the full-scale current relations
  with different constants and wording, which is why
  [the SYNC decision](#the-dacs-clock-blank-and-sync-inputs) quotes `Rev. D` and
  labels the earlier figures as the earlier revisions'. These are records of what
  was read, not second readers' confirmations. Vendor
  documentation is a reference, not redistributed source, and no copy is
  committed.
- [Cyclone IV device handbook](https://www.intel.com/content/www/us/en/docs/programmable/683375/current/device-datasheet-for-devices.html),
  Intel document `CYIV-53001`. Vendor documentation is a reference, not
  redistributed source.
- [Board bring-up](board-bring-up.md): the qualified DE10-Lite path.
- [DE10-Nano board](de10-nano-board.md): the second board, and the family that
  had to replace ALTPLL and M9K rather than reuse them.
- [Builder FPGA build contract](../tools/n2m/SPEC.md#fpga-build)
