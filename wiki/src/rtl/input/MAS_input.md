# Shared input owner

The shared owner selects one complete Game Boy button mask. UART is the reset
default. PHYSICAL explicitly selects the latest coherent external mask. Both
sources use the same [JOYP](../joypad/MAS_joypad.md) event and wake path.
This owner does not acquire ADC samples or synchronize individual buttons.

## Interface and ownership

`n2m_input` runs on `clk_sys`. Package-owned `input_write_t` carries an accepted
host transaction: valid, source_write and value. UART core control emits it at
its existing INPUT_APPLY edge with `gb_tick=0`. Legacy INPUT and WRITE_HOST(INPUT)
normalize to this one operation. WRITE_HOST(INPUT_SOURCE) changes the selector.
The endpoint returns the dot count at acceptance; cached retransmissions do not
execute it again. See [wire ordering](../interfaces/MAS_interfaces.md).

`physical_commit` accompanies a coherent eight-bit `physical_buttons` mask on
`clk_sys` with `gb_tick=0`. The physical producer owns synchronization, debounce
and scheduling between dots. The valid signal must be known; committed data
must be known. There is no ready signal or input queue.

The owner retains host and physical shadows and one source bit. `host_buttons`
and public UART `buttons` retain the legacy host-mask meaning. `physical_observe`
reports the physical shadow even when UART is selected. `source_observe` reports
UART0 or PHYSICAL1. `effective_buttons` selects the authoritative shadow.
Host readbacks use these same observations, not a duplicate register bank.

All accepted fields at one edge resolve together. A source switch concurrent
with a physical commit selects the newly supplied mask. The combinational
`effective_update` record carries that final mask before the edge, with valid
only when it differs from the current effective mask. Connect valid/buttons
directly to JOYP input_commit/input_buttons so both owners capture together.
JOYP registers its selected-line fall at this A edge; IF consumes it at B.
No intermediate mask or extra event pipeline is introduced.

UART-mode physical updates change only their shadow. PHYSICAL-mode host writes
change only their shadow. Repeated identical values create no effective update.
Opposite directions and simultaneous buttons are preserved without filtering.

## Reset and power

Global reset asynchronously clears all shadows and selects UART. Core reset
asynchronously clears the host shadow and selects UART, producing effective0.
The physical shadow survives core reset and may accept external updates while
it is held. This retention is the delegated physical-input rule, not a claim
about the prior host-only endpoint. PHYSICAL must be selected explicitly again.
Both resets suppress effective_update, and JOYP reset cancels pending events.
Existing core-reset retry-cache retention and global-reset cache clearing remain.

Pause, CPU HALT and STOP do not block an accepted input transaction. Input does
not manufacture a Game Boy dot. Selected activity and request events use the
existing JOYP/IF boundary; oscillator restart remains the approved CPU contract.

## Verification

The full issue155 gate includes generated address/value rejection before
transport and before RTL effects; equivalent masks across both sources and all
four JOYP row selections; isolation and atomic switching; reset and physical
shadow retention; actual CPU HALT/STOP and pause; cached replay; and actual
mask/source/event faults plus a named assertion failure. Implementation and
runtime completion are tracked in PR160, not asserted by this specification.
