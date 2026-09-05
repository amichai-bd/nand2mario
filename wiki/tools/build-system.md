# Build system

Status: `doctor`, `check`, and Icarus `sim test` implemented; other stages planned.

## Purpose

The build system gives agents and people one predictable command to create
tagged workspaces, reuse valid results, and record evidence.

The entry point is:

```text
python tools/build.py <command> [options]
```

`tools/build.py` is a thin dispatcher. Command logic belongs in small modules
under `tools/n2m/`.

## Available commands

```powershell
python tools/build.py doctor --json
python tools/build.py check --tag builder-check --json
python tools/build.py sim test builder-smoke --tag smoke --seed 1 --json
python tools/build.py sim test builder-smoke --tag smoke --json
python tools/build.py sim test builder-smoke-fail --tag deliberate-failure --json
```

The second identical simulation reports `CACHED`. The deliberate-failure target
must exit 1 and retain its mismatch log and waveform. Other successful commands
exit 0; errors exit nonzero. `--json` emits one result object on stdout.

`doctor` identifies Icarus compiler/runtime versions; it does not prove a license,
simulation, or hardware connection. `sim test` proves compile, elaboration, run,
and the target's expected signature. `check` runs builder contract tests with
controlled executor doubles; these are not RTL evidence. Neither command touches
hardware. The broader doctor remains [#27](https://github.com/amichai-bd/nand2mario/issues/27).

Native Icarus on PATH is preferred; Windows otherwise tries the default WSL
distribution. Select `--sim icarus` or `--sim wsl-icarus` explicitly. Use
`--wsl-distro <name>` to select a distribution and `--iverilog <path>` / `--vvp
<path>` to override executables in that environment. WSL paths are Linux paths;
source/output paths are translated automatically. Paths with spaces are supported.
Missing tools fail with diagnostics; there is no silent simulator fallback after
an explicitly selected tool fails. Questa is not a backend yet.

## Bootstrap

The [dependency definition](../../tools/n2m/dependencies.json) pins Python and
Icarus source, provenance, and licenses. No Python packages or virtual environment
are required. Install Python 3.14.5 for the supported host environment. Linux/WSL
source-build prerequisites are Git, a C/C++ toolchain, Make, autoconf, bison, flex,
and gperf. On Ubuntu 24.04:

```sh
sudo apt-get update
sudo apt-get install -y git build-essential autoconf bison flex gperf
python3 tools/n2m/bootstrap.py
```

Run these inside the checkout in WSL, then from fresh PowerShell:

```powershell
python tools/build.py doctor --sim wsl-icarus --iverilog ./workdir/tools/iverilog/bin/iverilog --vvp ./workdir/tools/iverilog/bin/vvp --json
```

Executable overrides are resolved before entering the tagged output directories.
Native Linux uses the same bootstrap and overrides.
CI calls the same script and source pin. Host package versions depend on the OS;
they are build prerequisites, not a hermetic host image. An existing PATH tool is
allowed and its actual version/path is recorded; that is not proof it matches
the pinned source. No reference HDL or Game Boy assets are imported.

## First simulation target

`src/dv/builder/targets.json` defines sources, top module, plusargs, expected exit
class (`zero` or `nonzero`), and nonempty required output signature. The original smoke
fixture checks synchronous reset, counting through 4-bit wrap, and reset again:
22 comparisons on falling edges after rising-edge register updates. Its failure
variant injects expected=7 at cycle 3, where actual=3. Seed is recorded and passed
to the testbench; this directed fixture does not use randomness. A 1 us watchdog
and 60 s host command timeout bound execution. Partial timeout output is retained
in the failing command's log. Simulator warnings fail the stage.

Add simulation targets to this manifest when their contracts and tests are ready.
The [tile pixel checks](tile-pixel-sim.md) use this interface for normal and
expected-corruption runs; their Questa check remains separate.
Future software and FPGA commands should have separate modules under `tools/n2m/`
and the output boundaries below. They are not implemented by this issue.

## Source and workspace boundary

- Root `tools/` contains checked-in project automation.
- `workdir/tools/` contains downloaded or provisioned external tools.
- `workdir/cache/` contains reusable downloads and immutable cached data.
- `workdir/builds/` contains tagged build state and results.
- `workdir/logs/` contains bootstrap and doctor logs that have no build tag.

Keep generated build-specific scripts inside their tagged build alongside
commands, inputs, and results.

`workdir/` is ignored and disposable. It must never contain the only copy of
source, configuration, or documentation.

## Repository layout

```text
.agents/skills/       Agent methods
.github/              GitHub templates and workflow entry points
cfg/                  Small, project-wide YAML configuration
src/rtl/              Synthesizable RTL
src/dv/               Verification and regression definitions
src/sw/               Target software and ROM sources
src/fpga/             Board projects and constraints
tools/                 Checked-in build and automation code
wiki/src/              Source-design documentation
wiki/tools/            Tool documentation
wiki/agents/           Agent documentation
workdir/               Ignored tools, cache, builds, and logs
```

Do not create speculative configuration trees. Keep owner-specific input near
its owner. For example, put regression definitions under `src/dv/` and board
constraints under `src/fpga/de10_lite/`.

## Build tags

An explicit tag creates or reopens a persistent build workspace:

```text
python tools/build.py sim test builder-smoke --tag smoke-dev
```

If `smoke-dev` exists, reuse valid stages; rebuild stale stages and their
dependents.

Without `--tag`, the build uses a UTC timestamp:

```text
20260904t142311z
```

If the name exists, append a short numeric suffix. A build tag is a
directory name, not a Git tag.

Tags must be lowercase, filesystem-safe, and at most 48 characters.
Allowed characters are letters, numbers, `.`, `_`, and `-`. Start with a letter
or number; trailing dots and Windows device names are rejected. UTC `t` and `z`
are lowercase to satisfy the same rule as explicit tags.

## Cache rules

Directory names do not prove validity. Each stage has a content fingerprint
containing:

- source input hashes;
- direct dependency result hashes;
- consumed configuration hashes;
- tool name and version;
- command options; and
- test seed when applicable.

Reuse results only when the fingerprint matches and the prior stage succeeded.

- A cache hit reports `CACHED`.
- A changed input rebuilds that stage and dependent stages.
- A failed or interrupted stage is never reused.
- `--rebuild` bypasses reuse for the selected stage.
- A per-tag lock prevents concurrent writers.
- A stale stage is replaced atomically after the new stage completes.

The first backend treats compilation and simulation as one stage: any source,
runner module, dependency definition, target configuration, seed, or discovered
tool identity change rebuilds both. Artifact hashes are also checked before reuse.
`check` and `doctor` always rerun. A lock left by an interrupted process requires
confirming that writer stopped before manually removing the tagged `.lock` file.
There is no age-based lock stealing.

Named tags support fast iteration. Timestamp tags preserve isolated run history.
Different tags may share downloaded tools and immutable cache content, but not
mutable stage directories.

`workdir/latest.txt` identifies the latest successful build. It is updated only
after the requested command succeeds.

## Output layout

Implemented commands create only their needed directories. The larger layout
below reserves locations for planned regression, FPGA, and software stages.

```text
workdir/builds/<tag>/
├── manifest.json
├── status.json
├── commands.log
├── scripts/
├── compile/
│   ├── questa/
│   ├── verilator/
│   └── iverilog/
├── sim/
│   ├── test/
│   │   └── <test-name>/
│   └── regress/
│       ├── summary.json
│       ├── junit.xml
│       ├── level0/
│       │   ├── summary.json
│       │   └── <test-name>/
│       └── level1/
│           ├── summary.json
│           └── <test-name>/
├── fpga/
│   ├── quartus/
│   ├── reports/
│   └── images/
└── sw/
    └── <image-name>/
        ├── obj/
        ├── image.gb
        ├── image.map
        ├── image.sym
        └── image.lst
```

Separate compilation by simulator to prevent incompatible library collisions.
FPGA output stays separate because Quartus compilation, fitting, timing, and
image generation form their own flow.

Use `sw/`, not `sw-collateral`:

- `obj/` contains intermediate object files.
- `image.gb` is the final cartridge image.
- `image.map` is the linker memory map.
- `image.sym` contains exported symbols.
- `image.lst` is the compiler or assembler listing.

## Simulation results

An explicitly selected test writes to:

```text
workdir/builds/<tag>/sim/test/<test-name>/
```

A regression test writes to:

```text
workdir/builds/<tag>/sim/regress/level0/<test-name>/
```

The implemented simulation stage publishes `result.json` atomically. It records
status, fingerprint, provenance, commands, and hashes of immutable artifacts under
`attempts/<id>/` and `compile/iverilog/<test-name>/<id>/`. A new attempt never
modifies an old attempt. `sim.log` beside `result.json` is a convenience copy;
the record's hashed paths are authoritative. Each attempt contains `sim.log`,
`result.json`, `waves/`, and `coverage/` (empty until coverage is implemented).

Before execution, the published record becomes `RUNNING`, preventing reuse after
interruption. Completion publishes `PASS` or `FAIL`; a failed forced rebuild
invalidates the earlier success for that stage and preserves both attempts.
Discovery or preparation failure also invalidates that target's prior success.
`manifest.json` and `status.json` describe the latest command on the tag. The
latest pointer changes only after command success; it records the last successful
invocation's tag, whose later contents may change when explicitly reused.

Planned regression layout:

For multiple test seeds, use `seed-<number>/` below the test name. The
level directory contains an aggregate `summary.json`. The full regression also
produces `summary.json` and `junit.xml`.

Verification sources under `src/dv/` will define regression membership and
levels. Directory placement reflects output; it does not define regressions.

## Manifest

`manifest.json` records evidence to explain and reproduce a result:

- build tag and creation time;
- Git commit and dirty-tree fingerprint;
- host and tool versions;
- requested command and options;
- configuration and input hashes;
- completed stages and cache decisions; and
- paths to logs, reports, images, and test summaries.

Do not record credentials, commercial ROM paths, or private ROM hashes in a
committed file. Build manifests remain ignored under `workdir/`.

## Planned cleanup

Timestamp builds can consume significant disk space. These cleanup commands
are planned; the current CLI rejects them:

```text
python tools/build.py builds list
python tools/build.py builds inspect <tag>
python tools/build.py builds clean <tag>
python tools/build.py builds prune --keep 10
```

Cleanup resolves and validates the exact path under `workdir/builds/` before
removal. It never removes checked-in tools or source files.
