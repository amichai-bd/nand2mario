# VGA frame bridge

Design for [#80](https://github.com/amichai-bd/nand2mario/issues/80).
The [shared clock/reset/CDC contract](../../clocks-resets-cdc.md) owns raster
geometry, scaling, reset, bank transfer order and physical timing budgets.
This page defines the module boundaries and presentation choices. The
[bridge](../../../../src/rtl/vga/n2m_frame_bridge.sv),
[scanout](../../../../src/rtl/vga/n2m_vga_scan.sv) and
[RAM](../../../../src/rtl/vga/n2m_frame_ram.sv) implement these boundaries.
Measured resource/timing and simulation evidence is retained with
[the implementation review](https://github.com/amichai-bd/nand2mario/pull/111).

## Source and observation

`n2m_frame_bridge` consumes `clk_sys`, `reset_sys`, synchronous `core_reset`,
`clk_pix`, and `reset_pix` from the shared clock/reset controller. The two domain
resets belong to the same global reset; independently resetting a mailbox end
is invalid. Pixel-clock stoppage does not backpressure the source.

The system-domain source presents `source_valid`, `source_start`, and final
two-bit `source_shade`. Each valid edge supplies one row-major pixel.
`source_start` accompanies the first pixel of a new frame; exactly 23040 valid
pixels complete a frame. Gaps are allowed at any pixel. A new start during a
partial frame, a pixel without a start, or an extra pixel after completion is
invalid. Core reset abandons partial progress and requires a new start.
Reset takes priority over a valid pixel on the same edge.

`source_epoch[31:0]` and `source_dot[63:0]` come from the emulated-core controller.
The epoch remains constant throughout a frame; dot identifies the number of
completed emulated dots on each supplied pixel edge. The bridge numbers completed
source frames from zero after core reset with a 64-bit sequence. All counters
wrap modulo their width; verification bounds do not span wrap.

The observer outputs `observe_valid`, `observe_index[14:0]`, `observe_shade[1:0]`,
`observe_complete`, `observe_epoch[31:0]`, `observe_sequence[63:0]`, and
`observe_dot[63:0]` describe that same accepting system edge. Completion accompanies
pixel 23039. They are derived before presentation selection and have no ready
input. A passive verification sink therefore sees even presentation-discarded
frames. Gaps and resets suppress observer validity; partial frames are not complete.

This stream is also the stable assembly boundary for the future
[dedicated snapshot stores](../interfaces/MAS_interfaces.md#immutable-frame-snapshot).
The observer sees stable pixel values at the sampling edge; it does not grant
random access to a VGA bank. #93 owns assembly, atomic publication, immutable
host readback, packed byte format and snapshot command behavior. No host command
may lease any of these three banks.

## Ownership and storage

The system side tracks writer, last acknowledged display, optional pending bank,
and free bank. It applies acknowledgements before a same-edge source completion,
as required by the shared contract. Completion while either peer is unready or
an offer is outstanding discards presentation only and increments `discard_count`
in `clk_sys`. Core reset clears source progress and sequence, but does not clear
mailbox phases, presentation counters, or complete frames.

The pixel side synchronizes request, waits the additional capture edge, and
holds the captured bank/sequence until the permitted blanking boundary. The
display sequence, epoch and validity change only with that swap. Epoch travels
in the same stable bundle so core-reset sequence reuse remains unambiguous.
`repeat_count` is a
pixel-domain counter incremented at each permitted swap boundary with an already
valid displayed frame and no captured replacement. Initial black frames do not
count as repeats. Presentation counters clear on global reset only. Their ports
are domain-local observations; a host consumer must use the separately specified
status snapshot mailbox, not sample them as live multibit crossings.

`n2m_frame_ram` preserves the display-facing scalar boundary over the
[shared explicit Intel memory](../common/MAS_memory_primitives.md). It has one
system write port and one pixel read port, 23040 entries of two bits, and one
registered read stage. Three instances implement the ownership banks. Memory
contents and read data have no reset initialization. A read is enabled only for
a valid display bank and scaled-image coordinate. Ownership excludes same-bank
read/write collisions; collision results are never consumed. The same `n2m_intel_ram` instance and parameters run against the installed
Intel model in Questa and synthesize for MAX 10. A is write-only and B is
read-only with independent clocks. Its address/input stage provides the one-edge
read; the primitive output is unregistered, so no second RAM stage is added.
The adapter ties reset inactive, discards unused valid/A-read outputs, and gates
inactive addresses to zero. Owners still mask startup and reset validity; the
store is never cleared. The builder records the three exact reviewed Intel
model coercion diagnostics; prohibited collision results remain unused.

## Scanout

`n2m_vga_scan` generates the shared contract's raster and source address. RAM
read latency is one pixel edge; a following output register applies shade
conversion. Coordinates, active-video validity, image validity, and sync follow
those same two stages. Reset masks RGB to zero and sync inactive immediately,
including with a stopped pixel clock. Startup invalid pipeline stages are black
with inactive sync. The first valid output corresponds to raster coordinate zero.

| Final DMG shade | Each four-bit RGB channel |
|---|---|
| 0, white | `F` |
| 1, light gray | `A` |
| 2, dark gray | `5` |
| 3, black | `0` |

All three channels have the same value. Borders, blanking and invalid display
banks are black. This is presentation conversion after DMG palette selection;
it does not change stored shades or the snapshot ABI.

## Verification boundary

The [test plan](../../../../src/dv/vga/README.md) and
[independent source oracle](../../../../src/dv/vga/tb_vga.sv) supply asymmetric frame/row/column patterns and
records every observer completion. A raster oracle checks every output coordinate,
sync, border and scaled shade. Ownership monitors check immutable offers,
disjoint RAM ownership, blanking-only swaps, acknowledgement ordering and
counter explanations. Deliberate illegal bank reuse and active-video swap must
produce their specific nonzero failures in Questa. Clock/reset schedules include
faster and slower sources, pause, core reset, outstanding-offer global reset,
lock loss, and stopped pixel clocks.

Actual generated PLL and Quartus evidence must prove three explicit dual-clock
banks, fit resources, exact bundle endpoints and delay bounds, synchronizer
stages, output bounds and both reference-frequency timing analyses. This design
description is not that evidence. Physical monitor, pin/wiring and voltage proof
remain #28/GAP-012.

The [FPGA proof](../../../../src/fpga/de10_lite/vga_proof.sv) feeds original shades
from the emulated tick and exposes domain-local status through virtual ports.
The [target registry](../../../../src/fpga/de10_lite/targets.json) owns manual-derived
VGA pin assignments: DE10-Lite manual v1.7, table 3-11, printed page 36. The
manual and its verified hash are linked by the shared clock contract. The proof
uses 3.3-V LVTTL and an explicit 8 mA VGA output setting; connected-device,
resistor-load and electrical verification remain physical bring-up work.

## Reference method

The owner-supplied local frog-bui revision
`da16dc841d50c6c48827225b91dac6b8716b4311` was inspected read-only, including
`src/rtl/rv_cpu/rv_vga_subsystem/rv_vga_text_ram.sv`. Its separately clocked
scanout port and explicit RAM exception informed the boundary here. This local
unpublished revision has no verified file-level reuse grant. No HDL, font or
fixture source was copied; the project-specific two-bit ownership RAM and
independent asymmetric pattern are original. See the
[reference study](../../rtl-reference-style.md) for the related staged-metadata
and test-method observations.

## Register and assertion form

Ordinary state uses the shared register macros. Attributed two-stage crossing
registers use the explicit asynchronous reset macro with unchanged stage names
and polarity. The RAM uses the shared Intel primitive boundary; its data has no reset or
initialization and no additional output register.
Named concurrent assertions check source ordering/known values, immutable writer
ownership, pending bundle stability and display-bank changes only after a swap
boundary. The source-side ownership model and full raster oracle retain detailed
procedural comparisons independent of those local assertions.


## Explicit memory fit evidence

The shared wrapper's bidirectional primitive configuration fits as three
True Dual Port/Dual Clocks logical banks although the adapter uses A only for
writes and B only for reads. Each remains 23040x2, six M9Ks and 46080 stored bits;
three banks retain 18 M9Ks and 138240 bits. Input/address registers are enabled,
output registers are absent, initialization is unknown and mixed-port collision
behavior is unconsumed. The changed classification is not an added public port.

The VGA checker inspects all 18 fitted MAX10 RAM atoms, their bank/bit partition,
logical dimensions, system/pixel clocks, write-only A/read-only B roles, inactive
clears and byte-enable wiring, uninitialized contents and absence of an extra
output stage. It retains the existing CDC, bundle, output and timing checks.
The builder pins the installed primitive definition/declaration/model for every
consumer of the shared RAM, and requires a retained device netlist in its cache.

The Intel-model raster regression retains the original per-pixel oracle and
coverage. Its 600-second limit accommodates the installed vendor model, with
raster progress messages and sampled first/last-column pixel traces. Bounded
public wave windows cover reset and first-image output. An actual extra RAM
response edge must fail the independent coordinate/shade comparison. A timeout
is a failed run, never a substitute for the final PASS signature.
