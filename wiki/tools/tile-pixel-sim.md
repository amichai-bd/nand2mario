# Tile pixel simulation

The [product builder](build-system.md) runs the portable checks for the
[tile pixel contract](../src/display/tile-pixel.md):

```powershell
python tools/build.py sim test tile-pixel --tag tile-pixel --json
python tools/build.py sim test tile-pixel-corrupt --tag tile-corrupt --json
```

The [target registry](../../src/dv/builder/targets.json) requires a zero simulator
exit and exhaustive PASS counts for `tile-pixel`. The separate corrupt target
requires a nonzero simulator exit and the exact cycle, phase, expected/actual,
and input diagnostic. Its builder result is PASS only when that intended failure
is detected. It cannot replace the mandatory normal target.

Repeat either command to reuse a matching successful result (`CACHED`); use
`--rebuild` to rerun. Changed inputs or damaged artifacts invalidate reuse.
The builder records tools, input hashes, commands, exit codes, results, and
waves beneath `workdir/builds/<tag>/`. It handles native Icarus or Windows-to-WSL
execution. Its seed is recorded for cache identity; this test is deterministic
and reports `seed=none`.

## Questa and standalone checks

Questa remains a required independent local check. With Python 3.12 or later,
`vlib`, `vmap`, `vlog`, and `vsim` on `PATH`, and a valid simulation license:

```powershell
python tools/sim/tile_pixel.py --sim questa --tag tile-questa
```

This standalone runner checks normal and deliberately corrupt cases together.
It records hashes, commit/dirty status, commands, tool banners, logs, and VCDs
under a fresh tag; existing tags are rejected and results are never cached.
It also supports `--sim icarus` for direct comparison. Running that mode from
WSL inside a Windows-created worktree requires WSL `GIT_DIR`/`GIT_WORK_TREE`
paths. The builder's Windows-to-WSL mode needs no such Git override.

Both paths reject tool, compile, elaboration, warning, timeout, exit, or expected
output failures. Neither portable success nor command-construction tests waive
the licensed Questa compile/elaborate/run requirement.

The [workflow](../../.github/workflows/tile-pixel.yml) runs on pull requests and
pushes to `main`, using the shared [pinned bootstrap](build-system.md#bootstrap)
and builder targets. It checks both results and cache reuse and preserves logs
and traces even on failure. See [tool provenance](../../tools/sim/THIRD_PARTY.md).
This unit check
does not close the [global verification or trusted-CI gaps](../preflight-gaps.md).
