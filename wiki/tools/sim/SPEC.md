# Tile pixel simulation

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
waves beneath `workdir/builds/<tag>/`. It handles native Icarus, Windows-to-WSL
Icarus, and explicitly selected native Questa. Its seed is recorded for cache
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

The [GAP-008 decision](../../preflight-gaps.md#gap-008-verification-baseline) records
the scoped tile/doctor licensed evidence and remaining general Questa deferral.
For an authorized run, use Python 3.12 or later,
`vlib`, `vmap`, `vlog`, and `vsim` on `PATH`, and a valid simulation license:

```powershell
python tools/sim/tile_pixel.py --sim questa --tag tile-questa
```

This standalone runner checks normal and deliberately corrupt cases together.
It records hashes, commit/dirty status, commands, tool banners, logs, and VCDs
under a fresh tag; existing tags are rejected and results are never cached.
Each Questa case retains a `run.do` macro. Its handlers run with `-onfinish stop`
and inspect the simulator's stop reason: normal `$finish` exits zero; fatal,
other breaks, macro errors, or return without `$finish` exit nonzero. The normal
case requires the full exhaustive completion signature. Corruption requires
the full intended mismatch diagnostic and a nonzero exit; additional errors
or warnings fail the runner even when an expected signature appears.
It also supports `--sim icarus` for direct comparison. Running that mode from
WSL inside a Windows-created worktree requires WSL `GIT_DIR`/`GIT_WORK_TREE`
paths. The builder's Windows-to-WSL mode needs no such Git override.

Both paths reject tool, compile, elaboration, warning, timeout, exit, or expected
output failures. Portable success and command-construction tests do not prove
Questa execution. The gap register distinguishes established runtime evidence
from the broader verification baseline still due in #31.

The [workflow](../../../.github/workflows/tile-pixel.yml) runs on pull requests and
pushes to `main`, using the shared [pinned bootstrap](../n2m/SPEC.md#bootstrap)
and builder targets. It checks both results and cache reuse and preserves logs
and traces even on failure. See [tool provenance](../../../tools/sim/THIRD_PARTY.md).
This unit check
does not close the [global verification or trusted-CI gaps](../../preflight-gaps.md).
