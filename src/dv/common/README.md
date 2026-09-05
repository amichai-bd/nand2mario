# Register macro test plan

Contract: [product register convention](../../../wiki/src/rtl-reference-style.md#product-register-convention).
The test owns five registers, independent of the tile pipeline. No Game Boy or
CDC behavior is claimed.

| Requirement | Independent check |
|---|---|
| DFF capture | Eight-bit input pattern changes on every positive edge |
| DFF_RST clearing | One-bit value clears on reset, otherwise captures |
| DFF_RST_VAL | Seventeen-bit value resets to `17'h1abcd` |
| DFF_EN holding | Four-bit register holds across disabled edges, even during reset |
| DFF_RST_EN priority | Thirty-two-bit register resets to `32'h89abcdef` even when disabled |
| Synchronous behavior | Change reset, enable and data at falling edges; check no immediate update |
| Control coverage | All four reset/enable combinations over 64 cycles |
| Checker proof | Corrupt one observed bit at cycle 5; require exact expected/actual diagnostic and nonzero raw exit |

The initial enabled edge establishes state without assuming power-up values.
Stimulus uses fixed asymmetric integer patterns. Expected packed fields update
separately before each rising edge; observation waits for nonblocking assignments.
The seed is retained for reproduction; stimulus is deterministic. The corrupt
target uses seed 1, matching its exact registered diagnostic.

Run both `register-macros` and `register-macros-corrupt` through
`python tools/build.py sim test <target> --sim questa --tag <tag>`. The builder retains commands, raw exit codes,
seed, logs and waves. Tile positive/corrupt targets separately prove integration
against their unchanged exhaustive oracle. FPGA and simulation host tests cover
transitive include cache invalidation, missing/dynamic dependencies and constraints;
host mocks do not prove synthesis or simulation.

## Asynchronous registers and named assertions

`tb_async_assert_macros` owns two eight-bit registers with independently tracked
expected state: active-high reset to A5 and active-low reset to 3C. Reset pulses
and data changes occur between edges; checks prove immediate reset, priority,
no update on reset release, and rising-edge capture. Ten edges cover entry to
hold after a legitimate update, sustained hold, release/resume, and a reset pulse
entirely between sampled edges. An independently driven observed signal probes
the stable helper without deriving its expected behavior from the DUT.

Run `async-assert-macros` for the passing case. The five targets
`async-assert-hold`, `async-assert-direct`, `async-assert-no_reset`,
`async-assert-never`, and `async-assert-known` each corrupt only their named
invariant on the final edge. Require the registered `N2M_ASSERT <name>_check`
instance diagnostic and a nonzero raw Questa exit. An assertion watchdog is
fatal. `assert-synthesis` invokes all helpers with undefined arguments under
`SYNTHESIS`; compilation and its pass signature prove complete removal.
Actual clocking Quartus builds additionally prove synthesis exclusion and retain
all existing named chain setup/hold and asynchronous-clear endpoint checks.

These checks add no CPU coverage. Existing clocking positive and three deliberate
negative targets retain their independent oracle and exact signatures.
