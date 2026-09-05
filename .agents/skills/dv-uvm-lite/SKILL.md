---
name: dv-uvm-lite
description: Build or review lightweight SystemVerilog verification for nand2mario. Use for testbenches, assertions, scoreboards, coverage, and regressions; do not use to invent DUT behavior.
---

# DV UVM-lite

Derive checks from the issue and specification. Use the
[ownership map](../../../wiki/ownership.md) to link RTL MAS and tool PRD/SPEC
rules to independent checks, `src/` and `tools/` implementation, and evidence.

1. Write a test plan with normal, edge, reset, error, and ordering cases.
2. Separate stimulus, observation, reference behavior, and checks.
3. Make failures self-checking with expected, actual, cycle, and seed evidence.
4. Use assertions for local invariants and scoreboards for transactions.
5. Prove the harness with a passing DUT and a deliberate failing case.

Fill [the test plan](templates/test-plan.md) before broad regression work. Read
[the scenarios](examples/scenarios.md) for boundaries. Stop when expected
behavior is missing or contradictory.
