# Agent rules

## Goal

Build a verified, original-DMG-compatible Game Boy for the DE10-Lite. It must
display through VGA and accept controls through UART.

## Current phase

Research is complete. Read `wiki/preflight-gaps.md` before implementation.
Until the blockers are closed, do only bootstrap work requested by the user.

The GitHub repository is private. Do not change visibility, publish pages, or
program the FPGA without explicit approval.

## Sources of truth

- The issue defines the goal and acceptance criteria.
- The wiki defines behavior and decisions.
- A skill defines a recurring method.
- `src/` contains the product and its verification.
- Tests and build artifacts provide evidence.

Keep each fact in one place. Link to it elsewhere.

## Style

- Use plain words and short sentences.
- Lead with the result, evidence, or decision.
- Write small modules with direct names and explicit behavior.
- Comments explain intent, timing, or risk. They do not repeat code.
- Avoid clever abstractions, speculative features, and unrelated cleanup.
- Match nearby code and documents unless the issue changes the convention.

## Work

- One issue, one observable result, one short-lived branch.
- Read the issue and linked specification before editing.
- Keep changes inside the acceptance criteria.
- Update specification, implementation, and tests together when behavior
  changes.
- Record exact commands and results. Do not claim a planned command passed.
- Keep generated output under `workdir/`.

## Verification

- Run the smallest test that proves the change, then required lower-level
  checks.
- A simulation must compile, elaborate, run, and check an expected result.
- Treat unexplained warnings as failures.
- Preserve useful logs, seeds, traces, waves, and reports under the build tag.

## Safety and external content

- Verify the USB-Blaster, device, voltage, and wiring before hardware use.
- Keep programming and physical tests explicit and serialized.
- Never commit commercial ROMs, Nintendo boot ROMs, saves, or credentials.
- Pin external code, test suites, and tools. Record licenses and provenance.
- Use `frog-bui` for process ideas only until reuse terms are clear.

## Skills

Use a focused repository skill when one exists. Keep procedures, examples, and
tool-specific detail in the skill, not here.
