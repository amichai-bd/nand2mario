# nand2mario

A planned recreation of the original monochrome Game Boy on the DE10-Lite.
The goal is VGA video and game controls sent from a host CLI over UART.

The agent tooling and repository scaffold are in place. Game Boy implementation
has not started. [Preflight gaps](wiki/preflight-gaps.md) track what must come first.

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
Hosted CI checks host contracts; licensed simulation currently requires local
evidence. The [CI boundary](wiki/tools/n2m/SPEC.md#ci-execution-boundary) tracks
the trusted remote route still due in #32.

The repository is private; the documentation site is public and deploys after
merge to `main`. Do not commit commercial ROMs, saves, or credentials. A project
reuse grant is withheld under the [source and provenance policy](wiki/tools/provenance.md).
