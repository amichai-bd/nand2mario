---
name: dv-python
description: Build independent Python hardware testbenches with cocotb, starting with small contract-based proofs of concept. Use for Python RTL stimulus, monitors, reference models, and checks; not SystemVerilog testbench maintenance or DUT implementation.
---

# Python hardware verification

Follow [agent flow](../agent-flow/SKILL.md) for delivery and the
[builder contract](../../../wiki/tools/n2m/SPEC.md#testbench-types) for execution.
Use the [Python test entry point](../../../src/dv/python/README.md); keep
test-specific obligations in the owner test plan, as in the
[joypad plan](../../../src/dv/python/joypad/README.md).

Use Python as the testbench and the HDL simulator as the execution engine.
Start from the DUT's public interface and approved behavior contract. Keep this
environment separate from existing HDL verification: do not translate, import,
or use its drivers, monitors, scoreboard, stimulus vectors, or verdict as an
oracle. Sharing the unchanged DUT and specification is appropriate. Inspect an
older testbench only after establishing independent expectations, when comparison
is explicitly part of the task.

Select checks using the [verification tiers](../../../wiki/src/dv/integration/SPEC.md#verification-tiers).
Target 120 seconds per simulation and 300 seconds ordinary pre-merge aggregate;
obey the linked total wall cap and declare broader milestone aggregates. Use
only the explicitly authorized named exceptions in that contract; no other
target inherits a milestone allowance. Complete independent budget-change review
before a longer run, then run positive before its intended failure cases. Use
the owning complementary matrix for bounded execution and separate transport/
physical endurance evidence; never relabel historical longer runs as new-budget PASS.
Use the accepted continuous Python path for composed execution and shared Intel
preload for functional iteration; retain focused SV unit tests. Reuse existing
builders, validators and targets. Exercise final pause, completion and watchdog
handling in a short complete-harness run before expensive acceptance. Select
faults for affected behavior and stop at the shortest meaningful witness; reuse
valid unchanged negative evidence. Keep historical Tcl investigation off unrelated
delivery paths unless a concrete requirement depends on it.

## Small first experiment

Choose the smallest contract with observable success and failure. State what
the experiment proves and what remains outside its scope. Keep the initial
testbench in one Python module and execution setup in a separate small runner.
Use ordinary functions, explicit data, a local seeded random generator, and
plain assertions. Add classes, queues, background tasks, or pyuvm only when the
protocol's concurrency or reuse warrants them. Do not reproduce UVM phases or
component hierarchies by default.

Use one decorated test entry point per target module and share undecorated
helpers. The [builder's test identity](../../../wiki/tools/n2m/SPEC.md#testbench-types)
is checked after execution; it does not filter cocotb scheduling.

Keep three responsibilities easy to inspect, without requiring three frameworks:

- Drive public inputs at defined safe times.
- Observe applied inputs and outputs at the contract's sampling boundary.
- Predict from independent input history and compare with observed outputs.

Use a pure reference function when state permits. Never update expected state
from DUT outputs or internal next-state signals. Anchor calculations with small
literal examples. Start with directed reset, normal, hold, and boundary cases;
add bounded deterministic random stimulus only where useful.

## Simulation timing and evidence

Python awaits must use simulation triggers, not wall-clock sleeps. Separate
driving from sampling to avoid races with HDL nonblocking assignments. Respect
an explicit contract sampling delay; otherwise sample settled outputs with an
appropriate cocotb phase such as ReadOnly after a clock edge. Advance to a
writable phase before the next drive. Reject unknown values when known values
are required; do not coerce X/Z into integers silently.

Bound tests in simulation time and bound simulator execution in wall time.
Track background task failures and completion when concurrency is introduced.
Record cycle/time, seed, applied input, expected and actual before asserting.
Simulator-generated waves expose HDL signals; retain Python transactions
separately so expected values can be correlated with those waves.

Prove both a correct run and a deliberate DUT-side defect with the unchanged
checker. Distinguish compile/elaboration failures, simulator failures, and
functional mismatches. Check the result XML as well as process status: a zero
simulator exit alone may conceal a failed Python test. A negative proof requires
the exact expected mismatch and a failing test-command exit; preserve the raw
simulator exit independently and report any difference. Follow stricter project
acceptance requirements before promoting an experiment into required evidence.

Pin Python dependencies and record interpreter/simulator versions and provenance.
Use an isolated environment and output directory. Respect the project's licensed
runtime serialization and hardware boundaries. A POC is not an automatic
migration, replacement of existing acceptance tests, or RTL bug diagnosis.

Consult documentation matching the pinned cocotb version for timing and
simulator options: https://docs.cocotb.org/en/v2.0.1/ .
