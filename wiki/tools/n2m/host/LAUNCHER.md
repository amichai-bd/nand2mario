# Game launcher

Pick a game from a list, watch it load, and play it. `python tools/gb_launcher.py`
opens one window that lists every game this board can run, loads the one you
choose, resets it, runs it, and hands over to the [on-screen pad](GAMEPAD.md) in
the same window and the same UART session. It reads no frames and serves no
HTTP: the player watches the board's own VGA output, and the window is the
control surface. The [host contract](SPEC.md) owns UART, session, load and input
semantics; this page owns how a game is chosen and started.

It is a separate command rather than another flag on `fpga_viewer.py`, because
that tool deliberately never loads, resets or programs the board. The launcher
does all three.

## Run it

Verify the [board setup](../../../src/board-bring-up.md), the selected healthy
UART endpoint, wiring and voltage first. The board must be taking UART input with
effective input 0. No image needs to be loaded: loading one is what the launcher
is for.

```powershell
$Port = '<selected UART port>'
$Build = '<reviewed 32-digit lowercase wire build ID>'
python tools/gb_launcher.py --expected-build-id $Build --uart-port $Port
```

`--uart-vid`, `--uart-pid` and `--uart-identity` narrow the selection the same
way they do for every host command; exactly one healthy device must match.
Omitting `--tag` creates one unique tag; the startup line reports the tag, the
lease and the directory holding the run's `result.json` and packet journal.
`--seconds` sets the session lease, 900 seconds by default and at most 3600, and
covers the whole window: menu, loads and play alike.

## The menu

Two sections, both read from the manifests that already hold these facts, so
nothing about a game is retyped in the launcher's source and the window cannot
drift from the pins.

**Built from source in this repository** lists the targets in
[`src/sw/targets.json`](../../../../src/sw/targets.json) the launcher offers:
Stackdrop and Springtrail. Each card shows the cartridge title from the target
registry. No author or licence line is shown for these, because the registry
records neither and the launcher invents nothing; the section heading says where
they come from.

**Other people's games** lists every image pinned in
[`tools/n2m/dependencies.json`](../../../../tools/n2m/dependencies.json), in
manifest order. Each card shows the pinned name and, beneath it, the author and
the SPDX licence exactly as the manifest records them. The heading states that
these are pinned by digest, fetched at run time and stay under their own terms;
the [homebrew library](../../../showcase/homebrew-library.md) holds the full
attribution and the captured evidence.

**Wyrmhole and Rex Run are listed**, marked `⚠ does not boot`, with the one-line
reason — they wait for the LCD before enabling it, so they never draw, because
`dmg-direct-v1` has no boot ROM and starts with the LCD off — and a link to
[where that is explained](../../../showcase/homebrew-library.md#wyrmhole-and-rex-run-never-turn-the-lcd-on).
Hiding them would hide a real finding at exactly the moment a player would meet
it. They sort to the end of their section, because they are listed to be honest
about the limit and not as somewhere to start.

## Choosing a game

One flow, the way a console behaves: load, reset, run, play. Selecting a card
replaces whatever was loaded. That is ordinary session state and needs no
confirmation, but a load takes seconds, so the window shows each step as it
happens — building, fetching and verifying, sending and verifying the readback,
resetting, starting — rather than sitting silent.

A third-party game is fetched and verified against its pinned SHA-256 through
the same `host load --external` reader; a locally cached copy is verified again
on read. A game built from source is built through the ordinary
`python tools/build.py sw build <target>`, then loaded from the immutable
`runs/<attempt>/result.json` that build published, through the same
`host load --package` validator. The launcher never loads a loose ROM path.

### Built or reused

**A source-built game reuses its current attempt and relinks only when its
inputs changed.** The launcher runs `sw build` under one fixed tag and never
passes `--rebuild`, so the build's own fingerprint — over every source, asset,
layout, interface export and packaging input — decides. A player waits for a
build only after something actually changed, and never for a rebuild of
identical sources. Correctness does not depend on that choice: whichever way the
build goes, the loaded bytes come from an immutable attempt that
`host load --package` validates in full, including the artifact hashes, the
profile, the interface inputs and the header.

Then the pad appears. **Back** returns to the menu, releasing every held button
first; the game keeps running on the board. Choosing another game loads it in
place of the one running.

## One session throughout

The launcher, every load and the pad share one UART session. It takes the same
canonical machine lock and the same durable per-device session the pad and the
viewer take, and holds them for the whole window. There is no second session for
loading and no handoff between processes.

Its entry preconditions are the expected build and ABI, UART input authority and
effective input 0. It does not require a valid image, because putting one there
is its job. After a game is loaded, reset and running, the
[pad's own preflight](GAMEPAD.md#session-locks-and-exit) is what hands over:
valid image, UART authority, neutral input and a paused-or-running core, checked
in that order. A failed precondition sends no control traffic at all.

On exit — Escape, the window close, the lease expiring or Ctrl+C — the session
writes `INPUT` 0 and reads the effective input back to verify 0 before reporting
release, exactly as the pad does, and leaves the session certain. It does not
`HALT` the core: the player is watching the screen. The loaded game stays on the
board.

## When something goes wrong

Each of these produces a sentence a player can act on, not a traceback:

| What happened | What the window says |
| --- | --- |
| The board is already held | The pad's own explanation: another trusted controller, or another session holding the device lock |
| A pinned image does not match its digest | It was refused and nothing was loaded; delete the cached copy and retry |
| The image is not cached and cannot be fetched | Connect once or place the cached image, then retry |
| The board read different bytes back | It was not started; check the wiring and the selected port |
| A source-built game did not build | Nothing was loaded; the exact `sw build` command to run to see why |
| The link stopped answering mid-load | This session cannot send anything more; recover it before playing |
| The game runs but never enables the LCD | The core is running and the monitor is blank, with the documented reason and link for the two known cases |

The last one is a board answer, not a guess: after a game starts, the launcher
reads the live LCD status until the LCD comes on. If it is still off after the
grace period, the window says so and stays playable.

## Verification

[`tools/n2m/tests/test_launcher.py`](../../../../tools/n2m/tests/test_launcher.py)
covers the catalogue against the manifests themselves — every game listed once,
ours first, each third-party author and licence equal to its pin, the two known
blank games marked, explained, linked and sorted last — the exact request order
through load, reset, run and the pad's preflight, the progress reported while a
load is in flight, the build that is asked for without `--rebuild` and the
immutable attempt it resolves to, replacing one loaded image with another, every
failure message above, the blank-screen watch, and the exit path including the
uncertain session and a wire failure inside the window. It runs against a fake
endpoint with no board and no window.

A window cannot be asserted headlessly. Everything the launcher does other than
drawing itself lives in `Launcher`, `BootWatch` and `explain`, which is what
those tests drive; the pad's own behavior stays in `Driver` and its widgets in
`PadPanel`, which the launcher reuses rather than reimplements.
