# nand2mario documentation

Start here to explore the Game Boy platform, its original games, and the
engineering workflow. The [project overview](../README.md) introduces the
system; this guide points to the contracts that own the details.

## Choose a path

| I want to… | Start here | Continue with |
|---|---|---|
| Understand the project | [Project charter](src/project-charter.md) | [Current phase and gates](agents/bootstrap-plan.md#current-phase) |
| See it in action | [Animated showcases](showcase/README.md) | Build and tests, a UART board session, a Springtrail playthrough and the lesson terminal sessions, from real output |
| Learn the architecture visually | [Eight illustrated lessons](presentations/README.md) | CPU, memory, clocks, graphics, UART, verification, builds and software |
| Explore the game and artwork | [Springtrail](src/sw/springtrail/SPEC.md) | [8x8 tile composition](src/sw/springtrail/CHARACTER_ART.md) and [core asset gallery](src/sw/springtrail/CORE_ART.md) |
| Build or test something | [Build entry point](tools/n2m/SPEC.md#available-commands) | [Software toolchain](tools/sw/SPEC.md) and [verification tiers](src/dv/integration/SPEC.md#verification-tiers) |
| Find the owning specification | [Ownership map](ownership.md) | Tool PRDs/SPECs, RTL microarchitecture and verification contracts |
| Interpret repository activity | [Statistics report](statistics.html) | [How to read and refresh the snapshot](project-statistics.md) |
| Contribute with an agent | [Agent rules](../AGENTS.md) | [Agent flow](../.agents/skills/agent-flow/SKILL.md) and [worktree lifecycle](../worktrees/README.md) |

## What exists, and what still needs proof

The repository contains the DMG platform, a Python SM83 assembler/linker and
ROM build pipeline, and Springtrail's title, movement, scrolling, interactions
and game flow. See the [game contract](src/sw/springtrail/SPEC.md),
[software toolchain](tools/sw/SPEC.md) and
[build system](tools/n2m/SPEC.md) for their supported boundaries.

Implementation is not the same as release qualification. The
[verification plan](src/dv/springtrail/SPEC.md) separates the original baseline
from later changes; the [charter](src/project-charter.md#release-acceptance)
and [preflight register](preflight-gaps.md) retain physical acceptance and
setup requirements. Approved artwork is a source/review asset, not proof that
every depicted action is integrated or has run on the FPGA.

## Read the sources, not a second copy

The wiki owns behavior and design contracts. `src/` and `tools/` own their
implementations. Presentations explain the contracts through worked examples;
SVG galleries expose editable art sources. The statistics page is a dated
measurement, not a live dashboard or readiness score.

Use the category tabs and file filter to explore. **View source** shows the
published document's original text. Implementation links open the repository;
the documentation site does not mirror product source.

The [wiki build contract](tools/wiki/SPEC.md) describes publication and link
checks. Keep new pages focused and link the existing owner instead of copying
requirements into another overview.
