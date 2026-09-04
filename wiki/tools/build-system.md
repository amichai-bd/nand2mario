# Build system

Status: draft design; structure agreed; not implemented

## Purpose

The build system gives agents and people one predictable command. It creates
tagged workspaces, reuses valid results, and records evidence.

The planned entry point is:

```text
python tools/build.py <command> [options]
```

`tools/build.py` is a thin dispatcher. Command logic belongs in small modules
under `tools/n2m/`.

## Source and workspace boundary

- Root `tools/` contains checked-in project automation.
- `workdir/tools/` contains downloaded or provisioned external tools.
- `workdir/cache/` contains reusable downloads and immutable cached data.
- `workdir/builds/` contains tagged build state and results.
- `workdir/logs/` contains bootstrap and doctor logs that have no build tag.

Build-specific generated scripts belong inside their tagged build. This keeps
the command, inputs, and results together.

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
its owner. Examples include regression definitions under `src/dv/` and board
constraints under `src/fpga/de10_lite/`.

## Build tags

An explicit tag creates or reopens a persistent build workspace:

```text
python tools/build.py sim test timer-overflow --tag timer-dev
```

If `timer-dev` exists, valid stages are reused. Stale stages and their dependent
stages are rebuilt.

Without `--tag`, the build uses a UTC timestamp:

```text
20260904T142311Z
```

If that name already exists, append a short numeric suffix. A build tag is a
directory name, not a Git tag.

Tags must be lowercase, filesystem-safe, and no longer than 48 characters.
Allowed characters are letters, numbers, `.`, `_`, and `-`.

## Cache rules

A directory name is not proof that a result is valid. Each stage has a content
fingerprint containing:

- source input hashes;
- direct dependency result hashes;
- consumed configuration hashes;
- tool name and version;
- command options; and
- test seed when applicable.

The result is reused only when the fingerprint matches and the prior stage
completed successfully.

- A cache hit reports `CACHED`.
- A changed input rebuilds that stage and dependent stages.
- A failed or interrupted stage is never reused.
- `--rebuild` bypasses reuse for the selected stage.
- A per-tag lock prevents concurrent writers.
- A stale stage is replaced atomically after the new stage completes.

Named tags support fast iteration. Timestamp tags preserve isolated run history.
Different tags may share downloaded tools and immutable cache content, but not
mutable stage directories.

`workdir/latest.txt` identifies the latest successful build. It is updated only
after the requested command succeeds.

## Tagged build layout

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

Compilation is separated by simulator so incompatible libraries cannot collide.
FPGA output stays separate because Quartus compilation, fitting, timing, and
image generation form their own flow.

Use `sw/`, not `sw-collateral`. The output names have clear meanings:

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

Each test directory contains:

```text
result.json
sim.log
waves/
coverage/
```

If a test runs several seeds, use `seed-<number>/` below the test name. The
level directory contains an aggregate `summary.json`. The full regression also
produces `summary.json` and `junit.xml`.

Regression membership and level meaning will be defined with the verification
sources under `src/dv/`. Directory placement is output, not the source of the
regression definition.

## Manifest

`manifest.json` records enough information to explain and repeat a result:

- build tag and creation time;
- Git commit and dirty-tree fingerprint;
- host and tool versions;
- requested command and options;
- configuration and input hashes;
- completed stages and cache decisions; and
- paths to logs, reports, images, and test summaries.

Do not record credentials, commercial ROM paths, or private ROM hashes in a
committed file. Build manifests remain ignored under `workdir/`.

## Cleanup

Timestamp builds can consume significant disk space. Cleanup must be explicit:

```text
python tools/build.py builds list
python tools/build.py builds inspect <tag>
python tools/build.py builds clean <tag>
python tools/build.py builds prune --keep 10
```

Cleanup resolves and validates the exact path under `workdir/builds/` before
removal. It never removes checked-in tools or source files.
