# Builder requirements

The build system gives agents and people one predictable command to create
tagged workspaces, reuse valid results, and record evidence.

The [SPEC](SPEC.md) owns available commands, environment readiness, installation,
cache rules, and result records. Its status distinguishes implemented commands
from unimplemented aggregate regression and cleanup stages. The
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
accept the known-good fixture and detect its known defect through Questa, retaining reproducible failure evidence under the
[baseline contract](../../src/dv/baseline/SPEC.md), without claiming CPU
or hardware coverage from this fixture.

Questa is the sole simulator. The shared builder also supports independent Python
testbenches alongside SV through the [Python adapter](../../../tools/n2m/python_tb.py), using the same
tagged evidence and cache rules. Python failures must fail the command even
when the simulator returns zero. The [testbench contract](SPEC.md#testbench-types)
defines explicit selection and the first joypad proof; it does not replace
existing acceptance or authorize a wider verification migration.
Product memory simulation must use the installed Intel model for the same
explicit wrapper used by MAX 10 synthesis. The [model adapter](../../../tools/n2m/intel_memory.py)
requires checked model selection, retained source hashes and binding, and
failure on a missing, modified or shadow model. A host double cannot establish
primitive behavior. The [shared memory MAS](../../src/rtl/common/MAS_memory_primitives.md)
owns port timing and consumer migration boundaries.
Pre-merge host checks verify host contracts only; the [CI boundary](SPEC.md#ci-execution-boundary)
requires actual local evidence while the trusted licensed route stays out of
scope under [GAP-010](../../preflight-gaps.md#gap-010-github-remote-issues-ci-and-pages).
