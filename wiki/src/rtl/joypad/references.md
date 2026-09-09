# Joypad sources

These pins inform original code; no upstream implementation is copied.

- [Pan Docs joypad](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Joypad_Input.md), CC0: active-low selection/read matrix and read-only low nibble.
- [Pan Docs interrupt source](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Interrupt_Sources.md#int-60--joypad-interrupt), CC0: any selected-line falling edge and the shared-line case when both rows are selected.
- [SameBoy joypad](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/joypad.c#L81), Expat: independently corroborates both-row OR and per-line falling-edge detection. Its explicit DMG anti-debounce TODO means it is not proof of physical filtering or pulse timing. Its optional opposite-direction suppression does not override our generated ABI, which preserves all buttons.
- [GateBoy joypad](https://github.com/aappleby/metroboy/blob/36797ad4cf77b3e04ffe45716218a79b5280076a/src/GateBoyLib/GateBoyJoypad.cpp#L140) and [interrupts](https://github.com/aappleby/metroboy/blob/36797ad4cf77b3e04ffe45716218a79b5280076a/src/GateBoyLib/GateBoyInterrupts.cpp#L88): die-based aggregate input and four-stage filter model. Its external matrix model uses an if/else row choice, so it is not an oracle for the specified both-row digital matrix. No repository-root license was found at this pin; reference-only, no copied source.

The generated direct profile takes precedence over physical boot reset comments.
Physical switch bounce is outside the [JOYP owner](MAS_joypad.md). GateBoy filtering must not be silently
invented as an additional delay, nor may emulator behavior be called measured
silicon. Event transport is reviewed against the existing IF and CPU boundaries.
