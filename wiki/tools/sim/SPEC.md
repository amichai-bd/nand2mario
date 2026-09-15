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
waves beneath `workdir/builds/<tag>/`. Its seed is recorded for cache
identity; this test is deterministic and reports `seed=none`.

## Simulator

The builder runs [Verilator on WSL](../n2m/SPEC.md#verilator-simulation). Both
tile targets are registered `simulator: "verilator"`: `tile-pixel` passes with
its exhaustive signature and `tile-pixel-corrupt` fails with its exact mismatch
diagnostic. The testbench drives two-state fill values where its earlier
stimulus drove X and Z; the checks are unchanged.

## Standalone checks

Follow the [current authorization](../../agents/bootstrap-plan.md#verification-and-hardware-authorization).
Use Python 3.12 or later and the pinned Verilator on `PATH`, or name its tool
directory:

```bash
python3 tools/sim/tile_pixel.py --tag tile-standalone
python3 tools/sim/tile_pixel.py --verilator-bin <prefix>/bin --tag tile-standalone
```

This standalone runner checks normal and deliberately corrupt cases together.
It resolves and hashes transitive headers under the shared
[include contract](../n2m/SPEC.md#hdl-includes). Missing or unsupported includes
retain a failure manifest before tools run. It records commit/dirty status,
the Verilator and C++ compiler identities from the
[shared discovery](../n2m/SPEC.md#verilator-simulation), commands, logs, the
harness FST and the testbench VCD under a fresh tag; existing tags are rejected
and results are never cached. It builds the
[shared runner's command plan](../../../tools/n2m/verilator.py) once under
`compile/verilator/` and runs each case from `sim/test/tile-pixel/<case>/`
with the runner's seeded plusargs; the testbench itself is deterministic and
the manifest records the randomization seed separately from its `seed=none`.
Transcripts pass the runner's strict check: any `%Warning` fails, and an error
line must carry the expected mismatch. The normal case requires the full
exhaustive completion signature and a zero exit. Corruption requires the full
intended mismatch diagnostic and a nonzero exit; additional errors or warnings
fail the runner even when an expected signature appears. The runner accepts
only `--sim verilator`; retired selections such as `questa` fail argument
parsing, and there is no fallback.

Both paths reject tool, compile, elaboration, warning, timeout, exit, or expected
output failures. Host command-construction tests do not prove simulator execution. The
[baseline contract](../../src/dv/baseline/SPEC.md) owns broader verification.

The [workflow](../../../.github/workflows/tile-pixel.yml) runs standalone host
contracts by dispatch; authors run the same command
[locally before merge](../../agents/pull-requests.md#hosted-and-local-checks).
Its check is named `Tile runner checks`; it does not claim RTL execution. Actual local positive/corrupt simulator
evidence remains required. The [trusted CI boundary](../n2m/SPEC.md#ci-execution-boundary)
records the [out-of-scope trusted route](../../preflight-gaps.md#gap-010-github-remote-issues-ci-and-pages). See
[tool provenance](../../../tools/sim/THIRD_PARTY.md).
