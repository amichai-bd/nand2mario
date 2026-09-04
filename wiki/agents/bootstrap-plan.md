# Pre-RTL bootstrap plan

Functional Game Boy RTL is blocked until this plan reaches the implementation
gate below. The [gap register](../preflight-gaps.md) remains the source of truth
for each gap's close conditions.

## Completed infrastructure

| Result | Evidence |
|---|---|
| Agent delivery loop and worktree ownership | [#7](https://github.com/amichai-bd/nand2mario/issues/7) |
| Explicit-only `grill-me` alignment | [#8](https://github.com/amichai-bd/nand2mario/issues/8) |
| Concise prose skill | [#9](https://github.com/amichai-bd/nand2mario/issues/9) |
| Focused repository skills and issue tooling | [#10](https://github.com/amichai-bd/nand2mario/issues/10) |
| Pre-RTL directory structure | [#11](https://github.com/amichai-bd/nand2mario/issues/11) |
| Wiki pull-request checks | [#12](https://github.com/amichai-bd/nand2mario/issues/12) |
| Main-only wiki deployment workflow | [#13](https://github.com/amichai-bd/nand2mario/issues/13) |

These results establish the working method. They do not close the product,
tool, verification, or hardware gaps below.

## Remaining P0 work

Complete the work in this order. Create a focused, assigned issue for each
result before work starts.

1. Approve project scope and legal boundaries:
   [GAP-001](../preflight-gaps.md#gap-001-scope-and-success-contract) and
   [GAP-002](../preflight-gaps.md#gap-002-license-rom-policy-and-provenance).
2. Implement and prove the build environment:
   [GAP-003](../preflight-gaps.md#gap-003-build-command) and
   [GAP-004](../preflight-gaps.md#gap-004-real-environment-doctor).
3. Prove board I/O safety and define timing:
   [GAP-005](../preflight-gaps.md#gap-005-board-wiring-and-safe-bring-up) and
   [GAP-006](../preflight-gaps.md#gap-006-clock-reset-and-cdc-plan).
4. Establish executable interfaces and trusted verification:
   [GAP-007](../preflight-gaps.md#gap-007-executable-interface-contracts) and
   [GAP-008](../preflight-gaps.md#gap-008-verification-baseline).
5. Prove the full agent flow and finish repository automation:
   [GAP-009](../preflight-gaps.md#gap-009-initial-agent-skills),
   [GAP-010](../preflight-gaps.md#gap-010-github-remote-issues-ci-and-pages),
   and [#14](https://github.com/amichai-bd/nand2mario/issues/14).

Later integration also depends on
[GAP-011](../preflight-gaps.md#gap-011-cartridge-and-target-rom-facts),
[GAP-012](../preflight-gaps.md#gap-012-vga-frame-crossing), and
[GAP-013](../preflight-gaps.md#gap-013-external-dependencies).
[GAP-014](../preflight-gaps.md#gap-014-physical-audio-path) and
[GAP-015](../preflight-gaps.md#gap-015-native-compiler-scope) remain later
milestones.

## Implementation gate

Start the first functional CPU issue only when:

- every applicable P0 close condition has evidence;
- issue #14 records a ready decision; and
- the first CPU issue links its approved contracts and verification plan.

Before then, only bootstrap work and the minimal board-proving design allowed by
the gap register may add RTL.
