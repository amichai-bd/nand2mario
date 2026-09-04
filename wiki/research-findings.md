# Research findings

Date: 2026-09-04

Status: research baseline complete

## Conclusion

The connected PC and DE10-Lite are suitable for this project. Quartus, Questa,
JTAG, UART, Python, GitHub tooling, and useful open-source verification tools are
available.

The project should start with a small environment milestone. That milestone
must prove the build command, simulation, VGA, UART, and safe board programming
before functional Game Boy RTL begins.

The first compatibility target should be the original monochrome Game Boy
(DMG). The first visible product goal is a user-supplied Mario ROM running over
VGA with CLI-controlled input. Full DMG completion, audio, more cartridge
mappers, and a native software compiler follow in explicit milestones.

## Repository state at handoff

- Git was initialized locally.
- The initial branch was renamed from `master` to `main` for this baseline.
- A private GitHub remote was created after the research baseline.
- No FPGA was programmed during research.
- No UART data was transmitted during research.
- No Game Boy RTL or build system exists yet.
- The repository still contains policy and planning only; implementation has
  not started.

## Local environment

| Item | Finding |
|---|---|
| Host | Windows 11 with PowerShell 7.6.5 |
| Git | 2.54.0.windows.1 |
| GitHub CLI | 2.92.0, authenticated to GitHub as `amichai-bd` |
| Python | 3.14.5 with `pyserial`; `pytest` is not installed |
| Quartus | Prime Lite 25.1std.0 Build 1129 with MAX 10 support |
| Quartus path | Installed outside the normal `PATH`; resolve through tool configuration |
| Questa | Questa FPGA Starter Edition 2025.2; license variables are set |
| FPGA | USB-Blaster detects MAX 10 device `10M50DA` |
| UART | FTDI USB serial adapter detected; select its port at runtime |
| WSL | Ubuntu 24.04 is available |
| WSL RTL tools | Icarus 12.0, Verilator 5.020, Yosys 0.33, SymbiYosys 0.63 |
| Missing tools | RGBDS, SDCC/GBDK, pytest, Ninja, and native Windows open RTL tools |
| Containers | Docker was not found |

Quartus is not on the normal Windows `PATH`. The future build command should
discover the known installation and allow an ignored local override. It should
not require global machine changes.

## Tool smoke results

- `jtagconfig` identified the connected MAX 10 through USB-Blaster.
- Windows identified the FTDI serial adapter. The port is runtime-selected.
- Questa compiled the inspected `frog-bui` RTL without compile errors.
- The `frog-bui` MMIO smoke did not reach a passing simulation. Its builder used
  a Windows library path incorrectly, and the reference testbench also had stale
  implicit port connections.

This is not evidence that Questa is broken. It is evidence that a useful
environment doctor must compile, elaborate, execute, and check a repository-owned
known-good test. Version detection and compilation alone are insufficient.

## Reference project review

