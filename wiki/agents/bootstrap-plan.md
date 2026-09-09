# Project phase and implementation gates

The [gap register](../preflight-gaps.md) owns gap status and close conditions.

## Current phase

Authorized hardware design, verification, and the Python software stack toward
[the approved charter](../src/project-charter.md), delivered through focused
issues and the shared [builder](../tools/n2m/SPEC.md). Begin with prerequisite
contracts and their executable evidence, then implement each dependent unit.
The root selects assigned work and delegates separate author worktrees. The
current [original platformer](../src/sw/springtrail/SPEC.md) implements its
foundation, movement and interaction baseline. Expanded sprite, movement and
gameplay behavior remains planned in the
[SML1 alignment contract](../src/sw/springtrail/sml1-alignment.md), with explicit
open gaps. Game acceptance is separate from the v0.5 hardware baseline; no
commercial cartridge or new mapper is a prerequisite for the mapperless game.

The [reference study](../src/rtl-reference-style.md) informs style without
authorizing HDL reuse. Existing tile, builder, and doctor results retain their
bounded evidence. The [gap register](../preflight-gaps.md) records outstanding
verification and physical proof.

Design, software, simulation, and FPGA work may proceed as their applicable
contracts and dependencies are satisfied. Outstanding physical evidence gates
board acceptance, not independent simulation or host work.

### Verification and hardware authorization

The user authorizes required Questa verification, FPGA programming, UART
transmission, and physical tests within the approved project. This supplies
the separate hardware authorization; do not request it again within this scope.

Before physical execution, verify the expected device identity, wiring, ground
and voltage, a suitable reviewed build with applicable constraints and timing
evidence, and exclusive serialized access. Missing setup facts or access block
the dependent physical work.

Prefer bounded original-game checks on the FPGA through the connected UART
loader, debugger and inputs once the reviewed build and setup checks above pass.
This work has standing user authorization; do not request routine approval
again. Keep affected simulation within the
[test wall budget](../tools/n2m/SPEC.md#test-wall-budget).
Hardware results do not automatically replace the
[simulation acceptance matrix](../src/dv/integration/SPEC.md#milestone-acceptance).

Authorization is not evidence. Simulation must compile, elaborate, run, and check
expected results, including required positive and deliberately failing cases.
Independent review, passing CI, source privacy, and trusted-runner isolation
remain required. Preserve failures and distinguish simulation, Quartus fit/timing,
and physical results; none substitutes for another.

## Current infrastructure

The [agent rules](../../AGENTS.md), [agent flow](../../.agents/skills/agent-flow/SKILL.md)
and [worktree lifecycle](../../worktrees/README.md) govern delivery. The
[wiki builder](../tools/wiki/SPEC.md) renders source navigation and presentations;
the [PR checks](pull-requests.md) and Pages workflow validate and publish it.
Infrastructure checks do not establish product or physical acceptance.

Use the [infrastructure acceptance checklist](infrastructure-acceptance.md) to
exercise the existing flow with a fresh author and retain evidence in the PR.

## Future P0 sequence

Complete assigned prerequisites in this dependency order as authorized by the
current phase. Resolve each applicable contract before its dependent behavior;
independent prerequisites may proceed in parallel.

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
5. Finish trusted product CI and hardware-job isolation:
   [GAP-010](../preflight-gaps.md#gap-010-github-remote-issues-ci-and-pages).

Later integration also depends on
[GAP-011](../preflight-gaps.md#gap-011-original-game-image-and-build-facts),
[GAP-012](../preflight-gaps.md#gap-012-vga-frame-crossing), and
[GAP-013](../preflight-gaps.md#gap-013-external-dependencies).
[GAP-014](../preflight-gaps.md#gap-014-physical-audio-path) and
[GAP-015](../preflight-gaps.md#gap-015-native-compiler-scope) remain later
milestones.

## Implementation gate

Product implementation is authorized, subject to the applicable evidence below.

Start dependent product work only when:

- its scope follows the approved charter and committed source/reuse policy;
- its clock/reset, interface, verification, and CI prerequisites have evidence
  for that work's simulation/build scope;
- every applicable P0 close condition has evidence, except the physical
  evidence scoped below; and
- the issue links its approved contracts and verification plan.

GAP-005 physical bring-up and physical
portions of GAP-006, GAP-010, and GAP-012 remain outstanding board prerequisites;
record their missing evidence and do not count simulation as hardware proof.
The shared Questa baseline is recorded under GAP-008. Later unit evidence is
authorized above. The physical evidence exception allows independent
implementation progress; all other applicable conditions remain required. The
gap register stays open for unmet close conditions, even when an independent
implementation issue can finish.
