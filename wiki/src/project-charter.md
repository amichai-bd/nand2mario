# Project charter and release acceptance

Status: direction approved; release contract proposed in
[#24](https://github.com/amichai-bd/nand2mario/issues/24).

## Approved direction

Build an original-DMG-compatible Game Boy for the DE10-Lite. Design and verify
the hardware, build Python software tools that produce loadable programs, and
prove the complete system in simulation before board execution. Provide VGA
output and UART controls, with keyboard interaction informed by `frog-bui`.

Use the repository's issue, specification, implementation, verification, and
review flow. Keep software and hardware aligned through shared interface
contracts and the [build entry point](../tools/build-system.md).

The [reference study](rtl-reference-style.md) guides RTL style and verification.
Reference process and UART/input ideas do not select the Game Boy architecture
or permit copying code with unresolved reuse rights.

Original game ROMs already contain machine code; running them requires compatible
hardware and cartridge support. Our software tools build our own programs.
Rebuilding external game source is a separate, source/toolchain-dependent goal.

## Input design proposal

`frog-bui` separates [UART commands/input][uart] and [PS/2 reception][ps2], with
a [shared software input interface][keyboard]. Adapt that separation: keep host
loading/control separate from input routing, and map input to emulated DMG
buttons so game ROMs need no custom host MMIO. This source observation proposes
a boundary; it selects neither transport nor an implementation and proves no test.

## Proposed releases

These are candidate results, not approved acceptance criteria. Each release
needs a fixed test set, reference results, and run bounds before implementation.

| Release | Candidate result | Evidence to define |
|---|---|---|
| `v0.5` | Build and load a self-authored program; our CPU executes it, draws an image, and responds to input in full-system simulation. | Reproducible image build; load/readback check; expected CPU trace, pixels, and input-driven state; bounded PASS and deliberate-failure tests. |
| `v0.9` | Run the selected Mario ROM in full-system simulation. | Defined boot checkpoint, reference frames, scripted input outcomes, and uninterrupted run duration; private ROM identity and required mapper. |
| `v1.0` | Load and run the validated software on the DE10-Lite with VGA and interactive controls. | Verified board/wiring, timing closure, load integrity, matching display/input checks, and a sustained run with defined reset/recovery checks. |

## Decisions still required

- **Compatibility:** choose the DMG silicon behavior policy and treatment of
  undocumented or revision-dependent behavior.
- **Software:** choose assembler/linker first or an initial higher-level
  language; then specify outputs, ABI/runtime, diagnostics, and conformance.
- **Keyboard:** choose PC keyboard events over UART or a direct board interface.
- **Release scope:** approve the milestones and measurable boot, video, input,
  stability, and failure checks. Select the exact Mario title privately.
- **Feature boundaries:** proposed first releases defer CGB, SGB, physical link,
  and mappers beyond the selected cartridge. Decide when full APU behavior and
  physical audio are required, and when a higher-level compiler belongs.

The [gap register](../preflight-gaps.md) owns closure evidence, including
licenses/provenance, cartridge facts, audio, and compiler scope. These proposals
close no gaps. The [current phase](../agents/bootstrap-plan.md#current-phase)
governs which work may start; programming and physical tests still need explicit
authorization.

[uart]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/uart_ctrl/README.md
[ps2]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/ps2_keyboard/README.md
[keyboard]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/sw/include/frog/keyboard_input.h
