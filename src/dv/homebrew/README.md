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

One session on 2026-09-13 over COM3, wire build
`87d5f0280a2afad8be6b85dc601141cc`, ABI 1, profile `dmg-direct-v1`. Every game
was loaded with `host load --external`, which verified its pinned SHA-256 and
read all 32768 bytes back. Each run began and ended paused with `INPUT`,
`INPUT_SOURCE` and `INPUT_EFFECTIVE` 0 and the sequence certain; none reported
an uncertain completion, so no run needed `--endpoint-restarted`. `--intro-seconds 8`
throughout, each hold exactly its stated number of 70224-dot frames.

**Six of the eight boot and play. Two complete no frame at all.**

### The six that ran

Snapshot `dot` is the frame's completion and `seq` counts frames since the
reset epoch. `mask` is the JOYP mask in force when that frame completed.

| Pin | Frame | seq | dot | CRC32 | mask | Content |
|---|---|---|---|---|---|---|
| `airaki` | `intro` | 434 | 33614360 | `b935db35` | 0 | Two wolves and crossed swords |
| | `title` | 618 | 46664971 | `a8d1e713` | 0 | `AIRAKI!` with `START`, ©2014 FSEII |
| | `play` | 1164 | 85843549 | `4d186b45` | 0 | Match board, both fighters, health bars, timer |
| `gb-wordyl` | `title` | 476 | 33560807 | `ce4a8900` | 0 | `GAME BOY WORDYL`, `PRESS START` |
| | `instructions` | 602 | 42409041 | `e35d78bf` | 0 | Welcome and controls, `ANY KEY TO BEGIN` |
| | `play` | 752 | 52942635 | `3ac129fb` | 0 | Guess grid and keyboard, four letters entered |
| `max-pirate` | `title` | 413 | 33604911 | `982d979c` | 0 | `Max PIRATE`, `PRESS START` |
| | `play-1` | 539 | 42453141 | `0d4e58ee` | 0 | First room, hearts and item HUD |
| | `play-2` | 599 | 46666581 | `f4cb6138` | 1 | Right held: the pirate has walked to the crates |
| `alien-invasion` | `title` | 475 | 33587607 | `a21bbf1d` | 0 | `ALIEN INVASION`, `PRESS START` |
| | `play-1` | 601 | 42435831 | `7a5f389e` | 0 | Formation, `SCORE 00000000`, a shot in flight |
| | `play-2` | 661 | 46649277 | `2136d521` | 1 | Right held: the ship has moved right |
| `square-fall` | `title` | 471 | 33608607 | `7a3b88ce` | 0 | `SQUARE FALL`, `PRESS START`, `HI - 00000` |
| | `play-1` | 593 | 42457915 | `53d9e9b7` | 0 | Rotated field, `SCORE 00000`, `CHAIN 00` |
| | `play-2` | 875 | 62261083 | `702c2f39` | 0 | After A, Right, A: `SCORE 00021`, `CHAIN 16` |
| `unstoppable-knight` | `title` | 477 | 33568467 | `1d80a9c8` | 0 | `UNSTOPPABLE KNIGHT`, `RAFAGARS 2021` |
| | `play-1` | 601 | 42436429 | `7de454a8` | 0 | Forest, falling hazards, `SCORE 0000` |
| | `play-2` | 661 | 46649869 | `0e6311fc` | 1 | Right held: `SCORE 0010`, coins `0x01` |

The frozen scripts are in `SCRIPTS`; the applied masks and their exact dots are
in each archive under `tools/wiki/board_frames/homebrew-<pin>.json`. Wall time
per game was 30.7 to 49.2 s, each well inside its own 300 second host batch.

### The two that completed no frame

Wyrmhole and Rex Run both load, and both execute continuously, and neither ever
enables the LCD. `SNAPSHOT` answers `NO_FRAME` because no frame has completed.

| Pin | Ran for | Retirements | `LCDC` | `STAT` | `LY` | `BGP` |
|---|---|---|---|---|---|---|
| `wyrmhole` | 75615408 dots | 7089821 | `0x00` | `0x00` | `0x00` | `0x00` |
| `rex-run` | 42058030 dots | 4212561 | `0x00` | `0x00` | `0x00` | `0x00` |

Retirements climb at about one instruction per 10.7 dots throughout, the rate of
a tight polling loop, so neither has stopped or halted.

Each ROM says why. Both poll for the LCD before they enable it:

- Wyrmhole at `0x6370`, immediately before its only `LCDC` write:
  `F0 44` `LDH A,[rLY]`, `FE 90` `CP 144`, `38 FA` `JR C,-6`, then `AF`
  `XOR A`, `E0 40` `LDH [rLCDC],A`. It waits for `LY` to reach 144 so it can
  switch the LCD off safely. With the LCD off, `LY` stays 0. This is the only
  `LY` read in the image.
- Rex Run at `0x1186`: `F0 41` `LDH A,[rSTAT]`, `E6 03` `AND 3`, `FE 01`
  `CP 1`, `20 F8` `JR NZ,-8`, then `F0 40` / `E6 7F` / `E0 40`, clearing the
  LCD-enable bit. It waits for mode 1, VBlank, which the mode field never
  reports while the LCD is off.

A real DMG boot ROM hands control to the cartridge with `LCDC` = `0x91`, the
LCD already running, so both loops exit immediately there. `dmg-direct-v1` has
no boot ROM and starts with the LCD off, which the
[entry contract](../../../wiki/src/rtl/interfaces/MAS_interfaces.md#direct-entry-and-reset)
states and marks as deliberately not the Nintendo post-boot state. Both games
are correct for the machine they target; this is the documented difference
between that machine and this entry state, not a PPU, CPU or timing defect.
The other six enable the LCD themselves before waiting on it, so they are
unaffected.

Changing this would mean entering third-party images with the post-boot
register state instead of the project's entry state. That is a change to the
entry contract and is not proposed here.

The retained session folders and their ignored paths are listed in the
delivering pull request.
