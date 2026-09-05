# Documentation ownership

This is the ownership map for implementation and its wiki contracts. Directory
names follow the implementation owner, not a second software hierarchy.

| Implementation owner | Requirements | Design and observable rules | Verification |
|---|---|---|---|
| [tools/n2m](../tools/n2m/cli.py) and its [tools/build.py](../tools/build.py) dispatcher | [PRD](tools/n2m/PRD.md) | [SPEC](tools/n2m/SPEC.md) | [Host tests](../tools/n2m/tests/test_builder.py), [interface generator tests](../tools/n2m/tests/test_interfaces.py), [baseline report tests](../tools/n2m/tests/test_baseline.py), [simulation registry and smoke](../src/dv/builder/targets.json) |
| [tools/wiki](../tools/wiki/site.py) | [PRD](tools/wiki/PRD.md) | [SPEC](tools/wiki/SPEC.md) | [Publication tests](../tools/wiki/test_site.py), [check tests](../tools/wiki/test_check.py), [browser tests](../tools/wiki/browser_tests.py) |
| [tools/sim](../tools/sim/tile_pixel.py) | [PRD](tools/sim/PRD.md) | [SPEC](tools/sim/SPEC.md) | [Runner tests](../tools/sim/test_tile_pixel.py), [tile test plan](../src/dv/display/README.md) |
| [tools/sw](../tools/sw/THIRD_PARTY.md) (planned implementation; provenance exists) | [PRD](tools/sw/PRD.md) | [SPEC](tools/sw/SPEC.md) | Planned conformance owned by [#84–#88](tools/sw/SPEC.md#delivery-order) |
| [src/rtl/common](../src/rtl/common/macros.svh) | [#105](https://github.com/amichai-bd/nand2mario/issues/105) | [Shared register convention](src/rtl-reference-style.md#product-register-convention) | [Directed macro test plan](../src/dv/common/README.md) |
| [src/rtl/display](../src/rtl/display/dmg_tile_pixel.sv) | [Charter](src/project-charter.md) | [MAS_display](src/rtl/display/MAS_display.md) | [Tile test plan](../src/dv/display/README.md) |
| [src/rtl/interfaces](../src/rtl/interfaces/n2m_interfaces_pkg.sv) | [Charter](src/project-charter.md) and [#30](https://github.com/amichai-bd/nand2mario/issues/30) | [MAS_interfaces](src/rtl/interfaces/MAS_interfaces.md), shared with host and verification consumers | [Interface fixture](../src/dv/interfaces/tb_interfaces.sv), [codec tests](../tools/n2m/tests/test_interfaces.py) |
| [cfg/interfaces.json](../cfg/interfaces.json), schema shared across RTL and tools | [Interface requirements](tools/n2m/PRD.md) | [Generated tables](cfg/interfaces.md), [generator rules](tools/n2m/SPEC.md#interface-generation) | [Generator and drift tests](../tools/n2m/tests/test_interfaces.py) |
| [src/dv/baseline](../src/dv/baseline/README.md), test-only fixture and harness | [#31](https://github.com/amichai-bd/nand2mario/issues/31) | [Baseline SPEC](src/dv/baseline/SPEC.md) | [Test plan](../src/dv/baseline/README.md), [regression manifest](../src/dv/baseline/regression.json) |

`tools/scripts/` and `tools/automations/` contain only placement README files;
they own no executable tool or behavior contract yet. `src/rtl/README.md` is an
index; display is the implemented RTL behavior owner in this inventory; interfaces
contains generated representations, with endpoint behavior still planned. Verification
fixtures under `src/dv/` are not product RTL. The issue helper under
`.agents/skills/issue-author/` belongs to the agent method and its linked
[issue contract](agents/issues.md), not a `tools/` implementation.

## Placement and alignment

Each tool owner uses `wiki/tools/<name>/PRD.md` for purpose, scope, and acceptance
links, and `SPEC.md` beside it for interfaces, behavior, design, and verification
rules. An RTL owner uses `wiki/src/rtl/<name>/MAS_<name>.md` for its module
contracts and microarchitecture. Nested implementation owners retain the same
relative hierarchy. Add an entry when an owner is introduced; do not create
speculative tools or move implementation to fit documentation.

Keep requirements and detailed rules in one place and link between them. Shared
contracts, including the [charter](src/project-charter.md),
[clock/reset/CDC design](src/clocks-resets-cdc.md), and
[source policy](tools/provenance.md), remain shared authorities. A generated
table belongs to its schema and generator; do not hand-copy constants into a
PRD, SPEC, or MAS. Mark planned behavior and link its implementation issue.

The wiki may contain Markdown, HTML, and SVG documentation. Source and tests
stay in their implementation directories and are external references under the
[publication contract](tools/wiki/SPEC.md#sources-and-navigation). Do not copy
scripts, RTL, or test sources into the wiki. Apply the
[alignment review](../.agents/skills/agent-flow/references/review.md#code-spec-and-test-alignment)
to requirements, design, implementation, tests, and retained evidence.
