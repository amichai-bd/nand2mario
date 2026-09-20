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

`controls-running` composes the same actual producer, shared input owner and JOYP
with the timebase running. `controls-wire` and the board's own `controls_proof`
compose those three modules only while the timebase is paused, so `gb_tick` never
asserts and no JOYP bus cycle happens in either; this fixture releases the pause
and a bus owner writes the row selection and reads FF00 on tick edges, which is
the boundary prepared CPU service uses. No host is present, so the owner selects
the physical producer out of reset the way a
[host-free composition](../../../wiki/src/rtl/system/MAS_system.md#host-free-composition)
does. Fourteen held masks are read through all four row selections: released, one
and four action buttons, each axis extreme, the hysteresis band that holds a
direction, the centre, both axes with an action button, and a full reversal in one
published pair. Public ADC command/response stimulus supplies the samples;
eight-cycle debounce and a 32-cycle interval bound the run and the board values are
unchanged. Concurrent monitors require the commit rule in both directions, no
commit on a tick and no JOYP write off one; the opposing-axes rule at the published
mask, at the JOYP button field and at the direction-row read; and JOYP register
stability on public outputs. A ten-value sweep of both axes while ticks run is what
puts a pending mask change on a tick edge, and the run requires a nonzero census of
ticks, commits, effective updates and deferred commits, plus all four direction
lines observed. `JOYP_STATE_STABLE` holds throughout.
`controls-running-corrupt` changes the actual register read;
`controls-running-stable` moves the JOYP button field with no accepted mask and no
select write, which sensitizes the register-stability witness. This composition does
not establish physical wiring, ADC accuracy or the generated board clocks.

`controls-held` drives what `controls-running` assigns low and never moves:
`core_reset`, with a mask held. The two owners do not lose the same state at a core
reset — JOYP clears its button field while the input owner's physical shadow
survives — and the update between them is a difference, so the fixture settles what
the program reads afterwards. One producer and one reset drive two actual input
owners, one per value of `PHYSICAL_SOURCE_DEFAULT`, and both JOYPs are read at FF00
through all four row selections on tick edges: 40 checks over ten phases. Phase 0 is
the power-up ordering, with the button held before the global reset releases and the
single core reset issued two cycles after it, as the host-free start path does;
measured here, that reset lands at cycle 3 and the first commit at cycle 11, so the
held button arrives on the ordinary commit rather than across the reset. Phases 1 to
4 are the mechanism, with the mask already published and read, at four alignments:
the reset driven on a negedge from the stimulus block, one delay past a posedge,
released between edges, and as a single cycle. Phase 5 changes the mask while the
reset is held, because the producer never sees core reset and commits through it.
Phases 6 and 7 select the physical producer on the host-default instance by host
write and take it back by core reset. Every reset exit with a mask held costs exactly
one update on the physical instance and none on the host-default one, a released mask
costs none on either, and the host-default instance reads released at every reset exit
throughout. Against the pre-fix owner the fixture fails at phase 1 with zero updates
while phase 0 passes, which is what separates the two cases.
`controls-held-corrupt` changes the actual JOYP observation to released at the first
post-reset read, which is the pre-fix symptom itself and sensitizes the held-mask
oracle. This fixture does not establish physical wiring, ADC accuracy or the board's
own filter and interval values.

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
`simulators: ["verilator"]`. `tb_adc_backend` composes the same backend with the
real reset controller and producer; its `adc-backend` targets still declare the
vendor model and follow the builder's simulator policy.
