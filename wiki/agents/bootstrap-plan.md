# Pre-RTL bootstrap plan

The [gap register](../preflight-gaps.md) owns gap status and close conditions.

## Current phase

Infrastructure refinement and user-authorized reference RTL/display analysis.
Maintain the existing methodology; study frog-bui and FROG_FS before proposing
display microarchitecture or RTL. See the [reference study](../src/rtl-reference-style.md).

Defer final product architecture and all product RTL, DV, SW, and FPGA work. This
includes project build/doctor implementation and simulation, board-proving
designs and tests, and physical runner setup. An assigned issue or a P0 priority
does not authorize this work.

The user must explicitly authorize broader product work before these prerequisites begin.
Gap close conditions and separate programming and physical-test authorization
still apply.

## Completed infrastructure

| Result | Evidence |
|---|---|
| Agent rules, issue flow, and worktrees | [#34](https://github.com/amichai-bd/nand2mario/issues/34), [agent rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md), and [agent flow](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/agent-flow/SKILL.md) |
| Explicit alignment and concise writing | [#8](https://github.com/amichai-bd/nand2mario/issues/8) and [#9](https://github.com/amichai-bd/nand2mario/issues/9) |
| Focused skills and issue helper | [#10](https://github.com/amichai-bd/nand2mario/issues/10) |
| Pre-RTL directory structure | [#11](https://github.com/amichai-bd/nand2mario/issues/11) and [repository layout](https://github.com/amichai-bd/nand2mario/blob/main/README.md#repository-layout) |
| Required wiki and PR checks | [#12](https://github.com/amichai-bd/nand2mario/issues/12) and [PR #23](https://github.com/amichai-bd/nand2mario/pull/23) |
| Custom HTML wiki, source navigation, README/AGENTS toggle, and presentations | [#40](https://github.com/amichai-bd/nand2mario/issues/40), [#41](https://github.com/amichai-bd/nand2mario/issues/41), and [wiki build contract](../tools/wiki.md) |
| Automatic Pages after merge to main | [#13](https://github.com/amichai-bd/nand2mario/issues/13) and [#35](https://github.com/amichai-bd/nand2mario/issues/35) |
| Draft PR, independent review, author merge | [PR #38](https://github.com/amichai-bd/nand2mario/pull/38) and [PR #37](https://github.com/amichai-bd/nand2mario/pull/37) |

The [final audit issue](https://github.com/amichai-bd/nand2mario/issues/36) owns
delivery and cleanup evidence. Skill structure checks do not prove agent
behavior; reviewed PRs demonstrate only their own flow.
These results do not close the product, tool, verification, or hardware gaps below.

Use the [infrastructure acceptance checklist](infrastructure-acceptance.md) to
exercise the existing flow with a fresh author and retain evidence in the PR.

## Future P0 sequence

After an explicit phase change, complete assigned issues in this dependency
order. This plan does not authorize work now.

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

Functional Game Boy RTL is not ready to start; the current phase also blocks
its P0 prerequisites.

Start the first functional CPU issue only when:

- the user has explicitly authorized the product implementation phase;
- every applicable P0 close condition has evidence;
- issues #24 through #32 are closed or the gap register names approved
  replacements; and
- the first CPU issue links its approved contracts and verification plan.

Board-proving RTL belongs to the future prerequisites, not the current phase.
