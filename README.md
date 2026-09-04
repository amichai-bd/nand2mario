# nand2mario

`nand2mario` is a planned FPGA recreation of the original monochrome Game Boy
for the Terasic DE10-Lite.

The intended system will:

- implement the Game Boy SM83 CPU and supporting hardware in SystemVerilog;
- load a user-supplied cartridge image through UART;
- display the Game Boy picture through the board's VGA output;
- accept Game Boy controls from a host CLI through UART; and
- use simulation, open test ROMs, formal checks, and hardware tests as evidence.

## Status

Research is complete. Functional RTL and build tooling have not started.

Read these documents before implementation:

- [Research findings](wiki/research-findings.md)
- [Gaps before implementation](wiki/preflight-gaps.md)
- [Project documentation index](wiki/index.md)
- [Agent working rules](AGENTS.md)

The GitHub repository is private. Issue forms, labels, the PR policy check, and
`main` protection are active. Build CI and Pages are not configured yet.

## Repository layout

- `src/rtl/` — synthesizable SystemVerilog.
- `src/dv/` — testbenches, assertions, and verification data.
- `src/sw/` — target software and test ROM sources.
- `src/fpga/de10_lite/` — DE10-Lite projects and constraints.
- `cfg/` — small, project-wide YAML configuration only.
- `tools/automations/` — checked-in CI and repository automation support.
- `tools/scripts/` — checked-in developer and maintenance scripts.
- `wiki/src/` — hardware and software specifications.
- `wiki/tools/` — tool and build specifications.
- `wiki/agents/` — agent workflow guidance.
- `.agents/skills/` — focused procedures for recurring agent tasks.
- `.github/` — issue forms, labels, PR templates, and workflows.
- `worktrees/` — ignored issue checkouts plus a tracked lifecycle guide.
- `workdir/` — downloaded tools, generated scripts, tagged builds, and logs.

`worktrees/` isolates source changes. `workdir/` contains disposable output
inside each checkout. Neither child worktrees nor generated files are committed.

The tagged build layout is defined in the
[build-system specification](wiki/tools/build-system.md).

## Content policy

Do not commit commercial ROMs, Nintendo boot ROMs, save files, generated FPGA
images, or copied reference-project code without a compatible license and a
recorded provenance decision.

No project license has been selected yet. See
[GAP-002](wiki/preflight-gaps.md#gap-002--license-rom-policy-and-provenance).
