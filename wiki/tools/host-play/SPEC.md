# Original UART play loop

Issue [#157](https://github.com/amichai-bd/nand2mario/issues/157) owns this bounded scenario. It uses the existing [host Client](../n2m/host/SPEC.md), [input owner](../../src/rtl/input/MAS_input.md) and [immutable snapshot](../../src/rtl/snapshot/MAS_snapshot.md). It adds no hardware register or commercial-game interpretation.

The original ROM draws one solid 8-by-8 background tile at map column8,row8. All other map entries and tile0 are explicitly cleared by CPU instructions while LCD is off. Tile1 has low bytes FF and high bytes00. SCY is0. BGP E4 maps tile color1 to shade1; EC maps it to shade3. SCX0 places the object at (64,64); SCX F8 places it at (72,64). The ROM selects the direction row at JOYP and polls Right/Left. Right chooses F8, Left chooses0, and neither preserves position. A press selects EC; release selects E4. No DMA, timer or interrupt handler is used.

The host identifies and loads the original image with complete readback, explicitly selects UART input authority, and uses WRITE_HOST on INPUT for every complete mask. It locates the object from decoded snapshot pixels before choosing Right when x=64 and Left when x=72. Releases follow each press. The independently fixed observations are:

| Observation | Mask | Object x,y | Shade |
|---|---|---|---|
| Initial | 0 | 64,64 | 1 |
| Right | 1 | 72,64 | 3 |
| Release | 0 | 72,64 | 1 |
| Left | 2 | 64,64 | 3 |
| Release | 0 | 64,64 | 1 |

Every other pixel must be shade0. The decoder requires exactly5760 packed bytes, earliest pixel in bits1:0, and produces a160-by-144 grayscale image. Recognition requires exactly one solid64-pixel object with the stated8-by-8 bounds, not a position inferred from the input count. Game interpretation remains in host software.

Each change occurs while host-paused, followed by RUN, a bounded observation interval, HALT and SNAPSHOT with all READ_FRAME chunks. Initial execution permits200000 dots including map setup and startup blank frame; later changes permit150000 dots, more than two70224-dot frame periods plus the bounded polling loop. The latest completed snapshot must have sequence at least1, the load epoch2, and strictly increasing sequence and dot after the first observation. No second SNAPSHOT occurs during readback. The exact publication remains immutable while bytes are read. Failure or uncertainty stops the loop without automatic retry or recovery.

The host loop takes an existing Client and a bounded run-wait callback, so the same command/image path can support later authorized physical operation. Simulation waits observe only elapsed public dots; they do not signal game position or alter product state. Physical execution still requires the repository hardware checks and is not part of this simulation evidence.

Verification uses the real UART byte transport, CPU/memory, JOYP/IF, PPU, frame bridge and dedicated Intel snapshot stores. Actual wrong snapshot data, missing frame completion, wrong button and missing release updates must fail the host's independent checks. These faults do not alter the expected image. Portable image/metadata/failure tests and current-head review complement the composed checks; #88 and #140 acceptance remain unchanged.

The host-play fixture uses the shared 25 MHz system clock, an eight-system-edge UART bit period (3.125 Mbaud), and a separate 25.2 MHz pixel clock. Its watchdog permits one second of simulation time, preserving the former 25-million-system-edge budget for full ROM load/readback and five snapshot downloads. The original 800000-dot sequence and independent image expectations remain unchanged.

The target obeys the [300-second total simulation cap](../n2m/SPEC.md#test-wall-budget), including setup, compilation, run and checking. The declared frame-wait callback permits 300 seconds but cannot extend the outer deadline; serial-response progress retains 120 seconds and the Client wire timeout remains in simulated time. These host limits do not change the game, pixel or frame-freshness expectations. Existing longer historical runs do not establish feasibility under the new cap. Physical execution has a separately declared duration and sampling plan.
