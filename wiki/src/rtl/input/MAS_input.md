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
only when it differs from the mask JOYP last accepted. Connect valid/buttons
directly to JOYP input_commit/input_buttons so both owners capture together.
JOYP registers its selected-line fall at this A edge; IF consumes it at B.
No intermediate mask or extra event pipeline is introduced.

UART-mode physical updates change only their shadow. PHYSICAL-mode host writes
change only their shadow. Repeated identical values create no effective update.
Opposite directions and simultaneous buttons are preserved without filtering.

## Reset and power

`PHYSICAL_SOURCE_DEFAULT` decides which producer reset selects, and defaults to
UART: the host owns the selection, so every existing composition keeps the host's
own mask out of reset. A composition on a board with no host link selects 1,
because nothing else would ever release the buttons and every physical press
would be discarded for the life of the image. The choice is compile-time, and the
selection the register then holds is still the host's to change if one appears;
[the composition](../system/MAS_system.md#host-free-composition) owns which
boards select it.

Global reset asynchronously clears all shadows and selects the default producer.
Core reset
asynchronously clears the host shadow and selects that same default.
Under the UART default that produces effective0; under PHYSICAL it produces the
surviving physical shadow.
The physical shadow survives core reset and may accept external updates while
it is held. This retention is the delegated physical-input rule, not a claim
about the prior host-only endpoint. Under the UART default PHYSICAL must be
selected explicitly again.
Both resets suppress effective_update, and JOYP reset cancels pending events.

The first edge out of a core reset re-offers a nonzero effective mask. JOYP clears
its button field at that reset and this owner's physical shadow does not, so the
two owners hold different masks, and one update carrying a mask that never changed
is what agrees them again. Without it a button held across the reset would stay
invisible to the program until it moved. This is why the difference is taken
against the mask JOYP last accepted rather than against this owner's own previous
level. Every non-reset edge leaves that record equal to the effective mask, so no
other edge changes; only the interval between a core reset releasing and the next
edge holds the two apart, and that interval is the re-offer itself. A
released mask needs no update and produces none, which keeps the UART default's
effective0 exactly as it was. The
[held-mask check](../../../../src/dv/input/README.md) settles both compositions
against one producer and one reset.

Existing core-reset retry-cache retention and global-reset cache clearing remain.

Pause, CPU HALT and STOP do not block an accepted input transaction. Input does
not manufacture a Game Boy dot. Selected activity and request events use the
existing JOYP/IF boundary; oscillator restart remains the approved CPU contract.

## DE10-Lite synthesis

Tying the physical producer off does not remove the published record. The
[`v05_proof`](../../../../src/fpga/de10_lite/v05_proof.sv) wrapper drives
`physical_commit` and `physical_buttons` with constants, and the `v05-board` fit
of it still holds all eight `published_q` bits as dedicated registers at
`u_system|u_uart|u_input|published_q`. The owner's fitted register count there is
17: eight for the host shadow, one for the source bit, eight for the record. The
physical shadow is what the tie-off removes, because a constant commit leaves it
at zero forever; no `physical_q` register survives in that image with or without
the record.

The consumer decides whether the record survives, not the tie-off.
[`sdram_proof`](../../../../src/fpga/de10_lite/sdram_proof.sv) ties the same two
inputs off and carries the same host endpoint, and there the record is removed:
that top leaves `effective_update` unconnected and instantiates no JOYP, so the
register drives nothing. Every DE10-Lite target that routes `effective_update`
into an actual JOYP keeps it. `v05` and `v05-board` do so through
[the composed system](../system/MAS_system.md), and `v05-controls-board` and
`controls-board` through their own wrappers. `v05-board` is the named DE10-Lite
evidence for this register because it is the one that both routes it and fits;
`controls-board` does not build
([#904](https://github.com/amichai-bd/nand2mario/issues/904)). Measure a change
to the update comparison on `v05-board`, not on a target that drops the register.

Fitted cost on `v05-board` (Quartus Prime Lite 25.1std, `10M50DAF484C7G`, one
pinned build identity across both revisions): dedicated logic registers 5,259 to
5,267, combinational functions 11,606 to 11,598, logic elements 12,866 to 12,888,
and a changed netlist. Pins, virtual pins, memory bits, PLLs, UFM and ADC blocks
are unchanged, and the image fits at 26% of logic. No slack entry is negative
before or after and the design's worst slack is the same 0.055 ns `Fast 1200mV
0C` hold on the system PLL clock, but 44 of the 54 entries do move, by up to
1.115 ns; the largest loss leaves 3.473 ns of setup margin on that clock.

Those three resource totals do not sum, and the fitter's own partition is why.
Logic elements count LUT-only, register-only and LUT-and-register cells, which
are disjoint; combinational functions counts the first and third and dedicated
registers counts the second and third, so the shared class is counted twice
across those two totals. Measured: LUT-only 7,607 to 7,621, register-only 1,260
to 1,290, LUT-and-register 3,999 to 3,977, each triple summing to its element
total. The +22 elements are therefore 22 cells that stopped holding a function
and a register together, not added logic. The owner's own footprint falls, 26
logic cells to 25, so that repacking is in the rest of the design rather than
here. Why the fitter repacked is not established; it is what the moved slack
entries above accompany, and it costs no negative slack and the same worst path.

## Verification

The [input verification](../../../../src/dv/input/README.md) covers generated address/value rejection before
transport and before RTL effects; equivalent masks across both sources and all
four JOYP row selections; isolation and atomic switching; reset and physical
shadow retention; a mask held across a core reset; actual CPU HALT/STOP and pause;
cached replay; and actual
mask/source/event faults plus a named assertion failure. These component checks
do not establish physical wiring or acquisition acceptance.
