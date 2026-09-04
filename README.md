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

The GitHub repository is private. Issue forms and labels are configured. CI,
Pages deployment, and branch rules are not configured yet.

## Planned layout

- `src/` — RTL, verification, target software, and FPGA files.
- `cfg/` — small, project-wide YAML configuration only.
- `tools/` — checked-in build, automation, and maintenance code.
- `wiki/` — short documentation mirroring source, tools, and agent work.
- `.agents/skills/` — focused procedures for recurring agent tasks.
- `.github/` — issue forms, labels, PR templates, and workflows.
- `workdir/` — downloaded tools, generated scripts, tagged builds, and logs.

Generated files will live under ignored `workdir/` and will not be committed.

The tagged build layout is defined in the
[build-system specification](wiki/tools/build-system.md).

## Content policy

Do not commit commercial ROMs, Nintendo boot ROMs, save files, generated FPGA
images, or copied reference-project code without a compatible license and a
recorded provenance decision.

No project license has been selected yet. See
[GAP-002](wiki/preflight-gaps.md#gap-002--license-rom-policy-and-provenance).
