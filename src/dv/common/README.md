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
