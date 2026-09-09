# Tile pixel simulation

Purpose and scope: [PRD](PRD.md).

The [product builder](../n2m/SPEC.md) runs the registered checks for the
[tile pixel contract](../../src/rtl/display/MAS_display.md):

```powershell
python tools/build.py sim test tile-pixel --tag tile-pixel --json
python tools/build.py sim test tile-pixel-corrupt --tag tile-corrupt --json
```

The [target registry](../../../src/dv/builder/targets.json) requires a zero simulator
exit and exhaustive PASS counts for `tile-pixel`. The separate corrupt target
requires a nonzero simulator exit and the exact cycle, phase, expected/actual,
and input diagnostic. Its builder result is PASS only when that intended failure
is detected. It cannot replace the mandatory normal target.

Repeat either command to reuse a matching successful result (`CACHED`); use
`--rebuild` to rerun. Changed inputs or damaged artifacts invalidate reuse.
The builder records tools, input hashes, commands, exit codes, results, and
waves beneath `workdir/builds/<tag>/`. It uses Questa by default. Its seed is recorded for cache
identity; this test is deterministic and reports `seed=none`.

## Questa checks

Use the shared builder with the same normal and corruption targets:

```powershell
python tools/build.py sim test tile-pixel --sim questa --tag tile-questa --json
python tools/build.py sim test tile-pixel-corrupt --sim questa --tag tile-questa-corrupt --json
```

The [Questa backend contract](../n2m/SPEC.md#questa-simulation) owns discovery,
isolated libraries, strict diagnostics, and cache behavior. Add `--questa-bin
<directory>` for explicit discovery; use `--rebuild` for fresh runtime evidence.

## Standalone checks

Follow the [current authorization](../../agents/bootstrap-plan.md#verification-and-hardware-authorization).
Use Python 3.12 or later,
`vlib`, `vmap`, `vlog`, and `vsim` on `PATH`, and a valid simulation license:

```powershell
python tools/sim/tile_pixel.py --sim questa --tag tile-questa
```

This standalone runner checks normal and deliberately corrupt cases together.
It resolves and hashes transitive headers under the shared
[include contract](../n2m/SPEC.md#hdl-includes). Missing or unsupported includes
retain a failure manifest before tools run. It records commit/dirty status,
commands, tool banners, logs, and VCDs
under a fresh tag; existing tags are rejected and results are never cached.
Each Questa case retains a `run.do` macro. Its handlers run with `-onfinish stop`
and inspect the simulator's stop reason: normal `$finish` exits zero; fatal,
other breaks, macro errors, or return without `$finish` exit nonzero. The normal
case requires the full exhaustive completion signature. Corruption requires
the full intended mismatch diagnostic and a nonzero exit; additional errors
or warnings fail the runner even when an expected signature appears.
Questa is the default and only supported backend. Retired simulator selections
fail argument parsing; there is no fallback.

Both paths reject tool, compile, elaboration, warning, timeout, exit, or expected
output failures. Host command-construction tests do not prove Questa execution. The
[baseline contract](../../src/dv/baseline/SPEC.md) owns broader verification.

The [workflow](../../../.github/workflows/tile-pixel.yml) runs standalone host
contracts on pull requests and main. Its check is named `Tile runner checks`;
it does not claim licensed RTL execution. Actual local positive/corrupt Questa
evidence remains required. The [trusted CI boundary](../n2m/SPEC.md#ci-execution-boundary)
records the [open trusted-route activation gap](https://github.com/amichai-bd/nand2mario/issues/32). See
[tool provenance](../../../tools/sim/THIRD_PARTY.md).
