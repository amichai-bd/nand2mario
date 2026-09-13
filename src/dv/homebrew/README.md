# Homebrew physical play

Eight freely licensed third-party Game Boy images are pinned in
[dependencies.json](../../../tools/n2m/dependencies.json) beside
[Libbet](../libbet/README.md), and `host load --external <pin>` uploads each.
This record holds what the board did with them. It is bounded third-party-image
evidence under the [host commands](../../../wiki/tools/n2m/host/SPEC.md); it is
not a milestone gate, a correctness proof, a physical-control proof or a
connected-monitor proof. The published captures are on
[Other people's games on this Game Boy](../../../wiki/showcase/homebrew-library.md).

## What was verified before anything was pinned

Each artifact was downloaded once and its header re-read from the downloaded
bytes, not from an HTTP range request. All eight are 32768 bytes with
`0x0147` = `0x00` (ROM ONLY), `0x0148` = `0x00` (32 KiB), `0x0149` = `0x00` (no
cartridge RAM), a valid header checksum and an exact Nintendo logo, so all
eight fit the 32 KiB direct profile
([interfaces](../../../wiki/src/rtl/interfaces/MAS_interfaces.md)) with no RTL
change. Three declare CGB flag `0x80`, CGB-enhanced but DMG-compatible.

| Pin | Title | Author | Licence | CGB flag | SHA-256 |
|---|---|---|---|---|---|
| `wyrmhole` | Wyrmhole 1.1 | Quinn Painter | MIT | `0x00` | `a5e07f89119ee9c9…` |
| `airaki` | Airaki | furrtek | GPL-3.0-or-later | `0x80` | `fd8fe6e023d99699…` |
| `gb-wordyl` | GB Wordyl 0.85 (English) | bbbbbr | GPL-3.0-only | `0x80` | `acc12e3e920e0c43…` |
| `max-pirate` | Max Pirate v1.0 | Marcel Wehrstedt | MIT | `0x00` | `ade748a976cc87d3…` |
| `rex-run` | Rex Run v1.0 | elseyf | GPL-3.0-only | `0x00` | `9e074f66648f7095…` |
| `alien-invasion` | Alien Invasion v1.0.0 | NiliusJulius | GPL-3.0-only | `0x00` | `78cbb13080f587c1…` |
| `square-fall` | Square Fall v0.3 | bjorn_nah | MIT | `0x00` | `ef69e75e1b9bb5fa…` |
| `unstoppable-knight` | Unstoppable Knight 2.2.2 | Rafagars | MIT | `0x80` | `191c7fad34e643ab…` |

The manifest holds each full digest, the immutable URL, the exact licence and
the retained licence text. `airaki` and `gb-wordyl` are pinned to a
`gbdev/database` blob: a third-party redistribution, not an author release,
because neither author publishes a release asset. `rex-run` and `square-fall`
pin their licence text at a later commit than the release, because neither
repository carried a `LICENSE` file when the release was cut. No image bytes
are committed; each is fetched at run time and refused unless its size and
SHA-256 match.

## Driver

[play.py](play.py) opens one ordinary host session per game (device lock,
durable sequence journal, machine mutex, verified wire build, paused valid
image with neutral UART input). With `--load` it first runs
`host load --external <pin>`, which verifies the pinned digest and reads all
32768 bytes back. Then `RESET`, `RUN`, a wall-paced wait and `HALT` reach the
first screen, and the game's frozen script runs in exact `RUN_DOTS` of 70224
dots a frame. Three frames are retained per game: an opening screen and two
frames of play. `frame_png.py` from the
[Libbet driver](../libbet/frame_png.py) decodes each packed frame to PNG and
marks pixels that differ from the previous snapshot. Frames, diffs, CRC32,
shade histograms and `result.json` stay in the ignored
`workdir/homebrew-play/<pin>-<plan>-<stamp>/`; the transaction journal stays
under the build tag. Each session ends paused with input released.

```text
python src/dv/homebrew/play.py play <pin> --load \
    --uart-port <verified-port> --expected-build-id <reviewed-wire-id>
python src/dv/homebrew/play.py explore <pin> \
    --uart-port <verified-port> --expected-build-id <reviewed-wire-id>
```

`explore` applies no input and samples every `--every` frames. It is how each
game's opening screen and the button that leaves it were found before a script
was frozen in `SCRIPTS`.

Nothing here checks a pixel. No reference model exists for third-party code, so
the driver records what the board returned and never asserts what it should
have been.

Host masks are active high: Right 1, Left 2, Up 4, Down 8, A 16, B 32, Select
64, Start 128 ([JOYP](../../../wiki/src/rtl/joypad/MAS_joypad.md)).

## Recorded session

<!-- SESSION -->