The main process reference was the private
[`frog-bui` repository at commit `2fa0be4`](https://github.com/amichai-bd/frog-bui/tree/2fa0be4e5b2ef7b52fc42ae9eb74a0a459782e5a).
No code was copied.

Patterns worth keeping:

- issue, specification, implementation, test, and PR traceability;
- a single user-facing build command;
- simulation, FPGA, and UART operations behind that command;
- fixed, versioned UART packets with a checksum;
- a living wiki deployed from `main`;
- isolated, short-lived issue branches and worktrees;
- validation that grows from compile to simulation to hardware;
- machine-readable build results and artifact manifests; and
- separate hosted CI from licensed or physical-hardware jobs.

Patterns to improve:

- Keep build commands in small Python modules rather than one very large file.
- Split CI by purpose so failures are easy to locate.
- Test elaboration and execution, not only compilation.
- Check issue labels and documentation for stale state automatically.
- Keep `AGENTS.md`, skills, issues, and wiki pages short.
- Avoid copying reference code until its license and provenance are clear. No
  root license file was found in the inspected `frog-bui` commit.

## Game Boy technical findings

- The CPU target is the Sharp SM83. It is not RISC-V and should not be treated as
  a generic Z80.
- The CPU has an 8-bit data path, a 16-bit address space, variable-length
  instructions, and timing-sensitive interrupt and HALT behavior.
- The memory map separates cartridge ROM/RAM, VRAM, work RAM, OAM, I/O, high RAM,
  and interrupt enable.
- The display is 160 by 144 pixels. It uses 8 by 8, 2-bit-per-pixel tiles,
  background/window layers, and sprites.
- The PPU has 154 lines of 456 dots. Mode 3 length changes with scrolling,
  windows, and sprites. A frame-only renderer is not a sufficient final model.
- Joypad register `FF00` exposes two active-low four-button groups and can cause
  an interrupt on a selected high-to-low transition.
- OAM DMA, timer overflow, interrupt entry, EI delay, and the HALT bug need
  directed timing tests.
- Cartridge hardware varies. The exact Mario ROM header must determine which
  mapper and storage capacity are required.

Primary behavior references:

- [Game Boy Complete Technical Reference](https://gekkio.fi/files/gb-docs/gbctr.pdf)
- [Pan Docs instruction set](https://gbdev.io/pandocs/CPU_Instruction_Set.html)
- [Pan Docs memory map](https://gbdev.io/pandocs/Memory_Map.html)
- [Pan Docs hardware registers](https://gbdev.io/pandocs/Hardware_Reg_List.html)
- [Pan Docs rendering](https://gbdev.io/pandocs/Rendering.html)
- [Pan Docs joypad input](https://gbdev.io/pandocs/Joypad_Input.html)

## Recommended system boundary

### Game Boy system

- SM83 CPU and interrupt control
- cartridge and mapper interface
- work RAM, high RAM, video RAM, and OAM
- timer, divider, DMA, joypad, and serial registers
- dot-aware PPU
- APU and serial/link completion for the full DMG milestone

### Host control plane

UART should access a separate, versioned host register space. It should provide:

- version and capability discovery;
- reset, run, halt, and step control;
- safe ROM loading with length, header, hash, and checksum checks;
- joypad press, release, and tap operations;
- trace and status access; and
- frame CRC or framebuffer readback.

The host register space must not occupy normal Game Boy addresses. Host joypad
state feeds the authentic `FF00` behavior. ROM writes must be blocked or
arbitrated while the CPU is running.

### Display path

- Keep the PPU behavior independent of VGA timing.
- Store completed pixels in on-chip dual-port or double-buffered memory.
- Scale 160 by 144 by three to 480 by 432.
- Center that image inside a 640 by 480 VGA frame.
- Swap buffers safely at VGA blanking to avoid tearing.
- Check frames by CRC in simulation and hardware.

The exact Game Boy and VGA clock plan remains an open design decision. It must
be proven with generated clocks, explicit clock-domain crossings, and complete
TimeQuest constraints.

## Verification findings

Recommended independent evidence:

- exhaustive ALU and flag tests;
- [SingleStepTests SM83 vectors](https://github.com/SingleStepTests/sm83);
- [Mooneye Test Suite](https://github.com/Gekkio/mooneye-test-suite);
- selected open test ROMs with pinned commits and recorded licenses;
- differential retirement traces against
  [SameBoy](https://github.com/LIJI32/SameBoy);
- SystemVerilog assertions and focused formal checks;
- frame CRCs and captured failure waveforms; and
- Quartus fit, resource, RAM inference, and timing reports.

Use a UVM-lite structure first: interfaces, transactions, drivers, monitors,
scoreboards, assertions, coverage, and reference models. Questa is the
authoritative SystemVerilog simulator. Verilator, Icarus, Yosys, and SymbiYosys
provide fast and portable checks.

A model generated from the same opcode table as the RTL is not an independent
oracle. At least one test path must come from an independent implementation or
published vector set.

## Build and repository findings

The repository separates product, automation, configuration, documentation,
and generated work:

- `src/` contains RTL, verification, target software, and FPGA files.
- `tools/` contains checked-in build and automation code.
- `cfg/` contains only small, project-wide YAML configuration.
- `wiki/` contains short documentation for source, tools, and agents.
- `.agents/` and `.github/` contain agent and GitHub integration metadata.
- ignored `workdir/` contains downloaded tools, cache, tagged builds, and logs.

Owner-specific configuration stays with its owner. Do not create speculative
configuration directories.

The planned command should be small and consistent:

```text
python tools/build.py doctor
python tools/build.py check
python tools/build.py sim test <test>
python tools/build.py sim regress <level>
python tools/build.py fpga build|program
python tools/build.py uart ping|load-rom|press|release|tap
python tools/build.py docs build|serve
```

The command does not exist yet. It should be a modular, standard-library-first
Python package with JSON results, dry runs where useful, and reproducible
manifests. All tools should use it rather than duplicate shell commands.

An explicit build tag reopens a persistent workspace and reuses stages whose
content fingerprints still match. Without a tag, the build uses a UTC timestamp.
The complete layout is in the
[build-system specification](tools/build-system.md).

## Development flow

- One issue defines one observable result.
- The issue contains one goal, three to five acceptance checks, a spec link, and
  a short out-of-scope list.
- One short-lived branch and worktree implement the issue.
- The PR links the issue, lists up to three changes, declares spec impact, and
  records exact verification commands.
- Behavioral changes update specification, code, and tests together.
- Hosted CI runs documentation, Python, and portable RTL checks.
- Trusted self-hosted jobs run Questa, Quartus, and physical-board tests.
- Wiki checks run on pull requests. Pages deploys only after merge to `main`.

`AGENTS.md` should remain a short constitution and map. Skills hold focused
procedures. The wiki holds behavior. Issues hold goals. PRs hold change evidence.

## Recommended delivery sequence

1. Close the preflight blockers and create the environment bootstrap.
2. Prove a known-good simulation, VGA test card, UART ping, and safe programming.
3. Define executable memory-map, host-register, trace, clock, and PPU contracts.
4. Build the UVM-lite harness and independent CPU test adapters.
5. Implement and verify the SM83.
6. Add memory, cartridge support, timer, interrupts, joypad, DMA, and serial.
7. Implement the dot-aware PPU, framebuffer, and VGA adapter.
8. Add the UART loader, control plane, trace, and CLI input.
9. Run open system tests, close Quartus timing, and automate board tests.
10. Load the user-owned Mario ROM, inspect its header, add only the required
    mapper support, and demonstrate stable play.
11. Complete APU/link behavior and broader cartridge support.
12. Build the native assembler/toolchain, then treat a high-level compiler as a
    separate product milestone.

## External project references

These are useful behavioral or architectural references, not sources to copy
without checking file-level licenses:

- [VerilogBoy](https://github.com/zephray/VerilogBoy)
- [MiSTer Game Boy core](https://github.com/MiSTer-devel/Gameboy_MiSTer)
- [dmg-sim](https://github.com/msinger/dmg-sim)
- [SameBoy](https://github.com/LIJI32/SameBoy)
- [RGBDS](https://github.com/gbdev/rgbds)

Official platform and workflow references:

- [Terasic DE10-Lite resources](https://www.terasic.com.tw/cgi-bin/page/archive.pl?Language=English&No=1021&PartNo=4%2F1000)
- [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow)
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Actions security](https://docs.github.com/en/actions/reference/security/secure-use)
- [Codex skills](https://developers.openai.com/codex/skills)
- [Codex `AGENTS.md` guidance](https://developers.openai.com/codex/guides/agents-md)
