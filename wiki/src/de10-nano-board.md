# DE10-Nano board

This page owns the DE10-Nano board data: its device, the JTAG chain that reaches
it, the resources it has and lacks against the DE10-Lite, and every pin
assignment with its provenance. It is the single source of that data;
[`src/fpga/de10_nano/`](../../src/fpga/de10_nano/README.md) links here instead of
restating it, as [board bring-up](board-bring-up.md) does for the DE10-Lite.

The DE10-Lite stays the qualified board. Nothing on this page is a physical
DE10-Nano result: no image has been programmed onto it, and the only checks
behind it are a read-only JTAG chain detect and a Quartus fit.

## Device

Terasic DE10-Nano, Intel Cyclone V SE `5CSEBA6U23I7`. It is an industrial part:
fitting for it, Quartus reports a 1.10 V nominal core voltage and a -40 °C to
100 °C junction temperature range, which is also why its analysed timing
corners differ from the DE10-Lite's. The same [`nano-smoke` fit](#targets)
reports the device capacity:

| Resource | DE10-Nano (`5CSEBA6U23I7`) | DE10-Lite (`10M50DAF484C7G`) |
|---|---|---|
| Logic | 41,910 ALMs | 49,760 logic elements |
| Block memory | 5,662,720 bits in 553 M10K blocks | 1,677,312 bits |
| Multipliers | 112 DSP blocks | 288 9-bit embedded multipliers |
| PLLs | 6 | 4 |
| DLLs | 4 | none reported |
| User I/O in this package | 314 | 360 |
| Internal flash | none | 1 UFM block |
| Analog input | none on the FPGA | 2 ADC blocks |

Both device rows come from the `Fitter Status : Successful` summary of a local
fit: `nano-smoke` for the Cyclone V and `builder-smoke` for the MAX 10, both on
Quartus Prime Lite 25.1std.0 Build 1129.

### Resources this board lacks against the DE10-Lite

- No MAX 10 UFM, so the flash game library has no home here.
- No MAX 10 ADC, so the analog controls have no home here.
- No VGA connector. Video leaves the board through an ADV7513 HDMI
  transmitter instead.
- No FPGA-side SDRAM. The 1 GiB DDR3 belongs to the hard processor system, not
  to the FPGA fabric.
- No ALTPLL. Cyclone V uses a different PLL primitive, so the pixel and system
  PLLs do not port across unchanged; `nano-smoke` runs from the 50 MHz
  reference directly.

It gains block memory: 5,662,720 bits against 1,677,312, about 3.4 times as
much.

## JTAG chain

The chain has **two** devices and the FPGA is at **index 1**, so anything that
addresses the chain by position needs that index:

| Index | IDCODE | Device |
|---|---|---|
| 0 | `0x4ba00477` | ARM Cortex-A9, the hard processor system |
| 1 | `0x2d020dd` | Cyclone V SoC, `5CSE*A6`/`5CSX*6` |

`0x2d020dd` matches `5CSEBA6U23I7`, so the silicon itself confirms the device
this page describes. The detect was read-only; nothing was programmed.

The onboard USB-Blaster II enumerates as `09fb:6810` unconfigured and becomes
`09fb:6010` only after `blaster_6810.hex` is loaded into cable RAM. That
firmware is volatile: every replug returns the cable to `6810`.

## Pin data

Every assignment below was taken from public Quartus settings files that carry
device `5CSEBA6U23I7`, parsed for `set_location_assignment PIN_<pin> -to
<signal>`, and compared across sources. They agree on all 145 board signals
below with no conflict. `Sources` counts how many of them state that
assignment; a signal a source does not use is simply absent from it.

**What this establishes, and what it does not.** None of these projects measured
the board. Every one of them transcribes Terasic's published pin table, so
agreement between them is strong evidence against a transcription error and no
evidence at all of independent measurement. The pins are unverified against
hardware until something is programmed onto a DE10-Nano and observed. Read a
source count as "this many projects transcribed it the same way and built
successfully against it", not as "this many measurements agree".

`Rows` is how many of the 145 assignments below that source states. Three
sources state none of them: they name only their own design ports, and they
support the no-conflict statement without attesting any board signal.

