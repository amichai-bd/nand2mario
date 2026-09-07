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
