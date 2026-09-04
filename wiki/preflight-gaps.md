# Gaps before implementation

Date: 2026-09-04

Status: open gap register

## Purpose

This file records what is missing after research. It prevents planned work from
being mistaken for completed infrastructure.

The current output and caching design is recorded in the
[build-system specification](tools/build-system.md).

Priorities:

- **P0** — close before functional Game Boy RTL starts.
- **P1** — close before the affected subsystem or shared integration starts.
- **P2** — planned later and does not block early implementation.
- **Deferred** — intentionally waiting for user authorization or a later phase.

The board-proving test design is allowed during P0. It should contain only the
logic needed to test clocks, VGA, UART, reset, and safe programming.

## Gap summary

| ID | Priority | Gap | Closed when |
|---|---|---|---|
| GAP-001 | P0 | Scope and success contract | DMG target, releases, and non-goals are approved |
| GAP-002 | P0 | License, ROM policy, and provenance | Licenses and reuse rules are committed |
| GAP-003 | P0 | Build command | A minimal `n2m` command runs from a fresh shell |
| GAP-004 | P0 | Real environment doctor | It proves compile, elaborate, run, JTAG, and UART detection |
| GAP-005 | P0 | Board wiring and safe bring-up | VGA test card and UART ping pass with documented wiring |
| GAP-006 | P0 | Clock, reset, and CDC plan | Frequencies, crossings, resets, and SDC rules are approved |
| GAP-007 | P0 | Executable interface contracts | Address maps, host registers, and trace formats have one source |
| GAP-008 | P0 | Verification baseline | A known-good DUT and deliberately failing DUT prove the harness |
| GAP-009 | P0 | Initial agent skills | Core skills exist and have concise trigger tests and examples |
| GAP-010 | P0 | GitHub workflow, CI, and Pages | Templates, checks, rules, and deployment pass end to end |
| GAP-011 | P1 | Cartridge and target ROM facts | Header is inspected privately and required mapper is specified |
| GAP-012 | P1 | VGA frame crossing | Buffering and monitor timing pass simulation and hardware tests |
| GAP-013 | P1 | External dependencies | Tests and tools are pinned, licensed, and reproducible |
| GAP-014 | P2 | Physical audio path | Output method and acceptance test are selected |
| GAP-015 | P2 | Native compiler scope | Language, ABI, outputs, and compatibility goal are approved |

## GAP-001 — Scope and success contract

**Current state**

The direction is clear, but “entire Game Boy” can mean original DMG hardware,
all later Game Boy models, or every cartridge peripheral ever released. Those
are very different projects.

**Risk**

Agents may add CGB behavior, unrelated mappers, audio output, or compiler work
before the core can run a test ROM.

**Close when**

- The first model is explicitly original DMG.
- A silicon behavior target or model policy is selected.
- `v0.5`, `v0.9`, and `v1.0` acceptance criteria are approved.
- CGB, SGB, link hardware, mapper breadth, and custom compiler timing are listed
  as included or deferred.
- “Mario works” has observable boot, video, input, and stability checks.

**Recommended first issue**

Create `Project charter and release acceptance` with no RTL changes.

## GAP-002 — License, ROM policy, and provenance

**Current state**

The repository has no license. The inspected `frog-bui` commit also has no root
license file. External cores and test packages use different licenses.

**Risk**

Unclear reuse rights can make code impossible to publish. A commercial ROM or
boot ROM could be committed accidentally.

**Close when**

- Hardware and software licenses are selected.
- A short third-party/provenance policy exists.
- Each imported dependency has a name, URL, commit, license, and purpose.
- Commercial ROM, Nintendo boot ROM, save, screenshot, and generated-image rules
  are enforced by ignore and CI checks.
- User ROMs are accepted only as ignored runtime paths.

**Recommended default**

Use permissive licenses where possible. Treat reference HDL as behavioral
research until file-level reuse permission is confirmed.

## GAP-003 — Build command

**Current state**

No build package, Python project, lock file, wrapper, or output convention
exists. Commands shown in the research document are planned interfaces only.

**Risk**

Every agent may invent a different command, directory, or tool invocation.

**Close when**

- `python tools/build.py doctor`, `check`, and one simulation command exist.
- The entry point works from a fresh PowerShell session.
- Commands are implemented as small Python modules.
- All generated output goes to ignored `workdir/`.
- An explicit tag reuses matching stages by content fingerprint.
- A missing tag creates a UTC timestamp build.
- Exit codes are reliable and machine-readable JSON is available.
- Results record tool versions, Git commit, inputs, seed, and artifacts.
- A clean checkout can bootstrap Python dependencies from a pinned definition.

