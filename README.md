# nand2mario

A verified, bounded original-DMG-compatible system on the DE10-Lite, with VGA
and shared UART/physical input. The current goal is
[Springtrail](wiki/src/sw/springtrail/SPEC.md), our own planned silent platformer
with original SM83 code, characters, art and level design.

The original [v0.5 hardware/software proof](https://github.com/amichai-bd/nand2mario/pull/246)
is complete within its stated limits; Springtrail is not implemented yet.
The [charter](wiki/src/project-charter.md) defines the revised goal and preserved
release checks. [Preflight gaps](wiki/preflight-gaps.md) retain outstanding
physical and integration requirements. No commercial cartridge is needed.

- [Documentation](https://amichai-bd.github.io/nand2mario/)
- [Open issues](https://github.com/amichai-bd/nand2mario/issues)
- [Research](wiki/research-findings.md)
- [Agent rules](AGENTS.md)

## Repository layout

- `src/`: RTL, verification, software, and FPGA projects.
- `wiki/`: specifications, decisions, and tool guidance.
- `.agents/skills/`: agent methods, examples, and templates.
- `.github/`: issue forms, PR template, labels, and workflows.
- `cfg/`: small project configuration.
- `tools/`: checked-in host scripts and automation.
- `worktrees/`: isolated issue checkouts.
- `workdir/`: local tools, temporary drafts, builds, and logs.

Questa is the sole supported simulator. See the
[build specification](wiki/tools/n2m/SPEC.md) for commands and output layout.
The builder accepts existing SV targets and separate
[Python testbenches](src/dv/python/README.md), beginning with the joypad owner.
Hosted CI checks host contracts; licensed simulation currently requires local
evidence. The [CI boundary](wiki/tools/n2m/SPEC.md#ci-execution-boundary) tracks
the trusted remote route still due in #32.

The repository is private; the documentation site is public and deploys after
merge to `main`. Do not commit commercial ROMs, saves, or credentials. A project
reuse grant is withheld under the [source and provenance policy](wiki/tools/provenance.md).
