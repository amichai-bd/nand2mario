# Shared input verification

The [input contract](../../../wiki/src/rtl/input/MAS_input.md) defines one atomic
mask and the [JOYP contract](../../../wiki/src/rtl/joypad/MAS_joypad.md) defines
selected-line events. The matrix checks 256 masks, four row selections and both
sources with an inverse inactive-source mask, real JOYP and real IF. Actual
mask, selector and event faults must fail independently. A separate physical
boundary fault targets the local named assertion.

The ordering fixture checks a simultaneous source/physical update, inactive
host writes, repeated values, asynchronous reset cancellation and retained
physical observation across core reset. The UART input fixture checks real
serial MMIO/legacy INPUT replies, all readbacks, invalid length/value/state
precedence, cache replay and reset. The power fixture uses both sources with actual CPU HALT/STOP, paused input
updates and effective-mask successor retirement checks. Legacy endpoint,
snapshot, stopped-STEP and integration checks preserve existing contracts.
[PR160](https://github.com/amichai-bd/nand2mario/pull/160) retains run evidence.

The physical acquisition fixture follows the
[board controls contract](../../../wiki/src/fpga-controls.md). `adc-pairs`
checks four literal X/Y publications, stalled-command ordering, timeout drain,
Y acceptance on the expiry edge, late-response rejection, and cancellation on
ADC availability loss. Its data corruption and wrong-channel targets sensitize
the public-pair oracle and named assertion. This fixture drives the public ADC
response interface; it does not replace installed Intel model, button/axis,
shared-input composition, or physical board evidence.

`controls-mask` composes the actual button filter, calibrated mask and shared
input owner. Its 24 literal checks include a debounce completion coincident
with a complete pair, hysteresis and reversed polarity, bounce, tick deferral,
stale-axis release, source isolation and reset. The negative corrupts the actual
physical mask. This bounded fixture does not replace acquisition or board proof.

`adc-backend` uses the installed encrypted ADC model, real reset controller and
producer, with Intel's documented user-stimulus simulation mode. Original
builder-generated two-column files supply channel1=0.625V and channel2=1.25V;
the independently calculated expected codes are1024 and2048 for2.5V reference.
All17 filenames are provided because the retained model opens each at startup.
The [stimulus format](https://docs.altera.com/r/docs/683596/24.1/max-10-analog-to-digital-converter-user-guide/user-specified-adc-logic-simulation-output)
defines row sequencing and repetition. The model configuration changes only
simulation parameters; the actual clock, reference selection and channel mask
remain those used by synthesis. Fixed-output attempts remain failed evidence.
The fixture checks ordered responses, cancels an outstanding X by injecting
PLL lock loss, then requires complete fresh pairs after recovery. Its negative
changes the actual Y response. Acceptance requires clean checked model execution; it does not prove analog
conversion accuracy or physical wiring.

`controls-lifecycle` checks each button's press/release boundary, adjacent axis
thresholds, retained extremes, and reset or ADC cancellation from five public
transaction phases. It also checks deadline equality, stale replacement and
missing-Y draining while buttons remain live. `controls-unsolicited` requires
the normal named protocol failure. `controls-sticky` compiles the same producer
with explicit `SYNTHESIS` assertion exclusion to observe the hardware fault
persisting across ADC recovery, live buttons, and release only by global reset.
The recovery negative corrupts the actual resumed physical mask.

`controls-wire` connects the actual producer, UART shared input owner, JOYP,
timebase and Intel-backed VGA bridge. Public ADC command/response stimulus
supplies center and low-axis samples; it does not replace or validate the
unaccepted vendor ADC simulation. Eight-clock serial bits and shortened filter
intervals bound this composition test; the board parameters remain unchanged.
Five four-register wire readbacks cover UART-default isolation, explicit physical
selection and debounced A/B plus directional masks. Two writes make 22 replies.
The paused timebase must remain paused while the diagnostic VGA producer advances;
96 displayed samples are checked from literal geometry and shade arithmetic.
The negative changes actual JOYP observation from 16 to zero. Physical wiring,
ADC accuracy, and the generated board clocks are separate acceptance evidence.

## ADC doubles

Contract: [DE10-Lite physical controls](../../../wiki/src/fpga-controls.md#acquisition-and-filtering).
`tb_sim_adc_double` drives `n2m_adc_backend` directly, so under `VERILATOR` it
exercises `n2m_sim_adc_pll` and `n2m_sim_adc_control`. It owns the 10 MHz
reference, `pll_areset` and `reset_sys`, and writes `adc_ch0.txt` to
`adc_ch16.txt` at time zero in the builder's two-column format: channel 1 is
the product fixture (0.625 V), channel 2 carries four rows (1.25, 2.0, 3.3,
-0.5 V) and the others 0 V.

| Requirement | Independent check |
|---|---|
| PLL reset | No `clk_adc` edge and `pll_locked` low while `areset` is high |
| PLL ratio | Ten `clk_adc` edges in the first microsecond after release |
| Lock delay | `pll_locked` rises 6.4 to 6.5 us after release at a falling reference edge (64 counted edges) |
| Control reset | `command_ready` low in reset, high two cycles after release |
| Handshake | A held command is accepted once; `command_ready` stays low until the response cycle; one response per command |
| Channel tag and codes | Channel 1 gives 1024; channel 2 replays 2048, 3276, 4095 (clamped), 0 (clamped), then 2048 |
| Latency | 195 to 206 system cycles from acceptance to response (80 ADC edges at 10 MHz) |
| Reset abandon | `reset_sys` during a conversion yields no response; the next command completes |
| Lock loss | `areset` during a conversion drops `locked` at once, stops `clk_adc`, yields no response and blocks the port until lock returns |
| Diagnostics | `+bad_channel` trips the backend's `adc_command_channel`; `+missing_stimulus` writes an empty channel file and trips `N2M_SIM_ADC_STIMULUS_EMPTY` |
| Checker proof | `+corrupt` forces channel 1 data to 0 and requires the exact `ADC_DOUBLE_DATA` diagnostic |

Targets: `sim-adc-double` (pass), `sim-adc-double-corrupt`,
`sim-adc-double-channel` and `sim-adc-double-missing`, all
`simulator: verilator`. `tb_adc_backend` composes the same backend with the
real reset controller and producer; its `adc-backend` targets still declare the
vendor model and follow the builder's simulator policy.

