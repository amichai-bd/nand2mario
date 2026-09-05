---
name: dv-uvm-lite
description: Build or review lightweight SystemVerilog verification for nand2mario. Use for testbenches, assertions, scoreboards, coverage, and regressions; do not use to invent DUT behavior.
---

# DV UVM-lite

Derive checks from the issue and specification. Use the
[ownership map](../../../wiki/ownership.md) to link RTL MAS and tool PRD/SPEC
rules to independent checks, `src/` and `tools/` implementation, and evidence.

Follow the [separate declaration and assignment rule](../../../wiki/src/rtl-reference-style.md#separate-declarations-and-assignments),
including loop variables and time-zero stimulus ordering.

1. Write a test plan with normal, edge, reset, error, and ordering cases.
2. Separate stimulus, passive public-boundary observation, reference behavior,
   and checks. Calculate expected values from the contract and observed inputs,
   not DUT decoded fields or internal next-state logic.
3. Compare valid/ready timing and every meaningful typed field, rejecting
   unknowns where the contract requires known values. Report expected, actual,
   cycle, seed and counts; cover backpressure, reset, error recovery and ordering.
4. Use the [shared named assertion macros](../../../wiki/src/rtl-reference-style.md#named-assertion-convention)
   for local sampled invariants and independent scoreboards for transactions.
   Retain detailed procedural expected/actual mismatch reports. Review each
   macro's name, argument order, fatal hierarchy diagnostic and synthesis guard.
   Prove deliberate violations and reset pulses between sampled clocks. Align
   sampled assertions to the correct prior edge and guard reset/history validity.
   Separate unit checks from composed paths with delayed responses.
5. Prove the harness with a passing DUT and a deliberate failing case in Questa.
   Use Questa only for new simulation evidence; do not start Icarus runs.
   Coordinate the licensed runtime slot with root and serialize all applicable
   builder, doctor, standalone and regression children. Release it after exit;
   preserve contention failures and retry only after competing execution ends.
   Watchdogs and mismatches must produce nonzero raw exits; require the exact
   intended failure diagnostic as well. A printed failure followed by `$finish`
   is not sufficient. Retain commands, raw exits, seeds, logs and waves.

Use the [pinned frog-bui observations](references/frog-bui.md) as method examples,
not a behavior oracle or permission to copy unlicensed source. Product register
macros do not require rewriting independent testbench stimulus or reference code.

Fill [the test plan](templates/test-plan.md) before broad regression work. Read
[the scenarios](examples/scenarios.md) for boundaries. Stop when expected
behavior is missing or contradictory.

The [CI boundary](../../../wiki/tools/n2m/SPEC.md#ci-execution-boundary) distinguishes
hosted host checks from required actual local Questa evidence until #32.
