# Gaps before implementation

Status: product P0 gaps remain open; GAP-001, GAP-002, GAP-003, GAP-004, and GAP-009 closed

## Purpose

This register distinguishes post-research gaps from completed infrastructure.

The [current phase](agents/bootstrap-plan.md#current-phase) defines which work
may start. Gap priority and close conditions describe future requirements, not
execution permission.

The [build-system specification](tools/build-system.md) records output and caching
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
| GAP-001 | P0 | Closed | [#24](https://github.com/amichai-bd/nand2mario/issues/24) | Scope and success contract | DMG target, releases, and non-goals are approved |
| GAP-002 | P0 | Closed | [#25](https://github.com/amichai-bd/nand2mario/issues/25) | License, ROM policy, and provenance | Approved private source policy, provenance rules, and practical content safeguards are committed |
| GAP-003 | P0 | Closed | [#26](https://github.com/amichai-bd/nand2mario/issues/26) | Build command | A minimal `n2m` command runs from a fresh shell |
| GAP-004 | P0 | Closed | [#27](https://github.com/amichai-bd/nand2mario/issues/27) | Real environment doctor | Portable smoke and read-only identity checks work; licensed runtime evidence remains in GAP-008 |
| GAP-005 | P0 | Open | [#28](https://github.com/amichai-bd/nand2mario/issues/28) | Board wiring and safe bring-up | VGA test card and UART ping pass with documented wiring |
| GAP-006 | P0 | Open | [#29](https://github.com/amichai-bd/nand2mario/issues/29) | Clock, reset, and CDC plan | Frequencies, crossings, resets, and SDC rules are approved |
| GAP-007 | P0 | Open | [#30](https://github.com/amichai-bd/nand2mario/issues/30) | Executable interface contracts | Address maps, host registers, and trace formats have one source |
| GAP-008 | P0 | Open | [#31](https://github.com/amichai-bd/nand2mario/issues/31) | Verification baseline | A known-good DUT and deliberately failing DUT prove the harness |
| GAP-009 | P0 | Closed | [#14](https://github.com/amichai-bd/nand2mario/issues/14) | Initial agent skills | Core skills exist and have concise trigger tests and examples |
| GAP-010 | P0 | Open | [#32](https://github.com/amichai-bd/nand2mario/issues/32) | GitHub workflow, CI, and Pages | Templates, checks, rules, and deployment pass end to end |
| GAP-011 | P1 | Later | — | Cartridge and target ROM facts | Header is inspected privately and required mapper is specified |
| GAP-012 | P1 | Later | — | VGA frame crossing | Buffering and monitor timing pass simulation and hardware tests |
| GAP-013 | P1 | Later | — | External dependencies | Tests and tools are pinned, licensed, and reproducible |
| GAP-014 | P2 | Later | — | Physical audio path | Output method and acceptance test are selected |
| GAP-015 | P2 | Later | — | Native compiler scope | Language, ABI, outputs, and compatibility goal are approved |

## GAP-001 — Scope and success contract

**Current state**

The [charter](src/project-charter.md) records the approved end-to-end DMG direction
and approved DMG-family policy, bounded release acceptance, and deferred
features. Issue #24 records the decision; its charter closes this gap.

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

The [source policy](tools/provenance.md) records the owner's decision to keep
original hardware and software private with no reuse grant. No open-source
license is selected. The [provenance index](../tools/provenance.json) links the
existing dependency pins and notices. Ignore rules and required wiki checks
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
confirmed. Future dependency fetching remains in GAP-013.

## GAP-003 — Build command

**Current state**

The [build command](tools/build-system.md) implements tagged doctor, builder
checks, and portable self-checking simulation. Its stdlib host code and pinned
Icarus bootstrap satisfy [#26](https://github.com/amichai-bd/nand2mario/issues/26).
Questa licensing, full environment/hardware doctor, and software/FPGA backends
remain outside this result.

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

The [environment doctor](tools/build-system.md#environment-doctor) implements
checked portable/Questa smoke runs, Quartus edition reporting, and read-only
JTAG/UART enumeration. Portable smoke, selected UART health/identity, expected
JTAG identity, and scoped Quartus version checks satisfy the implementation
criteria in #27. Full environment readiness remains unproven; licensed runtime
evidence follows the [temporary deferral](#gap-008-verification-baseline).

**Risk**

Checking only executable names can report success while every simulation fails.

**Close when**

- Quartus and Questa are found without editing global `PATH`.
- License success, failure, or unverified scope is reported truthfully.
- A repository-owned SV design compiles, elaborates, runs, and checks a value in
  the portable simulator; positive licensed execution remains tracked in GAP-008.
- USB-Blaster reports the expected MAX 10 device.
- UART is found by VID, PID, or serial identity with an explicit override.
- WSL tools and optional dependencies are reported as pass, warning, or fail.
- The command performs no programming or UART transmission unless requested.
- One automated test proves the doctor reports a broken elaboration as failure.

## GAP-005 — Board wiring and safe bring-up

**Current state**

JTAG and a UART adapter are visible. Physical UART wire crossing, voltage, target
pins, reset polarity, and VGA monitor behavior remain unproven here.

Reference `frog-bui` assignments suggest:

- FPGA UART RX: Arduino D0, `PIN_AB5`;
- FPGA UART TX: Arduino D1, `PIN_AB6`;
- 3.3 V LVTTL with adapter TX connected to FPGA RX.

These reference values are not yet accepted project constraints.

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

The [timing contract](src/clocks-resets-cdc.md) defines the system clock, exact
average DMG enables, selected VGA rate, reset sequence, CDC ownership, and
required simulation/TimeQuest checks. Issue #29 delivers the contract only.
Generated PLL/RTL, fit, timing, and simulation evidence remain outstanding;
this gap stays open until the close conditions below are proven in
[#79](https://github.com/amichai-bd/nand2mario/issues/79) and
[#80](https://github.com/amichai-bd/nand2mario/issues/80).

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

External sources document the Game Boy memory map; this repository lacks a
canonical address map, host register map, UART packet format, trace format, and
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

The [tile pixel unit](src/display/tile-pixel.md) has a focused independent
testbench and dual-simulator runner. This does not establish the shared
assertion library, reference adapters, coverage model, or regression baseline.

**Temporary Questa deferral**

The user has deferred general Questa simulation until they confirm availability,
with a separately authorized tile/doctor diagnostic recheck. Real portable
simulation must compile, elaborate, run, and check expected results. Positive
and deliberately failing checks, independent review, and passing CI remain
required for affected delivery; compilation alone is not a simulation pass.

The [tile/doctor correction](https://github.com/amichai-bd/nand2mario/pull/77)
establishes licensed elaboration, normal and deliberately corrupt tile runs,
and the doctor's 22-observation checked smoke in Questa 2025.2. This is scoped
runtime evidence; it does not prove full environment or hardware readiness.

The shared baseline's good/broken examples and other accumulated licensed
coverage remain outstanding in
[#31](https://github.com/amichai-bd/nand2mario/issues/31). Each affected later issue
must identify any additional deferred Questa coverage and retained portable
evidence. Resume the accumulated licensed checks when the user confirms
availability. Failed doctor checks still report FAIL. GAP-008 remains open
until its full close conditions are met; this deferral substitutes portable
evidence only for implementation progress, not for licensed or physical proof.

**Risk**

Agents may implement many instructions without reliable evidence of correct
flags, timing, memory traffic, or interrupts.

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

Closed by issues [#7](https://github.com/amichai-bd/nand2mario/issues/7)
through [#10](https://github.com/amichai-bd/nand2mario/issues/10) and the
end-to-end audit in [#14](https://github.com/amichai-bd/nand2mario/issues/14).
Focused skills have short methods, separate templates, and examples.
Issue-helper validation tests pass. [#34](https://github.com/amichai-bd/nand2mario/issues/34)
aligns the flow and review guidance with the agreed operating rules.
Structural skill validation does not prove agent behavior; the
[scaffolding audit](https://github.com/amichai-bd/nand2mario/issues/36) links
observed workflow evidence.

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

A private GitHub repository, issue forms, a PR template, required PR and wiki
checks, protected `main`, labels, and automatic Pages deployment are proven.
[#34](https://github.com/amichai-bd/nand2mario/issues/34) defines the revised
agent workflow. [#40](https://github.com/amichai-bd/nand2mario/issues/40) and
[#41](https://github.com/amichai-bd/nand2mario/issues/41) provide the custom HTML
wiki and presentations, reusing original sources; the
[wiki contract](tools/wiki.md) owns its behavior. [#36](https://github.com/amichai-bd/nand2mario/issues/36)
records the final review, delivery, and cleanup evidence.
Product build CI and the protected physical runner remain open in
[#32](https://github.com/amichai-bd/nand2mario/issues/32).

**Risk**

Wiki-only checks cannot catch product defects. An unsafe self-hosted or hardware
job could run untrusted code on this PC or allow concurrent access to the FPGA.

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

The exact Mario file, header, size, mapper, RAM, and region are unknown. Do not
add a ROM to the repository to resolve them.

**Risk**

The wrong mapper or storage backend could be called Mario-compatible.

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

Identified test suites, RGBDS, and emulator references are not pinned or fetched
reproducibly. RGBDS is not installed locally.

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

“Software compiler” may mean an assembler/linker toolchain, C compiler, or new
higher-level language, each with different costs and interfaces.

**Risk**

Compiler work can delay hardware despite precompiled commercial cartridges and
RGBDS support for open test ROMs.

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

Follow the [future P0 sequence and implementation gate](agents/bootstrap-plan.md#future-p0-sequence).
The current phase names scoped evidence replacements for portable progress;
all outstanding licensed and physical close conditions remain tracked here.
