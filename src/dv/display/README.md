# Tile pixel verification

Contract: [DMG tile pixel](../../../wiki/src/display/tile-pixel.md).
DUT boundary: public ports of `dmg_tile_pixel`, one clock, no memory or board.

| Contract rule | Stimulus and independent check |
|---|---|
| PIXEL | All 65,536 byte pairs at all eight positions (524,288 cases); arithmetic division/modulo oracle, asymmetric walking bits, published row example |
| PALETTE | All 256 palettes × four indices × eight positions (8,192 cases); base-four arithmetic oracle; palette changes each transaction |
| ADVANCE | Compare after every rising edge and before the next; back-to-back distinct payloads detect extra latency and combinational leakage |
| BUBBLE, HOLD, RESET | All eight reset/enable/valid combinations from populated state; unknown unused payload, repeated holds, midstream reset, reset while disabled, recovery and drain |
| INPUTS | Known accepted payload; X/Z only where the contract permits it; all legal binary payload combinations covered |
| Checker integrity | `+corrupt` flips one observed output bit at cycle 5; the same assertion must report the expected cycle and a nonzero simulator exit |

The testbench separates stimulus (`step`), arithmetic reference functions, and
output assertions (`check_output`). It reads no DUT hierarchy. No randomized
stimulus or seed is used. Coverage counts are asserted by the required
PASS marker; this is exhaustive functional coverage of the independent pixel
and palette transformations, not their full Cartesian product.

Both builder targets must pass: `tile-pixel` proves normal behavior;
`tile-pixel-corrupt` proves the exact expected checker failure. Builder contract
tests reject unrelated failures and prevent the normal target accepting the
corrupt signature. The Questa runner still checks both cases locally.

Logs include expected/actual, cycle, phase, and input payload on failure. A
6 ms simulated-time watchdog prevents hangs. VCD records directed controls
and the final drain; exhaustive loops pause dumping. The deliberate failure
retains its own trace. Commands and result files remain under the build tag.
See [running the unit](../../../wiki/tools/tile-pixel-sim.md).
