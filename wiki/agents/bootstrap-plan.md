# Pre-RTL bootstrap plan

Functional Game Boy RTL is blocked until this plan reaches the implementation
gate below. The [gap register](../preflight-gaps.md) owns gap status and close
conditions.

## Completed infrastructure

| Result | Evidence |
|---|---|
| Agent rules, issue flow, and worktrees | [#7](https://github.com/amichai-bd/nand2mario/issues/7), [agent rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md), and [worktree lifecycle](https://github.com/amichai-bd/nand2mario/blob/main/worktrees/README.md) |
| Explicit alignment and concise writing | [#8](https://github.com/amichai-bd/nand2mario/issues/8) and [#9](https://github.com/amichai-bd/nand2mario/issues/9) |
| Focused skills and issue helper | [#10](https://github.com/amichai-bd/nand2mario/issues/10) |
| Pre-RTL directory structure | [#11](https://github.com/amichai-bd/nand2mario/issues/11) and [repository layout](https://github.com/amichai-bd/nand2mario/blob/main/README.md#repository-layout) |
| Required wiki and PR checks | [#12](https://github.com/amichai-bd/nand2mario/issues/12) and [PR #23](https://github.com/amichai-bd/nand2mario/pull/23) |
| Main-only Pages deployment | [#13](https://github.com/amichai-bd/nand2mario/issues/13) and [successful main run](https://github.com/amichai-bd/nand2mario/actions/runs/33899199181) |
| Wiki-only steady-state flow | [#22](https://github.com/amichai-bd/nand2mario/issues/22), reviewed SHA `a54e41a`, merge `55ba933`, and [#14](https://github.com/amichai-bd/nand2mario/issues/14) |

These results establish the working method. They do not close the product,
tool, verification, or hardware gaps below.

## Remaining P0 work

Complete the assigned issues in this order.

1. Approve project scope and legal boundaries:
   [GAP-001](../preflight-gaps.md#gap-001-scope-and-success-contract)
   ([#24](https://github.com/amichai-bd/nand2mario/issues/24)) and
   [GAP-002](../preflight-gaps.md#gap-002-license-rom-policy-and-provenance)
   ([#25](https://github.com/amichai-bd/nand2mario/issues/25)).
2. Implement and prove the build environment:
   [GAP-003](../preflight-gaps.md#gap-003-build-command)
   ([#26](https://github.com/amichai-bd/nand2mario/issues/26)) and
   [GAP-004](../preflight-gaps.md#gap-004-real-environment-doctor)
   ([#27](https://github.com/amichai-bd/nand2mario/issues/27)).
3. Prove board I/O safety and define timing:
   [GAP-005](../preflight-gaps.md#gap-005-board-wiring-and-safe-bring-up)
   ([#28](https://github.com/amichai-bd/nand2mario/issues/28)) and
   [GAP-006](../preflight-gaps.md#gap-006-clock-reset-and-cdc-plan)
   ([#29](https://github.com/amichai-bd/nand2mario/issues/29)).
4. Establish executable interfaces and trusted verification:
   [GAP-007](../preflight-gaps.md#gap-007-executable-interface-contracts)
   ([#30](https://github.com/amichai-bd/nand2mario/issues/30)) and
   [GAP-008](../preflight-gaps.md#gap-008-verification-baseline)
   ([#31](https://github.com/amichai-bd/nand2mario/issues/31)).
5. Finish trusted product CI and hardware-job isolation:
   [GAP-010](../preflight-gaps.md#gap-010-github-remote-issues-ci-and-pages)
   ([#32](https://github.com/amichai-bd/nand2mario/issues/32)).

Later integration also depends on
[GAP-011](../preflight-gaps.md#gap-011-cartridge-and-target-rom-facts),
[GAP-012](../preflight-gaps.md#gap-012-vga-frame-crossing), and
[GAP-013](../preflight-gaps.md#gap-013-external-dependencies).
[GAP-014](../preflight-gaps.md#gap-014-physical-audio-path) and
[GAP-015](../preflight-gaps.md#gap-015-native-compiler-scope) remain later
milestones.

## Implementation gate

Decision: the agent environment is ready for controlled P0 prerequisite work.
The repository is not ready for functional Game Boy RTL.

Start the first functional CPU issue only when:

- every applicable P0 close condition has evidence;
- issues #24 through #32 are closed or the gap register names approved
  replacements; and
- the first CPU issue links its approved contracts and verification plan.

Before then, only bootstrap work and the minimal board-proving design allowed by
the gap register may add RTL.
