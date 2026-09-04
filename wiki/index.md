# nand2mario documentation

This wiki is the version-controlled source for project behavior, architecture,
decisions, verification, and development guidance.

## Current documents

- [Research findings](research-findings.md) records the environment audit,
  reference review, recommended architecture, and delivery sequence.
- [Gaps before implementation](preflight-gaps.md) records unresolved work and
  the evidence required to close it.
- [Build-system specification](tools/build-system.md) defines tagged builds,
  cache behavior, and simulation result paths.
- [Issues and labels](agents/issues.md) defines concise issue intake and the
  reusable label model.
- [Branches and pull requests](agents/pull-requests.md) defines issue-backed
  branches, required closure, and the PR policy check.
- [Agent working rules](../AGENTS.md) defines the concise rules used throughout
  the repository.

## Status

The project is at the end of research and before repository bootstrap. There is
no functional RTL, simulation environment, FPGA project, host CLI, or deployed
website yet.

Future pages should remain short. Create one page per subsystem or interface and
use this structure where practical:

1. Purpose
2. Interface
3. Behavior
4. Edge cases
5. Verification
6. References
