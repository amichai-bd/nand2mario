# Project charter and release acceptance

The releases below are
required results, not claims of implemented or verified behavior.

## Approved direction

Build an original-DMG-compatible Game Boy for the DE10-Lite. Compatible means
the core follows DMG behavior: CPU, PPU, timer, DMA, interrupts, joypad and the
memory map match pinned DMG references and independent tests. It does not
mean an arbitrary cartridge runs; the [compatibility scope](#compatibility-scope)
states what each release runs. Design and verify
the hardware, build Python software tools that produce loadable programs, and
prove the complete system in simulation before board execution. Provide VGA
output and PC keyboard input over UART. The game goal is
[Springtrail](sw/springtrail/SPEC.md), an original silent platformer with
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

## Compatibility scope

Every release runs our own 32 KiB mapperless ROM on DMG-accurate core
hardware. The table states what is offered; the gap register owns each
deferral's close condition.

| Scope | `v0.5` | `v0.9` | `v1.0` |
|---|---|---|---|
| Cartridge profile | 32 KiB `dmg-direct-v1`, no mapper, no cartridge RAM | Same | Same |
| Program | Our v0.5 program | Our original platformer | Same |
| Core: CPU, PPU, timer, DMA, interrupts, joypad, memory | DMG behavior, independently tested | Same | Same |
| Serial `FF01`-`FF02` | Register access served, no transfer | Same | Same |
| Audio `FF10`-`FF3F` | Register access served, never powered, no synthesis | Same | Same |
| Output | VGA, silent | Same | Same |
| Input | UART keyboard and scripted input | Same | Same |
| Third-party ROM | Not offered | Not offered | Not offered |

The [serial](rtl/serial/MAS_serial.md) and [audio](rtl/audio/MAS_audio.md)
owners are present-but-unimplemented peripherals. They return DMG read values
so the CPU never faults; the audio owner's
[known divergence](rtl/audio/MAS_audio.md#known-divergence) records what a
game observes. Absent synthesis is
[GAP-016](../preflight-gaps.md#gap-016-audio-synthesis-rtl); the physical
output path is [GAP-014](../preflight-gaps.md#gap-014-physical-audio-path).
No mapper exists. A separate 64 KiB MBC1 profile for our own game is an open
gap in [#307](https://github.com/amichai-bd/nand2mario/issues/307); it is not
a release prerequisite.

Third-party ROM support is not offered in any release. A freely licensed
32 KiB mapperless ROM that uses only the implemented peripherals may run, but
no ROM not authored here has been proven to run. The first third-party boot
attempt is tracked in [#377](https://github.com/amichai-bd/nand2mario/issues/377).
Its result adds evidence to the relevant owner contracts; it does not widen
the offered scope. Loading a commercial cartridge is not a goal.

Build a Python assembler/linker, ROM packager, asset tools, and loader through
the shared builder. `v0.5` must use our software build. Use a pinned,
license-reviewed assembler as an independent encoding oracle. A C-like compiler
and rebuilding external game source are outside this delivery. Use the existing
pipeline for the original game; no new general engine or compiler is required.

## Input boundary

Use UART for scripted testing and PC keyboard input; UART is the supported
input path. Route UART and physical controls through one shared input boundary
for the same eight Game Boy buttons and MMIO state; game ROMs need no custom
host MMIO. Keep loading/control separate from input events. Preserve VGA output
and UART source-frame observation.

The [shared input owner](rtl/input/MAS_input.md) implements source selection.
Physical buttons and an ADC joystick are defined in the
[board controls contract](fpga-controls.md). Their RTL exists and is
simulation-verified; connecting and qualifying them is out of scope under the
[remote working scope](#remote-acceptance).
Python observation/play tools follow the [host tool specification](../tools/host-play/SPEC.md).
Existing UART commands
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
| `v0.5` | Two clean builds produce identical original-program bytes; actual full UART load/readback matches. Use the [bounded complementary matrix](dv/v05/SPEC.md#revised-milestone-matrix): real initialization and first image, precise continuous cross-frame retirement/write/pixel checks, timer/DMA proofs, all eight button presses/releases plus a pair, actual image/pixel/progress faults, and declared bounded FPGA endurance with sampled independent frames and reset/hang checks. No exhaustive physical observation claim. |
| `v0.9` | Identify the exact self-built original platformer ROM and independent reference configuration. Named boot checkpoint within 600 frame intervals; then 3,600 intervals of scripted start/movement/action. Every frame and input checkpoint agrees with the reference; no unexplained mismatch, hang, or reset. |
| `v1.0` | After separate board approval and wiring/timing proof: full load/readback, scripted checkpoints and pre-VGA frame hashes match simulation; VGA and keyboard work; 30-minute continuous run without unexpected reset/lost input; repeat reset/load/start three times. Silent output. |

The v0.5 and original v0.9 baselines are qualified separately from physical
release acceptance, whose physical-presence column remains open within the
[remote acceptance](#remote-acceptance) split below.
Functional boot/input/checkpoint requirements are preserved,
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
required frame/input checkpoints.

The user-approved [future milestone selection policy](dv/integration/SPEC.md#milestone-acceptance)
distinguishes the complete original-game baseline from later validation.
After acceptance, that baseline is reusable with explicit qualification rather
than an automatic 3600-interval repeat. Future milestones select deterministic
distinct-transition coverage, focused faults and sampled endurance under that
policy. The v1.0 full load/readback, actual VGA/keyboard operation, continuous
30 minutes and three reset/load/start cycles remain required.

### Remote acceptance

The owner works the board remotely; it is connected and answers over UART, but
no one is at it. The [gap register](../preflight-gaps.md#remote-working-scope)
records the 2026-09-11 decisions: physical controls and trusted CI are out of
scope, with [#156](https://github.com/amichai-bd/nand2mario/issues/156) and
[#32](https://github.com/amichai-bd/nand2mario/issues/32) closed. The `v1.0`
checks above keep their wording; this table states which a remote operator can
prove and which need physical presence.

| `v1.0` check | Proven over UART | Needs physical presence |
|---|---|---|
| Full load and readback | Yes: byte-exact readback of the loaded image | — |
| Scripted checkpoints and pre-VGA frame hashes | Yes: snapshots and frame hashes read over UART match simulation | — |
| Keyboard works | Yes: UART keyboard input drives the shared input owner and JOYP | — |
| VGA works | Frame hashes prove the source frames; the VGA owner is simulation- and fit-verified | Observing the monitor: timing tolerance, tearing, colors |
| 30-minute continuous run, no unexpected reset or lost input | Yes: UART-driven input, periodic snapshots, build ID and core-reset epoch | — |
| Three reset/load/start cycles | Yes with the UART core reset | KEY0 board reset |
| Wiring, voltage and timing proof at the board | — | [Board bring-up](board-bring-up.md): wiring and pins documented, timing by static analysis, supply not measured |

A `v1.0` claim built on the UART column alone must say so. The retained
[endurance fixture](../../src/dv/springtrail/ENDURANCE.md#retained-script) needs
current lives/countdown expectations under [#511](https://github.com/amichai-bd/nand2mario/issues/511)
before qualifying the current continuous-gameplay portion of the UART column.
Two entries in the physical column stay open: observing the monitor, under
[#417](https://github.com/amichai-bd/nand2mario/issues/417), and the KEY0 board
reset, which needs hands at the board and has no issue while the board is
worked remotely. They gate physical claims only, not UART-observable,
simulation or host work.

## Dependencies and authority

The [gap register](../preflight-gaps.md) owns closure evidence and the
[current phase](../agents/bootstrap-plan.md#current-phase) governs work order.
The [original-game build facts](../preflight-gaps.md#gap-011-original-game-image-and-build-facts)
define the original image prerequisite. Original sources remain private for now;
the repository's [provenance rules](../tools/provenance.md) govern external sources.

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
