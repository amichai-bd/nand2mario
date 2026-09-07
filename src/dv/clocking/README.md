# Clocking test plan

Contract: [clocks, resets and CDC](../../../wiki/src/clocks-resets-cdc.md).
The DUT boundary is portable reset qualification and the DMG timebase. The
independent destination clock exercises reset release; it is not an ALTPLL model.

| Rule | Independent check |
|---|---|
| Exact count and bounded jitter | Cumulative integer division predicts every carry and ceiling division predicts its edge across two complete periods; both legal gap lengths must occur |
| Pause and core reset | Request between dots, acknowledge at completion, hold, resume, and restart count from zero without resetting PLL or pixel domain |
| Configuration startup | Begin with button released and pixel clock stopped; check the complete release qualification interval |
| Lock qualification | Check every qualification edge and both destination release edges |
| Asynchronous assertion | Remove raw lock and assert/bounce the button between edges; observe immediate assertion |
| Stopped destination | No release without destination edges; retained lock does not invent a stopped-clock detector |
| Harness sensitivity | Wrong numerator, dropped first carry, and premature reset release each fail with a specific expected signature |

Run registered `clocking`, `clocking-bad-numerator`, `clocking-drop-tick`, and
`clocking-early-reset` targets through the shared builder with Questa.
The positive target must finish normally; mutations must terminate
nonzero and match their registered reason. A watchdog bounds hangs. Retained
logs and VCD waves include transitions around long qualification/count windows;
checking continues while wave dumping is disabled in their middle.

The `timebase25` target adds an independent absolute-rate oracle using
4,194,304 / 25,000,000 rather than the reduced RTL fraction. It covers both
five/six-edge dot gaps and 23/24-edge M-cycles over two complete periods;
`timebase25-bad-numerator` changes the actual accumulator and must fail.

The separate FPGA proof uses both actual generated vendor PLLs and the timing netlist.
Virtual control/observation pins isolate this fit from board programming and
physical acceptance. Its nominal and upper-reference evidence must meet the
shared clock contract before issue completion.