## GAP-004 — Real environment doctor

**Current state**

Tools were inspected manually. Quartus is outside `PATH`. Questa compiled RTL,
but the reference smoke exposed library-path and stale-port problems.

**Risk**

A doctor that checks only executable names can report success while every real
simulation fails.

**Close when**

- Quartus and Questa are found without editing global `PATH`.
- The expected license is checked.
- A repository-owned SV design compiles, elaborates, runs, and checks a value.
- USB-Blaster reports the expected MAX 10 device.
- UART is found by VID, PID, or serial identity with an explicit override.
- WSL tools and optional dependencies are reported as pass, warning, or fail.
- The command performs no programming or UART transmission unless requested.
- One automated test proves the doctor reports a broken elaboration as failure.

## GAP-005 — Board wiring and safe bring-up

**Current state**

JTAG and `COM3` are visible. The physical UART wire crossing, voltage, target
pins, reset polarity, and VGA monitor behavior have not been proven here.

Reference `frog-bui` assignments suggest:

- FPGA UART RX: Arduino D0, `PIN_AB5`;
- FPGA UART TX: Arduino D1, `PIN_AB6`;
- 3.3 V LVTTL with adapter TX connected to FPGA RX.

These are reference values, not yet accepted project constraints.

**Risk**

Incorrect direction or voltage can prevent communication or damage equipment.
An incorrect device or bitstream could be programmed.

**Close when**

- The DE10-Lite manual and physical wires agree with committed pin constraints.
- Voltage and ground are checked.
- Programming first verifies the USB-Blaster and `10M50DA` identity.
- A heartbeat and VGA test card work.
- A versioned UART ping and CRC failure test work.
- Programming and hardware tests use an exclusive lock.
- The resulting FPGA build ID can be read through UART.

## GAP-006 — Clock, reset, and CDC plan

**Current state**

The board clock is 50 MHz. Game Boy timing and 640 by 480 VGA require different
rates. The exact PLL outputs, clock-enable approach, error tolerance, buffer
crossing, and reset release are undecided.

**Risk**

Fabric-generated clocks, unconstrained crossings, or mismatched frame rates can
create intermittent failures that simulations miss.

**Close when**

- Required Game Boy and VGA rates and allowed error are written down.
- A PLL or clock-enable design is generated and reviewed.
- Every clock and generated clock is constrained.
- Reset assertion and synchronized release are specified for each domain.
- Framebuffer and control crossings use named CDC structures.
- TimeQuest reports no unexplained unconstrained paths.
- Simulation checks tick counts, line length, frame length, and buffer swaps.

## GAP-007 — Executable interface contracts

**Current state**

The Game Boy memory map is documented externally, but this repository has no
canonical address map, host register map, UART packet format, trace format, or
generated constants.

**Risk**

RTL, testbenches, Python, and wiki tables can use different values.

**Close when**

- Machine-readable contracts exist for Game Boy registers, host control
  registers, UART commands, and retirement trace fields.
- SystemVerilog and Python constants are generated from those contracts.
- Human-readable wiki tables are generated from the same data.
- Generated files are marked and never hand-edited.
- CI regenerates the contracts and fails on a diff.
- Game Boy addresses and host-only addresses are visibly separate.

## GAP-008 — Verification baseline

**Current state**

Questa and open-source tools are available, but there is no repository testbench,
assertion library, scoreboard, reference adapter, coverage model, or regression
manifest.

**Risk**

Agents may implement many instructions before there is trustworthy evidence of
correct flags, timing, memory traffic, or interrupts.

**Close when**

- A small UVM-lite structure is committed.
- A known-good example passes in Questa and the selected portable simulator.
- A deliberately broken example fails for the expected reason.
- Failure artifacts include logs, seed, waveform, and expected versus actual.
- SingleStepTests and Mooneye adapters are designed and license-reviewed.
- A trace-comparison format is agreed with an independent emulator.
- Regression levels and time budgets are documented.

## GAP-009 — Initial agent skills

**Current state**

Skill names and responsibilities are planned, but no repository skills exist.

**Risk**

Agents will reproduce long prompts, choose inconsistent validation, and let wiki
or PR evidence drift.

**Close when**

- `issue-author`, `pr-author`, `rtl-coder`, `dv-uvm-lite`,
  `fpga-de10-lite`, and `wiki-spec-writer` exist.
- Each skill has a narrow trigger and non-trigger description.
- Each skill links to sources rather than duplicating specifications.
- Each skill defines inputs, steps, outputs, validation, stop conditions, one
  good example, and one bad example.
- Trigger examples are tested against likely user requests.
- Skills invoke real build commands rather than planned commands.

