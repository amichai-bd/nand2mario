# Documentation ownership

This is the ownership map for implementation and its wiki contracts. Directory
names follow the implementation owner, not a second software hierarchy.

| Implementation owner | Requirements | Design and observable rules | Verification |
|---|---|---|---|
| `src/sw/springtrail` | [Charter](src/project-charter.md) | [Springtrail SPEC](src/sw/springtrail/SPEC.md) | Original ROM/asset builds and independent gameplay checkpoints |
| `src/dv/springtrail` | [Release requirements](src/project-charter.md) | [Game verification SPEC](src/dv/springtrail/SPEC.md) | Frozen independent reference, bounded execution matrix and separate physical endurance |
| `src/sw/v05` and `src/dv/v05` | [Release requirements](src/project-charter.md) | [v0.5 acceptance](src/dv/v05/SPEC.md) | Literal instruction and pixel oracles, continuous run and real loader |
| `src/rtl/system` | [Charter](src/project-charter.md) | [MAS_system](src/rtl/system/MAS_system.md) | Original v0.5 program and composed instruction/pixel acceptance |
| [tools/n2m/host_play.py](../tools/n2m/host_play.py) | [Host requirements](tools/n2m/host/PRD.md) | [Host play SPEC](tools/host-play/SPEC.md) | Original ROM, immutable images and real UART input loop |
| `src/rtl/dma` | [Charter](src/project-charter.md) | [MAS_dma](src/rtl/dma/MAS_dma.md) | FF46 transfer, OAM access/corruption and shared-store service |
| [src/rtl/snapshot](../src/rtl/snapshot/n2m_frame_snapshot.sv) | [Charter](src/project-charter.md) | [MAS_snapshot](src/rtl/snapshot/MAS_snapshot.md) | [Snapshot test plan](../src/dv/snapshot/README.md) |
| [src/rtl/timer](../src/rtl/timer/n2m_timer.sv) | [Charter](src/project-charter.md) | [MAS_timer](src/rtl/timer/MAS_timer.md) | [Timer test plan](../src/dv/timer/README.md) |
| [src/rtl/interrupts](../src/rtl/interrupts/n2m_interrupts.sv) | [Charter](src/project-charter.md) | [MAS_interrupts](src/rtl/interrupts/MAS_interrupts.md) | [Interrupt test plan](../src/dv/interrupts/README.md) |
| [tools/n2m](../tools/n2m/cli.py) and its [tools/build.py](../tools/build.py) dispatcher | [PRD](tools/n2m/PRD.md) | [SPEC](tools/n2m/SPEC.md) | [Host tests](../tools/n2m/tests/test_builder.py), [interface generator tests](../tools/n2m/tests/test_interfaces.py), [baseline report tests](../tools/n2m/tests/test_baseline.py), [simulation registry and smoke](../src/dv/builder/targets.json) |
| [tools/n2m/host](../tools/n2m/host/client.py) | [PRD](tools/n2m/host/PRD.md) | [SPEC](tools/n2m/host/SPEC.md) | [Fake endpoint and CLI tests](../tools/n2m/tests/test_host.py) |
| [tools/ci](../tools/ci/controller.py) and [trusted configuration](../cfg/trusted-ci.json) | [PRD](tools/ci/PRD.md) | [SPEC](tools/ci/SPEC.md) | [Admission, recovery and status host tests](../tools/ci/tests/test_trust.py) |
| [tools/wiki](../tools/wiki/site.py) | [PRD](tools/wiki/PRD.md) | [SPEC](tools/wiki/SPEC.md) | [Publication tests](../tools/wiki/test_site.py), [check tests](../tools/wiki/test_check.py), [browser tests](../tools/wiki/browser_tests.py) |
| [tools/sim](../tools/sim/tile_pixel.py) | [PRD](tools/sim/PRD.md) | [SPEC](tools/sim/SPEC.md) | [Runner tests](../tools/sim/test_tile_pixel.py), [tile test plan](../src/dv/display/README.md) |
| [tools/sw assembler/linker](../tools/sw/linker.py) and [software oracle](../tools/n2m/rgbds.py) | [PRD](tools/sw/PRD.md) | [SPEC](tools/sw/SPEC.md) | [Assembler tests](../tools/n2m/tests/test_assembler.py), [oracle tests](../tools/n2m/tests/test_rgbds.py), [full matrix](../tools/sw/conformance.py), [link/package tests](../tools/n2m/tests/test_linker.py), [RGBDS link proof](../tools/sw/link_conformance.py), [shade converter](../tools/sw/assets.py), [asset checks](../tools/n2m/tests/test_assets.py) |
| [src/rtl/common](../src/rtl/common/macros.svh) | [Charter](src/project-charter.md) | [Shared register convention](src/rtl-reference-style.md#product-register-convention) | [Directed macro test plan](../src/dv/common/README.md) |
| [Intel product memory boundary](../src/rtl/common/n2m_intel_ram.sv) | [Builder requirements](tools/n2m/PRD.md) | [Shared memory MAS](src/rtl/common/MAS_memory_primitives.md) | [Installed-model wrapper fixtures](../src/dv/common/README.md) and MAX 10 inference checks |
| [src/rtl/display](../src/rtl/display/dmg_tile_pixel.sv) | [Charter](src/project-charter.md) | [MAS_display](src/rtl/display/MAS_display.md) | [Tile test plan](../src/dv/display/README.md) |
| [src/rtl/clocking](../src/rtl/clocking/n2m_reset_control.sv) and its [FPGA wrapper](../src/fpga/de10_lite/n2m_clocking.sv) | [Clock/reset contract](src/clocks-resets-cdc.md) | [MAS_clocking](src/rtl/clocking/MAS_clocking.md) | [Clocking test plan](../src/dv/clocking/README.md) |
| [src/rtl/vga](../src/rtl/vga/n2m_frame_bridge.sv) | [Clock/reset/CDC contract](src/clocks-resets-cdc.md) | [MAS_vga](src/rtl/vga/MAS_vga.md) | [Frame bridge test plan](../src/dv/vga/README.md) |
| [src/rtl/input](../src/rtl/input/n2m_input.sv) | [Charter](src/project-charter.md) | [MAS_input](src/rtl/input/MAS_input.md) | [Input verification](../src/dv/input/README.md) |
| [src/rtl/serial](../src/rtl/serial/n2m_serial.sv) | [Charter](src/project-charter.md) | [MAS_serial](src/rtl/serial/MAS_serial.md) | [Serial test plan](../src/dv/serial/README.md) |
| [src/rtl/audio](../src/rtl/audio/n2m_apu.sv) | [Charter](src/project-charter.md) | [MAS_audio](src/rtl/audio/MAS_audio.md) | [Audio and serial service test plan](../src/dv/audio/README.md) |
| [src/rtl/joypad](../src/rtl/joypad/n2m_joypad_matrix.sv) | [Charter](src/project-charter.md) | [MAS_joypad](src/rtl/joypad/MAS_joypad.md), [sources](src/rtl/joypad/references.md) | [JOYP test plan](../src/dv/joypad/README.md) |
| [src/rtl/cpu](../src/rtl/cpu/n2m_cpu.sv) | [Charter](src/project-charter.md) | [MAS_cpu](src/rtl/cpu/MAS_cpu.md), [source boundaries](src/rtl/cpu/references.md) | [CPU test plan](../src/dv/cpu/README.md) |
| [src/rtl/ppu](../src/rtl/ppu/README.md) | [Charter](src/project-charter.md) | [MAS_ppu](src/rtl/ppu/MAS_ppu.md) | [PPU test plan](../src/dv/ppu/README.md) |
| [src/rtl/interfaces](../src/rtl/interfaces/n2m_interfaces_pkg.sv) | [Charter](src/project-charter.md) | [MAS_interfaces](src/rtl/interfaces/MAS_interfaces.md), shared with host and verification consumers | [Interface fixture](../src/dv/interfaces/tb_interfaces.sv), [codec tests](../tools/n2m/tests/test_interfaces.py) |
| [src/rtl/uart](../src/rtl/uart/n2m_uart_packet_store.sv) | [Charter](src/project-charter.md) | [MAS_uart](src/rtl/uart/MAS_uart.md) | [UART test plan](../src/dv/uart/README.md) |
| [src/rtl/memory](../src/rtl/memory/n2m_memory_stores.sv) | [Charter](src/project-charter.md) | [MAS_memory](src/rtl/memory/MAS_memory.md) | [Intel storage/routing verification](src/rtl/memory/MAS_memory.md#shared-primitive-and-verification) |
| [cfg/interfaces.json](../cfg/interfaces.json), schema shared across RTL and tools | [Interface requirements](tools/n2m/PRD.md) | [Generated tables](cfg/interfaces.md), [generator rules](tools/n2m/SPEC.md#interface-generation) | [Generator and drift tests](../tools/n2m/tests/test_interfaces.py) |
| [src/dv/baseline](../src/dv/baseline/README.md), test-only fixture and harness | [Builder requirements](tools/n2m/PRD.md) | [Baseline SPEC](src/dv/baseline/SPEC.md) | [Test plan](../src/dv/baseline/README.md), [regression manifest](../src/dv/baseline/regression.json) |

`tools/scripts/` and `tools/automations/` contain only placement README files;
they own no executable tool or behavior contract yet. `src/rtl/README.md` is an
index; each implemented RTL owner has its own contract. Interfaces
contains generated representations consumed by the endpoint and host. Verification
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
PRD, SPEC, or MAS. Describe current source; mark each planned implementation or
verification gap explicitly and link only its open issue. Remove completed issue
and PR history from contracts. External technical citations and the statistics
page's delivery measurements are the stated exceptions in [AGENTS](../AGENTS.md).

The wiki may contain Markdown, HTML, and SVG documentation. Source and tests
stay in their implementation directories and are external references under the
[publication contract](tools/wiki/SPEC.md#sources-and-navigation). Do not copy
scripts, RTL, or test sources into the wiki. Apply the
[alignment review](../.agents/skills/agent-flow/references/review.md#code-spec-and-test-alignment)
to requirements, design, implementation, tests, and retained evidence.
