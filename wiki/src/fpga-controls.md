# DE10-Lite physical controls

Status: implementation contract for [issue156](https://github.com/amichai-bd/nand2mario/issues/156).
Board execution and acceptance remain unproven. The
[shared input owner](rtl/input/MAS_input.md) already implements source selection;
this producer supplies its physical mask.

## Electrical boundary

Use a passive two-axis potentiometer joystick and four normally-open switches.
Supply the potentiometers from 3.3 V and common ground. Connect each button
between its input and ground with an external 10 kohm pull-up to 3.3 V.
Do not connect an unidentified module, a powered 5 V digital output, or an
unknown terminal orientation. Actual part ratings, terminal order, measured
supply, common ground, and wiring must be recorded before programming.

| Function | Connector | FPGA resource |
|---|---|---|
| X, low means left | A0 / ADC_IN0 | ADC1 channel1 |
| Y, low means up | A1 / ADC_IN1 | ADC1 channel2 |
| A, B, Start, Select | D2, D3, D4, D5 | AB7, AB8, AB9, Y10; inputs, 3.3-V LVTTL |
| UART receive, transmit | D0, D1 | AB5, AB6; existing UART owner |
| ADC reference clock | ADC_CLK_10 | N5, 10 MHz; dedicated PLL input |
| Diagnostic board reset | KEY0 | B8, active low; 3.3-V Schmitt trigger |

JP8 halves the analog header voltage before ADC1. A 3.3 V input therefore
corresponds nominally to code2703, not4095, with the 2.5 V ADC reference.
Only A0/A1 are enabled. Other header pins are not driven by this producer.
VGA pins and the pixel clock remain owned by the existing display contract.

## Acquisition and filtering

Use the installed Intel Modular ADC control core only, ADC1, internal 2.5 V
reference, 125 ksample/s, and a dedicated ALTPLL c0 at10 MHz from N5 in
no-compensation mode. This clock feeds the ADC's dedicated input; it need not
align a fabric clock or external output to the reference phase. The
control core's command and response interfaces run at50 MHz `clk_sys`; its
hard-block crossing uses the vendor handshake and corresponding scoped SDC.
The generated PLL, vendor HDL, atom models, and constraints remain build
artifacts with recorded source hashes. There is no alternative behavioral ADC
implementation in the product.

The two-channel proof explains only the pinned Intel control core's unused
dual-ADC next-state variable and twelve outputs of its unused channel17
temperature-averaging FIFO. Its diagnostic checker requires the complete
15-message inventory and exact vendor source hashes; all other diagnostics
retain the shared builder's strict treatment. The raw messages remain evidence.

The producer requests X then Y, holds each command until accepted, and
publishes only complete ordered pairs. Start a pair every1 ms when the prior
pair has completed. A missing response does not generate an emulated tick or
block buttons. Each pair has a20 ms deadline starting at acceptance of its X
command. Deadline expiration discards partial X. Expiration of a previously
fresh pair's20 ms freshness interval also clears both axis directions and
discards any partial replacement pair. Expiration wins over a response on the
same edge.

After expiration, drain and discard an outstanding response before issuing a
new X command. Cancel a not-yet-accepted Y command. An indefinitely missing
response leaves directions released while buttons continue. A late Y cannot
combine with stale X; only a new complete pair restores freshness. Unexpected
response channels latch a protocol fault, discard acquisition until global
reset, and raise a named verification failure. They do not block buttons.

Synchronize each button through two system registers. Accept a changed level
after5 ms of consecutive agreement; bounce restarts only that button's counter.
All four buttons can change together. Reset initializes them released.
The filter exposes the button proposal accepted on the current edge. The mask
combines that proposal with the axis pair accepted on that same edge.

Each axis has build-time minimum, center, maximum, and polarity calibration.
Initial nominal values are0,1352,2703. These are design defaults, not measured
calibration. Physical acceptance records measured endpoints and center and
uses the reviewed matching build. Require minimum < center < maximum and
at least512 codes on each side. Enter a direction at one third of that side's
calibrated span from center; release it within one quarter of the span.
Integer thresholds round down. The space between thresholds supplies
hysteresis. Crossing directly to the other direction releases the old one
and selects the new one from the same sample.

## Input, reset, and indication

Build the complete eight-bit mask in the shared owner's documented bit order.
Commit changes only on a `clk_sys` edge with `gb_tick=0`; retain pending changes
until that edge. A simultaneous axis pair and button change produce one
coherent mask. Pause, HALT, STOP, and core reset do not stop acquisition.
Global reset releases controls and discards incomplete samples. ADC PLL lock
loss invalidates axis data and restarts acquisition after synchronized lock
recovery; it does not create a clock or reset the Game Boy.
Unlike a missing-response timeout, backend reset abandons an outstanding ADC
transaction because its response may never arrive. It preserves a protocol
fault until global reset. Buttons remain live during recovery.

LEDR[7:0] show the effective shared input mask, LEDR8 shows PHYSICAL selection,
and LEDR9 shows fresh ADC pair availability. LED outputs are active high.
The shared input owner remains authoritative for UART isolation, physical
shadow retention, source changes, and core-reset selection of UART.

## Board diagnostic composition

`controls_proof` connects the actual producer to `n2m_uart`, whose input owner
is the sole selector, then sends its effective update to `n2m_joypad`. LEDs use
the owner's effective mask and source observation. A generated-shade VGA source
uses the existing clocking, frame bridge, Intel memories and scan output. Its
pattern includes the JOYP button observation and continues while the emulation
timebase is paused. It is a diagnostic image, not a PPU frame or gameplay proof.

This diagnostic supports PING, host-register reads, INPUT and input-source
writes through the real serial endpoint. It has no CPU, ROM service or snapshot
owner. Their completion/valid inputs remain deasserted; no successful execution,
initialization or frame reply is fabricated. RESET, RUN and STEP reject the
missing valid image. LOAD_BEGIN, READ_ROM and SNAPSHOT are unsupported diagnostic
operations and can wait indefinitely; use KEY0 to recover if one is sent.
The physical test uses only the supported input operations. The build must
provide a nonzero recorded identity before physical use.

System reset cancels the ADC backend as well as the sampler. ADC lock loss
alone invalidates acquisition while buttons, UART and VGA continue. The
combined project's pin, clock, reset and timing proof is required independently
of earlier component fits. Its implementation does not close physical acceptance.
The bridge's existing counter/sequence observations remain virtual proof
outputs so its checked CDC metadata paths survive synthesis. They add no
physical output assignments. Core reset restarts the diagnostic source epoch
and frame assembly through the existing bridge contract.

## Sources and acceptance

The [Terasic manual](https://www.terasic.com.tw/cgi-bin/page/archive_download.pl?Language=English&No=1021&FID=a13a2782811152b477e60203d34b1baa),
footer October17,2022, tables3-2/3-5/3-8 and figure3-20, defines board clocks,
LEDs, digital pins and analog scaling. Retained PDF SHA256:
`ab2c47e5a7e4ac26874013bfe05df31e2d498bc9a7f9f6b33bd931c64db848ac`.
The [Intel ADC guide](https://www.intel.com/content/www/us/en/docs/programmable/683596/22-1/configuration-4-adc-control-core-only.html)
defines the control-only configuration; its
[clock table](https://www.intel.com/content/www/us/en/docs/programmable/683596/22-1/valid-adc-sample-rate-and-input-clock.html)
permits10 MHz at125 ksample/s. Installed25.1std source parameters and physical
fit must corroborate the selected implementation.

ADC verification uses the vendor's user-stimulus simulation mode with original
builder-generated two-column voltage files and recorded hashes. Channel1 has
0.625V and channel2 has1.25V; inactive channels have0V. Each file has one row,
which the documented model repeats. The independent expected codes are1024
and2048. Simulation mode and filenames do not change the hardware clock,
reference selection or channel mask.

The installed generator encodes the reference as `(Vref / 3.3) * 65536`;
the integer49648 represents the selected2.5V reference. Its voltage conversion
uses integer truncation of `(Vin / Vref) * 4096`. Ideal2.5V and the encoded
reference both produce the stated expected codes. These rules come from
`altera_modular_adc_hw.tcl` (SHA256
`0de2a5dab422d7c34100603413b6746ab86f77ca4aa3afe4740191692aee4669`,
lines3278,3905 and4638). The
[official stimulus format](https://docs.altera.com/r/docs/683596/24.1/max-10-analog-to-digital-converter-user-guide/user-specified-adc-logic-simulation-output)
defines file columns and repetition. Expected samples alone do not excuse
runtime diagnostics; earlier fixed-mode failures remain failed evidence.

Issue156 requires independent Questa filtering/fault/atomicity checks, early
ADC fit, final constrained FPGA proof, and actual verified controls with
visible indication and UART isolation. Simulation does not satisfy the
physical criterion. Missing hardware facts leave that criterion open.
