# Project charter and release acceptance

Status: scope and acceptance approved in
[#24](https://github.com/amichai-bd/nand2mario/issues/24). The releases below are
required results, not claims of implemented or verified behavior.

## Approved direction

Build an original-DMG-compatible Game Boy for the DE10-Lite. Design and verify
the hardware, build Python software tools that produce loadable programs, and
prove the complete system in simulation before board execution. Provide VGA
output and PC keyboard input over UART.

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

Start with a self-authored fixed-ROM program. For `v0.9`, implement the mapper
and storage required by the privately selected Mario ROM. Defer other mappers,
CGB, SGB, and link support. Full APU completion and physical audio are deferred;
these releases prove silent video and input, not full DMG compatibility.

Build a Python assembler/linker, ROM packager, asset tools, and loader through
the shared builder. `v0.5` must use our software build. Use a pinned,
license-reviewed assembler as an independent encoding oracle. A C-like compiler
and rebuilding external game source are later work. Commercial ROMs already
contain machine code; our tools build our own programs.

## Input boundary

Use PC keyboard events over UART first; direct PS/2 follows later. Keep host
loading/control separate from input events. Converge scripted and keyboard
inputs at the emulated DMG button interface, so game ROMs need no custom host
MMIO. The pinned `frog-bui` [UART][uart], [PS/2][ps2], and
[shared input][keyboard] sources inform this separation without granting reuse.

## Release acceptance

Use simulated frame intervals from the approved timing contract, with an
independent cycle watchdog. Host wall-clock speed is not a compatibility test.
Fix reference checkpoints before judging DUT results. If ROM behavior makes a
bound unsuitable, obtain an explicit acceptance revision rather than tune the
bound to pass the implementation.

| Release | Required checks |
|---|---|
| `v0.5` | Two clean builds produce identical bytes; full load/readback matches. First expected image within 60 frame intervals; then run 600 intervals. Compare every visible pixel and every retired instruction of the bounded self-authored program with independent expectations. Script press/release of all eight buttons and one supported simultaneous pair; check registers and program effects. Corrupt image/pixel cases fail for their intended reason. |
| `v0.9` | Privately identify ROM and reference configuration. Named boot checkpoint within 600 frame intervals; then 3,600 intervals of scripted start/movement/action. Every frame and input checkpoint agrees with the reference; no unexplained mismatch, hang, or reset. |
| `v1.0` | After separate board approval and wiring/timing proof: full load/readback, scripted checkpoints and pre-VGA frame hashes match simulation; VGA and keyboard work; 30-minute continuous run without unexpected reset/lost input; repeat reset/load/start three times. Silent output. |

## Dependencies and authority

The [gap register](../preflight-gaps.md) owns closure evidence and the
[current phase](../agents/bootstrap-plan.md#current-phase) governs work order.
Exact Mario title and local ROM identity are required before cartridge work,
not before `v0.5`. Original sources remain private for now; source, ROM, and
reuse policy delivery belongs to
[#25](https://github.com/amichai-bd/nand2mario/issues/25).

Agents own focused issue boundaries, module organization, test seeds/artifacts,
and detailed ABI, reset/load, protocol, clock/CDC, and input contracts within
approved behavior. Escalate changes to scope, acceptance, or safety boundaries.
Programming, UART transmission, and physical tests need separate explicit
authorization and verified device, wiring, and voltage. Simulation cannot
satisfy physical acceptance. Questa evidence follows the
[temporary deferral](../preflight-gaps.md#gap-008-verification-baseline).

[uart]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/uart_ctrl/README.md
[ps2]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/ps2_keyboard/README.md
[keyboard]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/sw/include/frog/keyboard_input.h
