# Builder requirements

The build system gives agents and people one predictable command to create
tagged workspaces, reuse valid results, and record evidence.

The [SPEC](SPEC.md) owns available commands, environment readiness, bootstrap,
cache rules, and result records. Its status distinguishes implemented commands
from planned software, regression, and cleanup stages. The
[FPGA build contract](SPEC.md#fpga-build) requires checked MAX 10 fit/timing
evidence without physical execution. Acceptance links
command results to the [gap register](../../preflight-gaps.md#gap-003-build-command)
and the [environment doctor criteria](../../preflight-gaps.md#gap-004-real-environment-doctor).
The [ownership map](../../ownership.md) links implementation and tests.

The interface generator gives RTL, host tools, assembly users, and documentation
matching checked exports from one schema. Its acceptance is
[#30](https://github.com/amichai-bd/nand2mario/issues/30) and
[GAP-007](../../preflight-gaps.md#gap-007-executable-interface-contracts).
[Generation rules](SPEC.md#interface-generation) and the
[shared interface contract](../../src/rtl/interfaces/MAS_interfaces.md) own the
details; these requirements do not claim implemented CPU or UART behavior.
