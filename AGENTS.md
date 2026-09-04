# Agent working rules

## Goal

Build a verified, original-DMG-compatible Game Boy hardware implementation for
the DE10-Lite. It should run open test ROMs and a user-supplied Mario cartridge,
display through VGA, and accept controls through UART.

## Current state

This repository contains a research baseline only. Before functional RTL work,
read `wiki/preflight-gaps.md` and close the applicable blockers.

The repository is local. Do not create a remote, publish pages, or program the
FPGA unless the user explicitly asks for that action.

## Sources of truth

- The issue states the goal and acceptance criteria.
- The wiki states required behavior and design decisions.
- A skill states how to perform a recurring task.
- `src/` contains implementation and verification.
- Tests and artifacts provide evidence.
- This file contains rules that apply to all work.

Do not duplicate a long rule or specification in several places. Link to its
source instead.

## Work flow

- Use one issue for one observable result.
- Use one short-lived branch per issue: `issue/<number>-<slug>`.
- Read the issue and linked specification before editing.
- Keep the change inside the issue acceptance criteria.
- Change specification, implementation, and tests together when behavior
  changes.
- Record an explicit `no documentation impact` reason when no spec changes.
- Prefer small commits that leave the tree testable.
- Open a draft PR early when a GitHub remote exists.
- Squash merge after required checks pass, then delete the branch.

Until the issue tracker exists, do only repository-bootstrap work explicitly
requested by the user.

## Repository layout

- Put synthesizable RTL in `src/rtl/`.
- Put testbenches, formal properties, and test manifests in `src/dv/`.
- Put DE10-Lite project and constraint files in `src/fpga/de10_lite/`.
- Put target-side software and test ROM sources in `src/sw/`.
- Put host build and UART tools in `src/tools/`.
- Put human-readable specifications and decisions in `wiki/`.
- Put generated output only in `.work/`.

Do not create a new top-level project directory without a clear need.

## Build and validation

The planned command is `n2m`. It does not exist yet. Until it is implemented,
record every exact command used and do not claim a planned command passed.

Use the smallest validation level that proves the change, then run all lower
levels:

1. Formatting, links, schema, lint, compile, and elaboration.
2. Unit simulation and assertions.
3. CPU vectors and subsystem tests.
4. Open Game Boy test ROMs and differential checks.
5. Quartus synthesis, fitting, and TimeQuest.
6. Explicitly authorized tests on the connected board.

A passing tool-version check is not a simulation test. A simulation must
compile, elaborate, run, and check an expected result.

## Definition of done

- The issue acceptance criteria are met.
- Relevant specifications are current and linked.
- Tests cover normal behavior and important edge cases.
- Required checks pass without unexplained warnings.
- Results identify the Git commit, tools, inputs, and seed where applicable.
- Generated files, ROMs, credentials, and machine-specific paths are absent
  from the commit.

## Hardware safety

- Confirm the USB-Blaster and expected MAX 10 device before programming.
- Keep FPGA programming and physical UART tests explicit.
- Serialize access to the board.
- Never program hardware from an untrusted pull request.
- Do not assume UART voltage or pin direction; verify the wiring first.
- Report what was programmed and whether the board state changed.

## Protected and external content

- Never commit commercial Game Boy ROMs, Nintendo boot ROMs, or save data.
- Treat user ROM paths and hashes as private runtime inputs.
- Pin external tests and tools to a version or commit.
- Record license and provenance before copying reference code.
- Use `frog-bui` for process ideas only until its reuse terms are resolved.

## Writing style

- Use plain language and short sentences.
- State observable behavior.
- Prefer a small table over repeated prose.
- Keep issues and PRs focused.
- Put history in issues and PRs, not in specifications.
- Remove stale instructions instead of adding exceptions around them.

## Skills

Use a focused skill when one exists. Planned initial skills are:

- `issue-author`
- `pr-author`
- `rtl-coder`
- `dv-uvm-lite`
- `fpga-de10-lite`
- `wiki-spec-writer`
- `build-maintainer`
- `uart-host-tool`

Each skill should define its trigger, inputs, method, outputs, validation, one
good example, one bad example, and stop conditions. Keep detailed procedures in
the skill rather than this file.
