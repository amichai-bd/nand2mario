# Builder requirements

The build system gives agents and people one predictable command to create
tagged workspaces, reuse valid results, and record evidence.

Every runnable test is indexed once, so a selection can be asked for by the
confidence it buys rather than by name, and a test cannot exist without a gate.
The [test catalogue](SPEC.md#test-catalogue) owns that index: a test present in
the tree but absent from it fails the build, and a selection matching nothing
fails rather than passing quietly.

The [SPEC](SPEC.md) owns available commands, environment readiness, installation,
cache rules, the [test catalogue](SPEC.md#test-catalogue),
[declared regression subsets](SPEC.md#regression-subsets),
[tagged cleanup](SPEC.md#cleanup) and result records. The
[FPGA build contract](SPEC.md#fpga-build) requires checked MAX 10 fit/timing
evidence without physical execution. Acceptance links
command results to the [gap register](../../preflight-gaps.md#gap-003-build-command)
and the [environment doctor criteria](../../preflight-gaps.md#gap-004-real-environment-doctor).
The [ownership map](../../ownership.md) links implementation and tests.

The interface generator gives RTL, host tools, assembly users, and documentation
matching checked exports from one schema. The [generator](../../../tools/n2m/interfaces.py)
and [interface tests](../../../tools/n2m/tests/test_interfaces.py) implement and check that boundary.
[Generation rules](SPEC.md#interface-generation) and the
[shared interface contract](../../src/rtl/interfaces/MAS_interfaces.md) own the
details; generator checks do not establish CPU or UART behavior.

The [verification baseline runner](SPEC.md#verification-baseline-runner) must
accept the known-good fixture and detect its known defect through the
simulator, retaining reproducible failure evidence under the
[baseline contract](../../src/dv/baseline/SPEC.md), without claiming CPU
or hardware coverage from this fixture.

Verilator on WSL is the sole simulator; the licensed Questa seat has left the
flow and no command may depend on a license. The
[simulator policy](SPEC.md#simulator-policy) owns the rules: one build tool
with per-OS command ownership (simulation and `doctor` on WSL, FPGA build and
programming on Windows), behavioral doubles for Intel primitives keyed on the
predefined `VERILATOR` macro, per-area migration in which an unmigrated target
reports `SKIPPED` with reason `questa-retired`, and the authorized removal of
four-state assertions in favor of randomized initial values. The
[doctor](SPEC.md#environment-doctor) already proves a checked Verilator smoke
without a license; the `sim test`, `regress` and `tests run` Verilator path is
the open gap in [#597](https://github.com/amichai-bd/nand2mario/issues/597).
The shared builder also supports independent Python
testbenches alongside SV through the [Python adapter](../../../tools/n2m/python_tb.py), using the same
tagged evidence and cache rules. Python failures must fail the command even
when the simulator returns zero. The [testbench contract](SPEC.md#testbench-types)
defines explicit selection and the first joypad proof; it does not replace
existing acceptance or authorize a wider verification migration.
Product memory simulation under Verilator uses the repository's behavioral
double of the Intel primitive for the same explicit wrapper used by MAX 10
synthesis; Quartus always sees the vendor instance. The
[shared memory MAS](../../src/rtl/common/MAS_memory_primitives.md) owns the
double's contract, port timing and consumer migration boundaries. While
unmigrated targets still run on Questa, the [model adapter](../../../tools/n2m/intel_memory.py)
keeps requiring checked model selection, retained source hashes and binding, and
failure on a missing, modified or shadow model.
Pre-merge host checks verify host contracts only; the [CI boundary](SPEC.md#ci-execution-boundary)
requires actual local evidence while the trusted remote route stays out of
scope under [GAP-010](../../preflight-gaps.md#gap-010-github-remote-issues-ci-and-pages).
