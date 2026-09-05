# Tile pixel simulation

`tools/sim/tile_pixel.py` runs only the [tile pixel contract](../src/display/tile-pixel.md).
The [product builder](build-system.md) currently runs separate smoke targets;
this tile target still uses its standalone runner, including Questa support.
Python 3.12 or later and the selected simulator must be on `PATH`:

```powershell
python tools/sim/tile_pixel.py --sim questa --tag tile-questa
python tools/sim/tile_pixel.py --sim icarus --tag tile-icarus
```

Questa uses `vlib`, `vmap`, `vlog`, and `vsim` with a valid simulation license.
Icarus uses `iverilog` and `vvp`. CI builds Icarus 12.0 from the pinned source
listed in [tool provenance](../../tools/sim/THIRD_PARTY.md). Questa remains a
local check; hosted CI requires no proprietary license.

Each invocation reserves a fresh `workdir/builds/<tag>/`. An existing tag is
rejected, preventing stale reuse and concurrent writes. Without a tag, use
the UTC timestamp. This runner has no cache or cleanup command. It launches
argument lists without a shell, so checkout paths may contain spaces.

The manifest records source/runner hashes, Git commit and dirty status, exact
commands, exit codes, and log paths. Compiler banners record tool versions.
Compile artifacts and simulator libraries stay separate from normal and
deliberately corrupt simulation runs. Each successful case writes its result
and VCD; the corrupt case succeeds only as an expected checker failure.
Missing tools, compilation/elaboration errors, warnings, timeouts, unexpected
exit status, or missing expected output make the runner fail.

When WSL operates on a Windows-created Git worktree, set `GIT_DIR` and
`GIT_WORK_TREE` to their WSL paths for that invocation; Git cannot interpret
the Windows path in its `.git` file. This is environment setup, not a simulator
or source difference.

The [workflow](../../.github/workflows/tile-pixel.yml) runs on pull requests and
pushes to `main`, preserving logs and traces even on failure. This unit check
does not close the [global verification or trusted-CI gaps](../preflight-gaps.md).