| Source | File | Commit | License | Rows |
|---|---|---|---|---|
| basics-graphics-music | [`boards/de10_nano/board_specific.qsf`](https://github.com/yuri-panchul/basics-graphics-music/blob/e8eccbdf4cd6f520f064e4b49772f1e28c6a2870/boards/de10_nano/board_specific.qsf) | `e8eccbd` | none stated | 122 |
| schoolMIPS | [`board/de10_nano/de10_nano.qsf`](https://github.com/MIPSfpga/schoolMIPS/blob/38a31d404ca6459061a2c9bfd39d85c49ea50a71/board/de10_nano/de10_nano.qsf) | `38a31d4` | none stated | 145 |
| c5soc_opencl | [`de10_nano_sharedonly_hdmi/top.qsf`](https://github.com/thinkoco/c5soc_opencl/blob/31374626ba7edba76bdd1bf848c8af18e6d45628/de10_nano_sharedonly_hdmi/top.qsf) | `3137462` | Apache-2.0 | 49 |
| riscV | [`HDL/de10-nano/build/top.qsf`](https://github.com/wyvernSemi/riscV/blob/27afe6c1a58eef8324fe9bc215c585216f8c748e/HDL/de10-nano/build/top.qsf) | `27afe6c` | GPL-3.0 | 145 |
| de10nano_vgaHdmi_chip | [`quartus/vgaHdmi.qsf`](https://github.com/nhasbun/de10nano_vgaHdmi_chip/blob/5894d5ba35c1b5f741066c6d0c7384aaa72d495f/quartus/vgaHdmi.qsf) | `5894d5b` | MIT | 34 |
| de10-nano-examples | [`counter/counter.qsf`](https://github.com/nullobject/de10-nano-examples/blob/82b4370d79c36a2f8da7d52770a0ecfe2c9ab79a/counter/counter.qsf) | `82b4370` | none stated | 0 |
| patmos | [`hardware/quartus/de10-nano/patmos.qsf`](https://github.com/t-crest/patmos/blob/a16f0c87b7c85c6a19deeb1251c1f86301473302/hardware/quartus/de10-nano/patmos.qsf) | `a16f0c8` | BSD-2-Clause | 0 |
| superrt | [`SRT/SRT.qsf`](https://github.com/ShironekoBen/superrt/blob/2a75f12ad9644191ec6b3aa49adb546a80007d57/SRT/SRT.qsf) | `2a75f12` | none stated | 34 |
| Matmul | [`de10nano/de10nano.qsf`](https://github.com/voldemoriarty/Matmul/blob/67fd7dc8f8bf1b34e96962606276b2e52ae37bbe/de10nano/de10nano.qsf) | `67fd7dc` | MIT | 0 |

Only the pin numbers are taken, and a package pin number is a fact about the
board, not an expression any of these projects owns. No source file is copied
into this repository.

How many sources reach each group, which is the number that matters when
choosing pins for a target:

| Group | Signals | Sources |
|---|---|---|
| Clocks | 3 | 3 |
| `KEY`, `LED`, `SW` | 14 | 4 |
| ADV7513 HDMI | 35 | 6 |
| `GPIO_0` (JP1) | 36 | 3 |
| `GPIO_1` (JP7) | 36 | 3 |
| Arduino header | 17 | 2 |
| LTC2308 ADC | 4 | 2 |

schoolMIPS and riscV state all 145 rows, so they alone carry the two-source
groups. Three sources place the same 49-signal HDMI, `KEY`, `LED` and `SW` block
in identical relative order; Quartus rewrites assignments in that canonical
order itself, so the shared order is not evidence of copying, and those sources
differ in order across the full table.

Three signal names disagree across sources, and all three are design port names
rather than board signal names: `reset_n` is `KEY[0]`'s pin in
de10nano_vgaHdmi_chip and `SW[3]`'s pin in superrt, and `i2c_scl`/`i2c_sda`
name different header pins in patmos and c5soc_opencl. No canonical board signal
conflicts.

Signals a MiSTer I/O add-on board defines are not on this table. They are add-on
signals carried over this board's expansion headers, not DE10-Nano resources,
and naming them as board pins would misrepresent the board. Every one of them
resolves to a pin already named above, across three different headers:

| MiSTer group | Header it uses |
|---|---|
| `SDRAM_A`, `SDRAM_BA`, `SDRAM_CLK`, `SDRAM_DQ`, `SDRAM_nCAS/nCS/nRAS/nWE` | `GPIO_0` (JP1) |
| `SDRAM_CKE`, `SDRAM_DQMH`, `SDRAM_DQML`, `USER_IO`, `SD_SPI_*`, `SDCD_SPDIF`, `IO_SCL`, `IO_SDA` | Arduino header |
| `VGA_*`, `AUDIO_*`, `BTN_OSD/RESET/USER`, `LED_POWER/HDD/USER`, `SDIO_*` | `GPIO_1` (JP7) |

For example MiSTer's `SDRAM_A[0]` is `PIN_Y11`, which is `GPIO_0[32]` above, and
its `USER_IO[6]` is `PIN_AF17`, which is `ARDUINO_IO[8]`.

All pins are single-ended and use the `3.3-V LVTTL` I/O standard, the same
standard and voltage as the DE10-Lite pins in
[board bring-up](board-bring-up.md#wiring-voltage-ground-and-reset-polarity).

### Clocks

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `FPGA_CLK1_50` | `PIN_V11` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `FPGA_CLK2_50` | `PIN_Y13` | 2 | schoolMIPS, riscV |
| `FPGA_CLK3_50` | `PIN_E11` | 2 | schoolMIPS, riscV |

### Push buttons

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `KEY[0]` | `PIN_AH17` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `KEY[1]` | `PIN_AH16` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |

### Slide switches

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `SW[0]` | `PIN_Y24` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `SW[1]` | `PIN_W24` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `SW[2]` | `PIN_W21` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `SW[3]` | `PIN_W20` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |

### LEDs

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `LED[0]` | `PIN_W15` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `LED[1]` | `PIN_AA24` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `LED[2]` | `PIN_V16` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `LED[3]` | `PIN_V15` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `LED[4]` | `PIN_AF26` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `LED[5]` | `PIN_AE26` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `LED[6]` | `PIN_Y16` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `LED[7]` | `PIN_AA23` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |

### ADC (LTC2308)

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `ADC_CONVST` | `PIN_U9` | 2 | schoolMIPS, riscV |
| `ADC_SCK` | `PIN_V10` | 2 | schoolMIPS, riscV |
| `ADC_SDI` | `PIN_AC4` | 2 | schoolMIPS, riscV |
| `ADC_SDO` | `PIN_AD4` | 2 | schoolMIPS, riscV |

### Arduino header

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `ARDUINO_RESET_N` | `PIN_AH7` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[0]` | `PIN_AG13` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[1]` | `PIN_AF13` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[2]` | `PIN_AG10` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[3]` | `PIN_AG9` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[4]` | `PIN_U14` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[5]` | `PIN_U13` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[6]` | `PIN_AG8` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[7]` | `PIN_AH8` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[8]` | `PIN_AF17` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[9]` | `PIN_AE15` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[10]` | `PIN_AF15` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[11]` | `PIN_AG16` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[12]` | `PIN_AH11` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[13]` | `PIN_AH12` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[14]` | `PIN_AH9` | 2 | schoolMIPS, riscV |
| `ARDUINO_IO[15]` | `PIN_AG11` | 2 | schoolMIPS, riscV |

### GPIO_0 (JP1)

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `GPIO_0[0]` | `PIN_V12` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[1]` | `PIN_E8` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[2]` | `PIN_W12` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[3]` | `PIN_D11` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[4]` | `PIN_D8` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[5]` | `PIN_AH13` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[6]` | `PIN_AF7` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[7]` | `PIN_AH14` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[8]` | `PIN_AF4` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[9]` | `PIN_AH3` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[10]` | `PIN_AD5` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[11]` | `PIN_AG14` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[12]` | `PIN_AE23` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[13]` | `PIN_AE6` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[14]` | `PIN_AD23` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[15]` | `PIN_AE24` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[16]` | `PIN_D12` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[17]` | `PIN_AD20` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[18]` | `PIN_C12` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[19]` | `PIN_AD17` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[20]` | `PIN_AC23` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[21]` | `PIN_AC22` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[22]` | `PIN_Y19` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[23]` | `PIN_AB23` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[24]` | `PIN_AA19` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[25]` | `PIN_W11` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[26]` | `PIN_AA18` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[27]` | `PIN_W14` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[28]` | `PIN_Y18` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[29]` | `PIN_Y17` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[30]` | `PIN_AB25` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[31]` | `PIN_AB26` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[32]` | `PIN_Y11` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[33]` | `PIN_AA26` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[34]` | `PIN_AA13` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_0[35]` | `PIN_AA11` | 3 | basics-graphics-music, schoolMIPS, riscV |

### GPIO_1 (JP7)

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `GPIO_1[0]` | `PIN_Y15` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[1]` | `PIN_AC24` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[2]` | `PIN_AA15` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[3]` | `PIN_AD26` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[4]` | `PIN_AG28` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[5]` | `PIN_AF28` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[6]` | `PIN_AE25` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[7]` | `PIN_AF27` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[8]` | `PIN_AG26` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[9]` | `PIN_AH27` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[10]` | `PIN_AG25` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[11]` | `PIN_AH26` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[12]` | `PIN_AH24` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[13]` | `PIN_AF25` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[14]` | `PIN_AG23` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[15]` | `PIN_AF23` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[16]` | `PIN_AG24` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[17]` | `PIN_AH22` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[18]` | `PIN_AH21` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[19]` | `PIN_AG21` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[20]` | `PIN_AH23` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[21]` | `PIN_AA20` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[22]` | `PIN_AF22` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[23]` | `PIN_AE22` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[24]` | `PIN_AG20` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[25]` | `PIN_AF21` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[26]` | `PIN_AG19` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[27]` | `PIN_AH19` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[28]` | `PIN_AG18` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[29]` | `PIN_AH18` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[30]` | `PIN_AF18` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[31]` | `PIN_AF20` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[32]` | `PIN_AG15` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[33]` | `PIN_AE20` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[34]` | `PIN_AE19` | 3 | basics-graphics-music, schoolMIPS, riscV |
| `GPIO_1[35]` | `PIN_AE17` | 3 | basics-graphics-music, schoolMIPS, riscV |

### ADV7513 HDMI transmitter

| Signal | Pin | Sources | Attesting sources |
|---|---|---|---|
| `HDMI_TX_CLK` | `PIN_AG5` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_DE` | `PIN_AD19` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_HS` | `PIN_T8` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_VS` | `PIN_V13` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_INT` | `PIN_AF11` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[0]` | `PIN_AD12` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[1]` | `PIN_AE12` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[2]` | `PIN_W8` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[3]` | `PIN_Y8` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[4]` | `PIN_AD11` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[5]` | `PIN_AD10` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[6]` | `PIN_AE11` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[7]` | `PIN_Y5` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[8]` | `PIN_AF10` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[9]` | `PIN_Y4` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[10]` | `PIN_AE9` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[11]` | `PIN_AB4` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[12]` | `PIN_AE7` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[13]` | `PIN_AF6` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[14]` | `PIN_AF8` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[15]` | `PIN_AF5` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[16]` | `PIN_AE4` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[17]` | `PIN_AH2` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[18]` | `PIN_AH4` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[19]` | `PIN_AH5` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[20]` | `PIN_AH6` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[21]` | `PIN_AG6` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[22]` | `PIN_AF9` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_TX_D[23]` | `PIN_AE8` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_I2C_SCL` | `PIN_U10` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_I2C_SDA` | `PIN_AA4` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_I2S` | `PIN_T13` | 4 | basics-graphics-music, schoolMIPS, c5soc_opencl, riscV |
| `HDMI_LRCLK` | `PIN_T11` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_MCLK` | `PIN_U11` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |
| `HDMI_SCLK` | `PIN_T12` | 6 | basics-graphics-music, de10nano_vgaHdmi_chip, schoolMIPS, superrt, c5soc_opencl, riscV |

## Targets

[`src/fpga/de10_nano/targets.json`](../../src/fpga/de10_nano/targets.json)
registers this board. The registry names the device, the family, the analysed
timing corners and this page; the
[builder contract](../tools/n2m/SPEC.md#fpga-build) owns that schema.

`nano-smoke` is the flow proof: the counter in
[`nano_smoke.sv`](../../src/fpga/de10_nano/nano_smoke.sv) driving `LED[7:0]`
from `FPGA_CLK1_50`, with `KEY[0]` synchronized through two flops into an
active-high reset. It uses ten pins, each stated by three or more sources:
`FPGA_CLK1_50`, `KEY[0]` and `LED[7:0]`. `nano-invalid` shares that source and
deliberately declares a negative clock period, so it must fail. The registry
states those ten pin numbers because the builder needs them as machine-readable
assignments; every other pin on this board is stated only in the table above.

Quartus analyses this industrial device at four corners, `Slow 1100mV 100C`,
`Slow 1100mV -40C`, `Fast 1100mV 100C` and `Fast 1100mV -40C`, and the builder
requires setup, hold and minimum-pulse-width slack at each of them. It also
requires a drive strength and a slew rate on every `LED` pin, because Cyclone V
reports an output pin without both as an incomplete I/O assignment.

`GPIO_0`, `GPIO_1`, the ADV7513 group, the Arduino header and the LTC2308 are
mapped above but belong to no target. Nothing places them until a target needs
them.

## Verification

- [`tools/n2m/fpga.py`](../../tools/n2m/fpga.py) resolves a target against its
  board registry and derives every device-dependent assignment and evidence
  check from it.
- [`tools/n2m/tests/test_fpga.py`](../../tools/n2m/tests/test_fpga.py) covers the
  registry schema, the board definition and the per-board device and family in
  the generated project files.
- `python3 tools/build.py fpga build nano-smoke` must PASS with its fit, timing
  and assembly reports retained; `nano-invalid` must FAIL. Both are recorded in
  the [builder contract](../tools/n2m/SPEC.md#fpga-build).
- The Questa compile gate elaborates `nano_smoke` with every other registered
  top.

Physical verification of this board is not done. It needs explicit hardware
authorization, and it is not part of the flow proof.

## References

- [DE10-Nano user manual](https://www.terasic.com.tw/cgi-bin/page/archive.pl?Language=English&CategoryNo=165&No=1046)
- [Cyclone V device overview](https://www.intel.com/content/www/us/en/docs/programmable/683694/current/cyclone-v-device-overview.html)
- [Board bring-up](board-bring-up.md): the qualified DE10-Lite path.
- [Builder FPGA build contract](../tools/n2m/SPEC.md#fpga-build)
