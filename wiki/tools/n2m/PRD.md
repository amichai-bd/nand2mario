# Builder requirements

The build system gives agents and people one predictable command to create
tagged workspaces, reuse valid results, and record evidence.

The [SPEC](SPEC.md) owns available commands, environment readiness, bootstrap,
cache rules, and result records. Its status distinguishes implemented commands
from planned software, FPGA, regression, and cleanup stages. Acceptance links
command results to the [gap register](../../preflight-gaps.md#gap-003-build-command)
and the [environment doctor criteria](../../preflight-gaps.md#gap-004-real-environment-doctor).
The [ownership map](../../ownership.md) links implementation and tests.
