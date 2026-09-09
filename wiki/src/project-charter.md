# Project charter and release acceptance

Status: scope and acceptance approved in
[#24](https://github.com/amichai-bd/nand2mario/issues/24), with the user-authorized
original-game scope revision in [#259](https://github.com/amichai-bd/nand2mario/issues/259).
The releases below are
required results, not claims of implemented or verified behavior.

## Approved direction

Build an original-DMG-compatible Game Boy for the DE10-Lite. Design and verify
the hardware, build Python software tools that produce loadable programs, and
prove the complete system in simulation before board execution. Provide VGA
output and PC keyboard input over UART. The game goal is
[Springtrail](sw/springtrail/SPEC.md), a planned original silent platformer with
one scrolling level, run/jump movement and original characters, art and code.
Its next release follows the [staged SML1 alignment contract](sw/springtrail/sml1-alignment.md),
which owns the first aligned release, dependent measurements and separate banking
qualification. Alignment preserves original implementation and excludes audio;
the delivered 32 KiB baseline and physical release gates below remain qualified
separately.
Build our own SM83 ROM; do not obtain, copy or reproduce a commercial cartridge.

Use the repository's issue, specification, implementation, verification, and
review flow. Keep software and hardware aligned through shared interface
contracts and the [build entry point](../tools/n2m/SPEC.md).

The [reference study](rtl-reference-style.md) guides RTL style and verification.
Reference process and UART/input ideas do not select the Game Boy architecture
or permit copying code with unresolved reuse rights.

## Model and feature boundaries

Target the original DMG family. Pin Pan Docs and independent DMG tests or traces
before using them to define a subsystem contract. Resolve undocumented or
revision-dependent behavior explicitly before affected RTL. Do not claim exact
silicon identity or universal compatibility.

The completed self-authored v0.5 program remains a qualified hardware baseline.
For `v0.9`, build the original platformer in the existing 32 KiB mapperless
`dmg-direct-v1` profile, with no cartridge RAM. No MBC or commercial-ROM identity
is a prerequisite. Keep gameplay in software and fix hardware only for actual
compatibility defects in its owning contract. Defer additional mappers,
CGB, SGB, and link support. Full APU completion and physical audio are deferred;
these releases prove silent video and input, not full DMG compatibility.

Build a Python assembler/linker, ROM packager, asset tools, and loader through
the shared builder. `v0.5` must use our software build. Use a pinned,
license-reviewed assembler as an independent encoding oracle. A C-like compiler
and rebuilding external game source are outside this delivery. Use the existing
pipeline for the original game; no new general engine or compiler is required.

## Input boundary

Use UART for scripted testing and PC keyboard input. Physical buttons and an
ADC joystick are planned controls. Route UART and physical controls through one
shared input boundary for the same eight Game Boy buttons and MMIO state;
game ROMs need no custom host MMIO. Keep loading/control separate from input
events. Preserve VGA output and UART source-frame observation.

The [shared input owner](rtl/input/MAS_input.md) implements source selection.
Physical buttons and ADC joystick are defined in the
[board controls contract](fpga-controls.md) for
[#156](https://github.com/amichai-bd/nand2mario/issues/156), and
Python observation/play tools in
[#157](https://github.com/amichai-bd/nand2mario/issues/157). These references do
not claim implemented or physically verified controls. Existing UART commands
follow the [shared interface contract](rtl/interfaces/MAS_interfaces.md).
The pinned `frog-bui` [UART][uart] and [shared input][keyboard] sources inform
this separation without granting reuse.

## Release acceptance

Use simulated frame intervals from the approved timing contract, with an
independent cycle watchdog. Host wall-clock speed is not a compatibility test.
Fix reference checkpoints before judging DUT results. If ROM behavior makes a
bound unsuitable, obtain an explicit acceptance revision rather than tune the
bound to pass the implementation.

| Release | Required checks |
|---|---|
| `v0.5` | Two clean builds produce identical original-program bytes; actual full UART load/readback matches. Use the [bounded complementary matrix](dv/v05/SPEC.md#revised-milestone-matrix): real initialization and first image, precise continuous cross-frame retirement/write/pixel checks, timer/DMA proofs, all eight button presses/releases plus a pair, actual image/pixel/progress faults, and declared bounded FPGA endurance with sampled independent frames and reset/hang checks. #88 tracks acceptance; no 600-continuous-interval or exhaustive physical observation claim. |
| `v0.9` | Identify the exact self-built original platformer ROM and independent reference configuration. Named boot checkpoint within 600 frame intervals; then 3,600 intervals of scripted start/movement/action. Every frame and input checkpoint agrees with the reference; no unexplained mismatch, hang, or reset. |
| `v1.0` | After separate board approval and wiring/timing proof: full load/readback, scripted checkpoints and pre-VGA frame hashes match simulation; VGA and keyboard work; 30-minute continuous run without unexpected reset/lost input; repeat reset/load/start three times. Silent output. |

The v0.5 matrix replaces its former 600-continuous-interval criterion by explicit
authorization; that former criterion was not passed. Later releases remain
unqualified. Their functional boot/input/checkpoint requirements are preserved,
but their execution matrices must be named and reviewed before work: use short
complementary simulations under the [total wall cap](../tools/n2m/SPEC.md#test-wall-budget)
and separately declared bounded physical endurance. The v0.9 emulated frame
quantities and v1.0 physical duration are not simulation wall-time allowances.
For v0.9 only, the user approved [paused full-frame acquisition](dv/springtrail/SPEC.md#v09-milestone):
every pixel of all3600 intervals and all inputs remain required in one emulation
history, without reload/reset/replay between bounded host batches. The v1.0
continuous30-minute requirement is unchanged.
The [original-game verification plan](dv/springtrail/SPEC.md) and its milestone
issues retain these obligations. A complete measured execution matrix must be
reviewed before milestone runs; selected snapshots cannot silently replace the
required frame/input checkpoints. Springtrail and these later releases remain
planned, not delivered by the scope revision.

The user-approved [future milestone selection policy](dv/integration/SPEC.md#milestone-acceptance)
distinguishes the unchanged #263 complete baseline from later validation.
After acceptance, that baseline is reusable with explicit qualification rather
than an automatic 3600-interval repeat. Future milestones select deterministic
distinct-transition coverage, focused faults and sampled endurance under that
policy. The v1.0 full load/readback, actual VGA/keyboard operation, continuous
30 minutes and three reset/load/start cycles remain required.

## Dependencies and authority

The [gap register](../preflight-gaps.md) owns closure evidence and the
[current phase](../agents/bootstrap-plan.md#current-phase) governs work order.
The [original-game build facts](../preflight-gaps.md#gap-011-original-game-image-and-build-facts)
replace the former commercial-ROM/mapper prerequisite. Original sources remain private for now; source, ROM, and
reuse policy delivery belongs to
[#25](https://github.com/amichai-bd/nand2mario/issues/25).

Agents own focused issue boundaries, module organization, test seeds/artifacts,
and detailed ABI, reset/load, protocol, clock/CDC, and input contracts within
approved behavior. Escalate changes to scope, acceptance, or safety boundaries.
The [current authorization](../agents/bootstrap-plan.md#verification-and-hardware-authorization)
owns permission and prerequisites for Questa and physical execution, including
the board approval required above. Simulation cannot satisfy physical acceptance.
Shared Questa baseline evidence is recorded in
[GAP-008](../preflight-gaps.md#gap-008-verification-baseline).

[uart]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/uart_ctrl/README.md
[keyboard]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/sw/include/frog/keyboard_input.h
