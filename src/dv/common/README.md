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
`python tools/build.py sim test <target> --tag <tag>`. The builder retains commands, raw exit codes,
seed, logs and waves. Tile positive/corrupt targets separately prove integration
against their unchanged exhaustive oracle. FPGA and simulation host tests cover
transitive include cache invalidation, missing/dynamic dependencies and constraints;
host mocks do not prove synthesis or simulation.

## Asynchronous registers and named assertions

`tb_async_assert_macros` owns two eight-bit registers with independently tracked
expected state: active-high reset to A5 and active-low reset to 3C. Parallel
initialized forms must start at those same values before any reset or clock
edge, then match the independent expected state at every check. Reset pulses
and data changes occur between edges; checks prove immediate reset, priority,
no update on reset release, and rising-edge capture. Invalid direct, never and
known values are disabled during reset; NO_RST is proved to fail during reset.
Ten edges cover entry to
hold after a legitimate update, sustained hold, release/resume, and a reset pulse
entirely between sampled edges. An independently driven observed signal probes
the stable helper without deriving its expected behavior from the DUT.

Run `async-assert-macros` for the passing case. The four targets
`async-assert-hold`, `async-assert-direct`, `async-assert-no_reset` and
`async-assert-never` each corrupt only their named invariant on the final edge.
Require the registered `N2M_ASSERT <name>_check` instance diagnostic and a
nonzero raw simulator exit. `known_check` is instantiated but has no fault
target: `N2M_ASSERT_KNOWN` is a no-op under `VERILATOR`, because a two-state
simulator cannot witness X. An assertion watchdog is
fatal. `assert-synthesis` invokes all helpers with undefined arguments under
`SYNTHESIS`; compilation and its pass signature prove complete removal.
Actual clocking Quartus builds additionally prove synthesis exclusion and retain
all existing named chain setup/hold and asynchronous-clear endpoint checks.

These checks add no CPU coverage. Existing clocking positive and three deliberate
negative targets retain their independent oracle and exact signatures.

## Intel memory doubles

Contract: [Intel memory primitives](../../../wiki/src/rtl/common/MAS_memory_primitives.md).
`tb_sim_ram_double` proves the `n2m_sim_dual_port_ram` double that
`n2m_intel_ram` selects under `VERILATOR`. Seven wrapper shapes go through the
public wrapper ports only: 8/1, 16/1, 32/4, dual-clock 2/1, and three preloaded
shapes (8/1 from a `.mif` with single and range rows, 1/1 from a `.mif` with
`BIN` data and a comment line, 16/1 from a `$readmemh` file). Two direct cases
instantiate the double for rules the wrapper forbids or masks. Fixture files
are written by the top at time zero from shared image functions.

| Requirement | Independent check |
|---|---|
| Reset masking | `a_valid`/`b_valid` low within 1 ns of reset; a masked write never lands; held data unchanged |
| Power-up contents | Every unpreloaded word is read before any write; more than one distinct value across the array |
| Preload | Every word of each preloaded shape equals the image the top wrote; a row with a non-hex digit is fatal |
| One edge of latency | Output unchanged in the 5 ns before an edge; new word and valid 1 ns after the request edge |
| Read hold | Disabled reads keep their data and drop valid while other words are written |
| Byte lanes | 32/4: single lanes then `0101`/`1010` pairs produce `D0C1D2C3`; single-lane shapes: enable 0 leaves the word |
| Same-port read/write | Full lanes return the new word at that edge; partial lanes trip `INTEL_RAM_SAME_PORT_LANES` |
| Mixed-port, single clock | Direct case: a same-edge B read returns the old word, the next read the new word; through the wrapper the collision trips `INTEL_RAM_MIXED_PORT_A` |
| Mixed-port, dual clock | Direct case: a B read of the word A is writing is unspecified; the next clean read and a different-address read are exact |
| Checker proof | `+corrupt` forces `a_rdata` and requires the exact `SIM_RAM_DATA_A` diagnostic |

Targets: `sim-ram-double` (pass), `sim-ram-double-corrupt`,
`sim-ram-double-collision`, `sim-ram-double-partial-lanes` and
`sim-ram-double-bad-preload`, all `simulator: verilator`. The unspecified
values are drawn from the run's seeded random stream, so a seed reproduces them.

