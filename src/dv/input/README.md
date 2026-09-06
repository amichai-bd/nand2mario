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