Add `build-maintainer`, `uart-host-tool`, and `sm83-platform` only when their
interfaces exist.

## GAP-010 — GitHub remote, issues, CI, and Pages

**Current state**

A private GitHub repository, three issue forms, a PR template, a PR policy
check, and the canonical label catalog exist. Main-branch rules, build CI, a
self-hosted runner, and Pages do not.

**Risk**

The intended GitHub Flow and wiki deployment cannot be tested. A careless
self-hosted runner configuration could execute untrusted code on this PC.

**Close when**

- Issue and PR templates are installed and tested.
- GitHub labels match `.github/labels.yml`.
- `main` requires focused portable checks.
- Wiki build and link checks run on PRs.
- Pages deploys only from merged `main`.
- Questa, Quartus, and board jobs run only for trusted code.
- The physical runner uses concurrency control and a protected environment.
- One sample issue completes branch, PR, checks, merge, and Pages deployment.

## GAP-011 — Cartridge and target ROM facts

**Current state**

The exact Mario file, header, size, mapper, RAM, and region are unknown. No ROM
should be added to the repository to answer these questions.

**Risk**

The project could build the wrong mapper or storage backend and still call it
Mario-compatible.

**Close when**

- The user supplies a local ROM path outside version control.
- A tool reports title, hashes, header checksum, ROM size, RAM size, and mapper.
- Only hashes and technical header facts are retained in private/local results.
- The required mapper has a short contract and directed tests.
- The selected on-chip or SDRAM storage backend fits the image.

## GAP-012 — VGA frame crossing

**Current state**

Three-times scaling and centering are recommended, but buffer format, write/read
ownership, frame-rate difference, palette mapping, and monitor tolerance are not
proven.

**Risk**

The PPU can be correct while the physical display tears, repeats partial frames,
or rejects the timing.

**Close when**

- Pixel and buffer formats are specified.
- Buffer swap ownership and CDC handshake are specified.
- Simulation proves no partial-frame display.
- The VGA test card and scaled test image work on the actual monitor.
- Frame CRCs match before and after the VGA adapter.
- Quartus confirms intended block-RAM inference and acceptable resources.

## GAP-013 — External dependencies

**Current state**

Useful test suites, RGBDS, and emulator references were identified but are not
pinned or fetched reproducibly. RGBDS is not installed locally.

**Risk**

Tests may change underneath the project, disappear, or introduce incompatible
licenses. CI and local results may differ.

**Close when**

- A dependency manifest pins every URL and commit or version.
- Hashes and licenses are recorded.
- Downloads go to `workdir/cache` or `workdir/tools`, not source directories.
- Offline behavior and cache validation are clear.
- Test selection and expected pass signatures are versioned.
- CI uses the same manifest as local builds.

## GAP-014 — Physical audio path

**Current state**

The full DMG goal includes APU behavior, but the requested VGA and UART setup
does not define a physical audio connection.

**Risk**

APU RTL may be confused with successful audible board output.

**Close when**

- Simulation PCM format and APU acceptance tests are defined.
- A physical output is selected, such as a documented GPIO adapter, PWM path, or
  external DAC.
- Voltage, filter, amplifier, and connector requirements are documented.
- The release plan states whether physical audio is required for `v1.0`.

This does not block silent video and input bring-up.

## GAP-015 — Native compiler scope

**Current state**

“Software compiler” may mean an assembler/linker toolchain, a C compiler, or a
new higher-level language. Those products have different costs and interfaces.

**Risk**

Compiler work can delay hardware even though commercial cartridges are already
compiled and open test ROMs can use RGBDS.

**Close when**

- The source language and compatibility goal are selected.
- Object format, linker model, calling convention, runtime, and debug output are
  specified.
- Bootstrap versus self-hosting expectations are clear.
- A conformance and differential-test plan exists.
- The compiler has its own milestone and does not block initial Game Boy RTL.

**Recommended default**

Use pinned RGBDS for bring-up. Build a native assembler, linker, disassembler,
ROM-header tool, runtime, and asset converter after the ISA contract is stable.
Treat a C-like compiler as a separate later epic.

## Required closing order

Before functional Game Boy RTL:

1. GAP-001 and GAP-002: approve scope and legal boundaries.
2. GAP-003 and GAP-004: create and prove the build environment.
3. GAP-005 and GAP-006: prove board I/O and clock safety.
4. GAP-007 and GAP-008: establish executable contracts and trusted tests.
5. GAP-009: make the agent workflow repeatable.

Then create the first CPU issue. Resolve GAP-011 through GAP-013 before system
integration. GAP-014 and GAP-015 can remain later milestones. GAP-010 waits for
explicit authorization to create the GitHub remote.
