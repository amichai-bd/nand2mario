# Gaps before implementation

Implementation boundaries and remaining verification gaps.

## Purpose

This register states current prerequisites and remaining verification gaps.

The [current phase](agents/bootstrap-plan.md#current-phase) defines which work
may start. Gap priority and close conditions describe future requirements, not
execution permission.

The [build-system specification](tools/n2m/SPEC.md) records output and caching
design.

Priorities:

- **P0** — close before functional Game Boy RTL starts, subject to the explicit
  scoped evidence replacements in the current phase.
- **P1** — close before the affected subsystem or shared integration starts.
- **P2** — planned later; does not block early implementation.
- **Deferred** — intentionally waiting for user authorization or a later phase.

## Gap summary

| ID | Priority | State | Issue | Gap | Closed when |
|---|---|---|---|---|---|
| GAP-001 | P0 | Closed | — | Scope and success contract | DMG target, releases, and non-goals are approved |
| GAP-002 | P0 | Closed | — | License, ROM policy, and provenance | Approved private source policy, provenance rules, and practical content safeguards are committed |
| GAP-003 | P0 | Closed | — | Build command | A minimal `n2m` command runs from a fresh shell |
| GAP-004 | P0 | Closed | — | Real environment doctor | Checked smoke and read-only identity checks work; runtime checks are described in GAP-008 |
| GAP-005 | P0 | Open | [#28](https://github.com/amichai-bd/nand2mario/issues/28) | Board wiring and safe bring-up | VGA test card and UART ping pass with documented wiring |
| GAP-006 | P0 | Physical gap | [#28](https://github.com/amichai-bd/nand2mario/issues/28) | Clock, reset, and CDC plan | Implemented timing still needs connected-board display acceptance |
| GAP-007 | P0 | Closed | — | Executable interface contracts | Address maps, host registers, and trace formats have one source |
| GAP-008 | P0 | Closed | — | Verification baseline | A known-good DUT and deliberately failing DUT prove the harness |
| GAP-009 | P0 | Closed | — | Initial agent skills | Core skills exist and have concise trigger tests and examples |
| GAP-010 | P0 | Open | [#32](https://github.com/amichai-bd/nand2mario/issues/32) | Trusted product CI | Licensed execution route and protected physical runner are not activated |
| GAP-011 | P1 | Closed | — | Original game image and build facts | Original 32 KiB mapperless image, header, provenance and reproducible build are verified |
| GAP-012 | P1 | Later | — | VGA frame crossing | Buffering and monitor timing pass simulation and hardware tests |
| GAP-013 | P1 | Later | — | External dependencies | Tests and tools are pinned, licensed, and reproducible |
| GAP-014 | P2 | Later | — | Physical audio path | Output method and acceptance test are selected |
| GAP-015 | P2 | Later | — | Native compiler scope | Language, ABI, outputs, and compatibility goal are approved |

## GAP-001 — Scope and success contract

**Current state**

The [charter](src/project-charter.md) records the approved end-to-end DMG direction
and approved DMG-family policy, bounded release acceptance, and deferred
features. The target uses the [original platformer](src/sw/springtrail/SPEC.md)
and retains separate release verification. This scope gap is closed; the game
contract distinguishes implemented behavior from planned features.

**Risk**

Agents may add CGB behavior, unrelated mappers, audio output, or compiler work
before the core can run a test ROM.

**Close when**

- The first model is explicitly original DMG.
- A silicon behavior target or model policy is selected.
- `v0.5`, `v0.9`, and `v1.0` acceptance criteria are approved.
- CGB, SGB, link hardware, mapper breadth, and custom compiler timing are listed
  as included or deferred.
- The original platformer has observable boot, video, input, and stability checks.

## GAP-002 — License, ROM policy, and provenance

**Current state**

The [source policy](tools/provenance.md) records the owner's decision to keep
original hardware and software private with no reuse grant. No open-source
license is selected. The [provenance index](../tools/provenance.json) links the
existing dependency pins and notices. Ignore rules and the wiki check
reject protected file extensions and private paths, including forced tracked
ASCII save files. The policy states detection limits and review duties.

**Risk**

Commercial content encoded as ordinary source text and unknown secret formats
can evade automated checks. Independent provenance and diff review remain needed.

**Close when**

- The approved private/no-reuse-grant policy for hardware and software is committed.
- A short third-party/provenance policy exists.
- Dependency records require name, URL, commit or version, license, purpose,
  and local changes, linking existing authoritative records.
- Commercial ROM, Nintendo boot ROM, save, screenshot, and generated-image rules
  are enforced by ignore and CI checks.
- User ROMs are accepted only as ignored runtime paths.

**Reference reuse**

Treat reference HDL as behavioral research until file-level reuse permission is
confirmed. Dependency fetching requirements remain in GAP-013.

## GAP-003 — Build command

**Current state**

The [build command](tools/n2m/SPEC.md) implements tagged doctor, builder
checks and self-checking simulation through Questa. The
[builder implementation](../tools/n2m/cli.py) dispatches scoped doctor, software,
simulation, regression and FPGA stages with tagged evidence.

**Risk**

Agents may invent different commands, directories, or tool invocations.

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

The [environment doctor](tools/n2m/SPEC.md#environment-doctor) implements
checked Questa smoke runs, Quartus edition reporting, and read-only
JTAG/UART enumeration. It reports selected UART health/identity, expected JTAG
identity and Quartus version independently. Each run must establish current
environment readiness; executable discovery alone is not licensed runtime proof.

**Risk**

Checking only executable names can report success while every simulation fails.

**Close when**

- Quartus and Questa are found without editing global `PATH`.
- License success, failure, or unverified scope is reported truthfully.
- A repository-owned SV design compiles, elaborates, runs, and checks a value in
  Questa; scoped licensed execution is recorded in GAP-008.
- USB-Blaster reports the expected MAX 10 device.
- UART is found by VID, PID, or serial identity with an explicit override.
- WSL tools and optional dependencies are reported as pass, warning, or fail.
- The command performs no programming or UART transmission unless requested.
- One automated test proves the doctor reports a broken elaboration as failure.

## GAP-005 — Board wiring and safe bring-up

**Current state**

The [board target definitions](../src/fpga/de10_lite/targets.json) specify the
UART and display pins. Connected wiring, voltage and monitor qualification remain
incomplete under the open board gap. UART assignments are:

- FPGA UART RX: Arduino D0, `PIN_AB5`;
- FPGA UART TX: Arduino D1, `PIN_AB6`;
- 3.3 V LVTTL with adapter TX connected to FPGA RX.

These are committed project constraints. They do not establish that the attached
hardware matches the [electrical boundary](src/fpga-controls.md#electrical-boundary).

**Risk**

Incorrect direction or voltage can block communication or damage equipment.
The wrong device or bitstream could be programmed.

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

The [timing contract](src/clocks-resets-cdc.md) defines clocks, enables, reset
and CDC requirements. The [clocking implementation](src/rtl/clocking/MAS_clocking.md)
and [VGA frame bridge](src/rtl/vga/MAS_vga.md) have dedicated
[clocking](../src/dv/clocking/README.md) and [raster/ownership](../src/dv/vga/README.md)
checks. The [system composition](src/rtl/system/MAS_system.md) uses the specified
25 MHz system clock and separate VGA clock. Physical display acceptance remains
unproven under [GAP-005](#gap-005-board-wiring-and-safe-bring-up)
and [GAP-012](#gap-012-vga-frame-crossing).

**Risk**

Fabric-generated clocks, unconstrained crossings, or mismatched frame rates can
cause intermittent failures missed by simulation.

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

The [executable contract](src/rtl/interfaces/MAS_interfaces.md) owns one checked source
for Game Boy/host spaces, UART packets, direct-entry state and retirement
records, with generated SV/Python/wiki exports. Required CI checks regeneration,
byte/width/space tests and real positive/corrupt portable simulation. This closes
the interface-data gap. The endpoint, loader, snapshot and verification consumers
have their own behavior and tests in the [ownership map](ownership.md).

**Risk**

Future implementations could bypass generated constants; their reviews must
check consumption and full behavioral verification, not only codec agreement.

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

The [shared baseline](src/dv/baseline/SPEC.md) supplies separate stimulus,
observation, integer reference, scoreboard, assertions and fixture coverage.
Its known-good and deliberately broken examples run through Questa with checked
logs, seed, expected/actual CSV and waves. The regression runner checks raw failure
exits, complete traces and artifact integrity. Questa is the sole simulator.
The [baseline specification](src/dv/baseline/SPEC.md) links independent adapters,
their licenses, immutable pins, comparison formats and bounded regression levels.
Baseline fixture coverage is not CPU, full-system or physical acceptance.

**Questa evidence**

The [current authorization](agents/bootstrap-plan.md#verification-and-hardware-authorization)
supersedes the earlier general Questa deferral. Required Questa simulation must compile, elaborate, run, and check expected results. Positive
and deliberately failing checks, independent review, and passing CI remain
required for affected delivery; compilation alone is not a simulation pass.

The [tile runner](tools/sim/SPEC.md) checks normal and deliberately corrupt runs;
the [doctor](tools/n2m/SPEC.md#environment-doctor) checks smoke observations.
Isolated libraries and validated cache reuse belong to the shared backend.
The deliberately failing smoke remains FAIL; only exact expected tile corruption
is accepted. Each affected change must execute its own required Questa coverage.
Failed doctor checks
remain FAIL. Closing this baseline gap does not waive later subsystem,
independent adapter or physical verification.

**Risk**

Agents may implement many instructions without reliable evidence of correct
flags, timing, memory traffic, or interrupts.

**Close when**

- A small UVM-lite structure is committed.
- A known-good example passes in Questa.
- A deliberately broken example fails for the expected reason.
- Failure artifacts include logs, seed, waveform, and expected versus actual.
- SingleStepTests and Mooneye adapters are designed and license-reviewed.
- A trace-comparison format is agreed with an independent emulator.
- Regression levels and time budgets are documented.

## GAP-009 — Initial agent skills

**Current state**

Focused [skills](../.agents/skills/agent-flow/SKILL.md) have short methods,
separate templates and examples. The issue helper has validation tests.
The [agent rules](../AGENTS.md) govern flow and independent review. Structural
skill validation does not prove agent behavior; review evidence belongs in PRs.

**Risk**

Agents will reproduce long prompts, choose inconsistent validation, and let wiki
or PR evidence drift.

**Close when**

- `issue-author`, `pr-author`, `rtl-coder`, `dv-uvm-lite`,
  `fpga-de10-lite`, `wiki-spec-writer`, `build-maintainer`, and
  `uart-host-tool` exist.
- Each skill has a narrow trigger and non-trigger description.
- Each skill links to sources rather than duplicating specifications.
- Each skill keeps its short method and stop conditions in `SKILL.md` and links
  its reusable template and scenarios.
- Trigger examples are tested against likely user requests.
- Skills do not claim planned build commands have passed.

## GAP-010 — GitHub remote, issues, CI, and Pages

**Current state**

A private GitHub repository, issue forms, a PR template, a required PR policy
check, protected `main`, labels, and automatic Pages deployment are proven.
The [wiki contract](tools/wiki/SPEC.md) defines custom HTML navigation and
presentations rendered from original sources.
Builder and Tile runner checks run locally before merge and by dispatch; they
check host contracts only.
Actual local Questa evidence remains mandatory; automated licensed simulation
is unavailable until the [trusted route](tools/n2m/SPEC.md#ci-execution-boundary)
is configured. Required product checks and the protected physical runner remain
open in [#32](https://github.com/amichai-bd/nand2mario/issues/32).

**Risk**

Wiki-only checks cannot catch product defects. An unsafe self-hosted or hardware
job could run untrusted code on this PC or allow concurrent access to the FPGA.

**Close when**

- Issue and PR templates are installed and tested.
- GitHub labels match `.github/labels.yml`.
- `main` requires focused host/product checks with honest licensed execution evidence.
- Wiki build and link checks run locally before merge and in the Pages build.
- Pages deploys only from merged `main`.
- Questa, Quartus, and board jobs run only for trusted code.
- The physical runner uses concurrency control and a protected environment.
- One sample issue completes branch, PR, checks, merge, and Pages deployment.

## GAP-011 — Original game image and build facts

**Current state**

The authorized goal is the [original platformer](src/sw/springtrail/SPEC.md),
built as a 32768-byte mapperless SM83 ROM with no cartridge RAM. There is no
commercial file, title or mapper to obtain. The
[software build](tools/sw/SPEC.md) checks original source/assets and the supported
header/profile. Its [composed-system tests](src/dv/springtrail/SPEC.md) check
title, input and world frames with deliberate output faults. Movement and
interactions are implemented; expanded features are explicitly planned in the
game specification. Physical release verification remains incomplete in
[#264](https://github.com/amichai-bd/nand2mario/issues/264).

**Risk**

A non-reproducible image or unsupported header/profile could conceal a build
or compatibility defect. Original content must not inherit copied game assets.

**Close when**

- Original source, character/art/level assets and their provenance are recorded.
- Two clean software builds produce identical image bytes and hashes.
- The built header/checksums identify the supported 32 KiB ROM-only/no-RAM profile.
- The image uses the existing direct-entry and Intel-backed storage contracts,
  with no MBC or SDRAM dependency.
- The original image loads and reaches the independently checked foundation
  checkpoint; later game verification and physical acceptance remain separate.

## GAP-012 — VGA frame crossing

**Current state**

The [VGA contract](src/rtl/vga/MAS_vga.md) specifies buffer format, ownership,
scaling and shade mapping under the shared clock/reset/CDC contract.
The [VGA tests](../src/dv/vga/README.md) check ownership, raster geometry,
bank reuse, active-swap failures and source-to-VGA RGB replicas with canonical
source/output CRCs. FPGA checks cover three-bank RAM inference and constrained
timing. Source/snapshot comparison is separate from VGA-output checking.
These component checks leave physical display acceptance open. Actual monitor
tolerance, test-card/scaled-image operation, and connected pin/wiring/voltage
verification also remain open under [GAP-005](#gap-005-board-wiring-and-safe-bring-up).
Simulation and fit evidence do not replace physical acceptance.

**Risk**

A correct PPU can still feed a physical display that tears, repeats partial
frames, or rejects timing.

**Close when**

- Pixel and buffer formats are specified.
- Buffer swap ownership and CDC handshake are specified.
- Simulation proves no partial-frame display.
- The VGA test card and scaled test image work on the actual monitor.
- Frame CRCs match before and after the VGA adapter.
- Quartus confirms intended block-RAM inference and acceptable resources.

## GAP-013 — External dependencies

**Current state**

The [RGBDS oracle](tools/sw/SPEC.md#implemented-oracle) is pinned, hash-verified,
provisioned and exercised by local checks and dispatched Builder runs. Independent adapters have
their own pinned fetching and executable acceptance contracts in the
[baseline specification](src/dv/baseline/SPEC.md). Each dependency must satisfy
the requirements below; adding a pin alone does not prove an adapter works.

**Risk**

Tests may change, disappear, or introduce incompatible licenses. CI and local
results may differ.

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

The [native software toolchain](tools/sw/SPEC.md) implements assembly, linking,
ROM packaging and asset conversion. A C compiler or new higher-level language
is outside that implemented scope and needs a separate approved contract.

**Risk**

Compiler work can delay delivery despite the existing original-program pipeline and
RGBDS support for open test ROMs.

**Close when**

- The source language and compatibility goal are selected.
- Object format, linker model, calling convention, runtime, and debug output are
  specified.
- Bootstrap versus self-hosting expectations are clear.
- A conformance and differential-test plan exists.
- The compiler has its own milestone and does not block initial Game Boy RTL.

**Recommended default**

Use the existing native toolchain and pinned RGBDS oracle. Treat any C-like
compiler, language runtime or broader development environment as later work.

## Required closing order

Follow the [future P0 sequence and implementation gate](agents/bootstrap-plan.md#future-p0-sequence).
The current phase names scoped evidence replacements for independent progress;
all outstanding licensed and physical close conditions remain tracked here.
