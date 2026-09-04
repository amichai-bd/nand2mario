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

The current repository is intentionally local. It has no GitHub remote, CI,
Pages deployment, or issue tracker yet.

## Planned layout

- `src/` — RTL, verification, FPGA files, software, and project tools.
- `wiki/` — architecture, specifications, decisions, verification plans, and
  development guidance.
- `.agents/skills/` — focused procedures for recurring agent tasks.
- `.github/` — issue templates, PR template, and workflows after a remote is
  approved.

Generated files will live under `.work/` and will not be committed.

## Content policy

Do not commit commercial ROMs, Nintendo boot ROMs, save files, generated FPGA
images, or copied reference-project code without a compatible license and a
recorded provenance decision.

No project license has been selected yet. See
[GAP-002](wiki/preflight-gaps.md#gap-002--license-rom-policy-and-provenance).
