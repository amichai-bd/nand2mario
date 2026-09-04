# nand2mario documentation

This wiki is the version-controlled source for project behavior, architecture,
decisions, verification, and development guidance.

## Current documents

- [Research findings](research-findings.md) records the environment audit,
  reference review, recommended architecture, and delivery sequence.
- [Gaps before implementation](preflight-gaps.md) records unresolved work and
  the evidence required to close it.
- [Pre-RTL bootstrap plan](agents/bootstrap-plan.md) orders the remaining work
  and defines the implementation gate.
- [Build-system specification](tools/build-system.md) defines tagged builds,
  cache behavior, and simulation result paths.
- [Wiki build](tools/wiki.md) defines the local and pull-request check.
- [Issues and labels](agents/issues.md) defines concise issue intake and the
  reusable label model.
- [Branches and pull requests](agents/pull-requests.md) defines issue-backed
  branches, required closure, and the PR policy check.
- [Worktree lifecycle](https://github.com/amichai-bd/nand2mario/blob/main/worktrees/README.md)
  defines isolated agent checkouts.
- [Agent working rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md)
  defines the concise rules used throughout the repository.

## Status

The agent workflow, repository structure, wiki checks, and deployment automation
exist. Product-facing P0 gaps still block functional RTL.

Future pages should remain short. Create one page per subsystem or interface and
use this structure where practical:

1. Purpose
2. Interface
3. Behavior
4. Edge cases
5. Verification
6. References
