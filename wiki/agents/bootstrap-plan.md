# Pre-RTL bootstrap plan

The [gap register](../preflight-gaps.md) owns gap status and close conditions.

## Current phase

Authorized hardware design, verification, and the Python software stack toward
[the approved charter](../src/project-charter.md), delivered through focused
issues and the shared [builder](../tools/n2m/SPEC.md). Begin with prerequisite
contracts and their executable evidence, then implement each dependent unit.
The root selects assigned work and delegates separate author worktrees.

The [reference study](../src/rtl-reference-style.md) informs style without
authorizing HDL reuse. Existing tile, builder, and doctor results retain their
bounded evidence. All simulation work follows the
[temporary Questa deferral](../preflight-gaps.md#gap-008-verification-baseline);
real portable positive and negative checks remain required.

Design, software, portable simulation, and preparation of FPGA builds may
proceed as their applicable contracts and dependencies are satisfied. Board
bring-up designs and timing/CDC work are now authorized prerequisites.
Programming, UART transmission, and physical tests require separate explicit
authorization and verified device, wiring, and voltage. Outstanding physical
evidence gates board acceptance, not independent simulation or host work.

## Completed infrastructure

| Result | Evidence |
|---|---|
| Agent rules, issue flow, and worktrees | [#34](https://github.com/amichai-bd/nand2mario/issues/34), [agent rules](https://github.com/amichai-bd/nand2mario/blob/main/AGENTS.md), and [agent flow](https://github.com/amichai-bd/nand2mario/blob/main/.agents/skills/agent-flow/SKILL.md) |
| Explicit alignment and concise writing | [#8](https://github.com/amichai-bd/nand2mario/issues/8) and [#9](https://github.com/amichai-bd/nand2mario/issues/9) |
| Focused skills and issue helper | [#10](https://github.com/amichai-bd/nand2mario/issues/10) |
| Pre-RTL directory structure | [#11](https://github.com/amichai-bd/nand2mario/issues/11) and [repository layout](https://github.com/amichai-bd/nand2mario/blob/main/README.md#repository-layout) |
| Required wiki and PR checks | [#12](https://github.com/amichai-bd/nand2mario/issues/12) and [PR #23](https://github.com/amichai-bd/nand2mario/pull/23) |
| Custom HTML wiki, source navigation, README/AGENTS toggle, and presentations | [#40](https://github.com/amichai-bd/nand2mario/issues/40), [#41](https://github.com/amichai-bd/nand2mario/issues/41), and [wiki build contract](../tools/wiki/SPEC.md) |
| Automatic Pages after merge to main | [#13](https://github.com/amichai-bd/nand2mario/issues/13) and [#35](https://github.com/amichai-bd/nand2mario/issues/35) |
| Draft PR, independent review, author merge | [PR #38](https://github.com/amichai-bd/nand2mario/pull/38) and [PR #37](https://github.com/amichai-bd/nand2mario/pull/37) |

The [final audit issue](https://github.com/amichai-bd/nand2mario/issues/36) owns
delivery and cleanup evidence. Skill structure checks do not prove agent
behavior; reviewed PRs demonstrate only their own flow.
These results do not close the product, tool, verification, or hardware gaps below.

Use the [infrastructure acceptance checklist](infrastructure-acceptance.md) to
exercise the existing flow with a fresh author and retain evidence in the PR.

## Future P0 sequence

Complete assigned prerequisites in this dependency order as authorized by the
current phase. Resolve each applicable contract before its dependent behavior;
independent prerequisites may proceed in parallel.

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

Product implementation is authorized, subject to the applicable evidence below.

Start the first functional CPU issue only when:

- its scope follows the approved charter and committed source/reuse policy;
- its clock/reset, interface, verification, and CI prerequisites from issues
  #29 through #32 have evidence for that issue's simulation/build scope;
- every applicable P0 close condition has evidence, except the explicitly
  deferred evidence recorded below; and
- the issue links its approved contracts and verification plan.

The user-approved phase replaces the former requirement that every issue #24
through #32 close before any CPU work. GAP-005 physical bring-up and physical
portions of GAP-006, GAP-010, and GAP-012 remain outstanding board prerequisites;
record their missing evidence and do not count simulation as hardware proof.
Licensed Questa evidence remains outstanding under GAP-008. These scoped
replacements allow portable implementation progress; all other applicable
conditions remain required. The gap register stays open for unmet close
conditions, even when an independent implementation issue can finish.
