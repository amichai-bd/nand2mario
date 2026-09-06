# Interrupt owner checks

Contract: [MAS_interrupts](../../../wiki/src/rtl/interrupts/MAS_interrupts.md).
Use the shared builder and Questa; source levels are original scripted stimuli,
not synthetic implementations of the timer, PPU, JOYP or serial owner.

`interrupts` checks all32 source masks,256 IE bytes, IF upper read bits,120
per-bit initial/write/ack/rise combinations, held-source clearing and rearming,
both reset paths and cancellation between A capture and B storage. The checker
observes public stored and resolved outputs and emits expected/actual CSV rows.
The literal truth table does not inspect the DUT next-state calculation.
Three targets force actual lost state, incorrect source history and lost
acknowledgement; expected data remains unchanged.

This first slice does not complete issue133. Explicit pre/on/post A/B schedules,
CPU T3/stack selection and composed retirement snapshot fixtures remain to be
added. No actual runtime result exists yet. Full criteria remain in the issue.
