# DMG tile pixel

Status: implemented isolated unit; not an integrated PPU.

## Contract

`dmg_tile_pixel` converts one background/window row position into a raw color
index and palette shade. [Tile data][tiles] and [BGP][palette] define the DMG
mapping. Pipeline controls below are this unit's interface, not DMG dot timing.

| Port | Direction, width | Meaning |
|---|---|---|
| `clk` | input, 1 | Sole clock; rising edge |
| `reset` | input, 1 | Synchronous active-high reset |
| `enable` | input, 1 | Advance the stage |
| `valid_s0` | input, 1 | Input pixel is meaningful |
| `row_low_s0`, `row_high_s0` | input, 8 each | First and second bytes of one tile row |
| `pixel_x_s0` | input, 3 | Position 0 (left) through 7 (right) |
| `palette_s0` | input, 8 | BGP value for this pixel |
| `valid_s1` | output, 1 | Registered pixel validity |
| `color_index_s1`, `shade_s1` | output, 2 each | Registered raw index and mapped shade |

- **PIXEL:** Bit `7 - pixel_x_s0` of the low byte supplies index bit 0;
  the same bit of the high byte supplies index bit 1.
- **PALETTE:** Index 0, 1, 2, or 3 selects palette bits 1:0, 3:2, 5:4,
  or 7:6 respectively. Shades 0 through 3 mean white, light gray, dark gray,
  and black. Background/window index 0 is opaque.
- **ADVANCE:** On an enabled rising edge without reset, valid input and its
  row, position, and palette produce the corresponding S1 outputs after that
  edge. This is one register of latency, with one pixel per enabled edge;
  there is no additional pending state. Later input changes cannot affect S1.
- **BUBBLE:** An enabled invalid input clears all three outputs to zero.
- **HOLD:** Without reset, a disabled edge holds every output, including valid.
  A held valid level is not a new transfer; consumers must share `enable`.
- **RESET:** Reset clears every output at the rising edge, regardless of enable
  or valid. Outputs are unspecified before the first reset edge. Reset changes
  between edges have no immediate effect.
- **INPUTS:** Reset must be known at each edge. Without reset, enable must be
  known; when enabled, valid must be known. Payload must be known only when
  accepted (`!reset && enable && valid_s0`); otherwise it may contain X/Z.
  All binary payload values are legal. Violating these obligations is outside
  the contract; there is no error port.

## Microarchitecture and boundaries

Two combinational selections feed five flip-flops: index, shade, and valid.
Explicit S0/S1 names preserve the [reference study](../../rtl-reference-style.md)'s
stage alignment. Original RTL uses one `always_ff` block without a macro or
package needed only by this unit. There is no memory, CDC, vendor primitive,
clock generation, or dependency on reference HDL.

This unit does not fetch tiles, access registers, arbitrate VRAM/OAM, resolve
objects, or define LCD/VGA timing. The palette is an input snapshot; when a
future PPU samples BGP is a separate contract. No game assets are included.
See the [bounded phase](../../../agents/bootstrap-plan.md#current-phase).

## Alignment and verification

[RTL](../../../../src/rtl/display/dmg_tile_pixel.sv) implements the named rules.
The [test plan](../../../../src/dv/display/README.md) maps each to independent
checks. The builder's [targets](../../../../src/dv/builder/targets.json) run Icarus;
the [standalone runner](../../../../tools/sim/tile_pixel.py) retains Questa support.
See [unit simulation](../../../tools/sim/SPEC.md).

[tiles]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Tile_Data.md
[palette]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Palettes.md
