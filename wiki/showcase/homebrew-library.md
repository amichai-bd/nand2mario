# Other people's games on this Game Boy

Eight freely licensed homebrew Game Boy games, written by eight other people,
were pinned by digest and booted on the DE10-Lite running this repository's
DMG. **Six of the eight run and play. Two never draw anything**, for one
specific and documented reason given below. One further pin, the 64 KiB MBC1
game PostBot, is the
[MBC1 profile's test material](../src/rtl/cartridge/MAS_mbc1_profile.md#external-test-material):
it loads through `host load --external postbot`, has not been captured on the
board, and is not claimed to run here.

**What these pictures are.** Every frame below is a `host snapshot`: the packed
160x144 framebuffer the board returned over UART during one recorded session.
They are not emulator screenshots, not host renderings and not photographs of a
monitor. **What they are not.** This is boot-and-play evidence, not a
correctness proof. No reference model exists for any of these games, so no
pixel here was compared against an expectation; the record says what the board
displayed, not that it displayed the right thing. The
[verification tiers](../src/dv/integration/SPEC.md#verification-tiers) own what
counts as proof, and none of it is claimed here.

**What the evidence is for.** These games were written for real Game Boy
hardware by people who never saw this project, so they cannot share a
misunderstanding with our own RTL, reference models and games. That independence
is not new here — the
[SameBoy adapter](../src/dv/baseline/SPEC.md#independent-emulator-and-retirement-traces)
and the [Mooneye targets](../../src/dv/mooneye/README.md) already supply it
narrowly — but eight full games widen it, and the two that never draw are a
finding of exactly that kind: a real documented difference between this machine
and a Game Boy rather than a shortfall.

**Why it matters.** The hardware supports the 32 KiB direct profile, cartridge
type `0x00` with no mapper and no cartridge RAM
([interfaces](../src/rtl/interfaces/MAS_interfaces.md)). Every game here is a
ROM-ONLY image that fits that profile, so it runs with no RTL change. Until
this page, [Libbet](README.md#libbet-on-the-board) was the only third-party
image the project had run: a sample of one.

**Attribution.** These games belong to their authors and stay under their own
terms. Each section names the author and the exact licence, and links the
artifact this repository pins. Nothing of any game's source or bytes is
committed here: each image is fetched at run time from its pinned URL and
refused unless its SHA-256 matches the
[dependency manifest](../../tools/n2m/dependencies.json).

## How each capture was made

```text
python src/dv/homebrew/play.py play <pin> --load --intro-seconds 8 \
    --uart-port <verified-port> --expected-build-id <reviewed-wire-id>
```

`--load` runs `host load --external <pin>`, which verifies the pinned SHA-256
and reads all 32768 bytes back before the run
([host commands](../tools/n2m/host/SPEC.md)). The driver then resets, reaches
the first screen on wall time, and walks that game's frozen input script with
exact `RUN_DOTS` of one 70224-dot frame, so every later sample's sequence and
completion dot are reproducible. Every session ran on wire build
`87d5f0280a2afad8be6b85dc601141cc`, ABI 1, over COM3 on 2026-09-13, and began
and ended paused with `INPUT`, `INPUT_SOURCE` and `INPUT_EFFECTIVE` all 0 and
the sequence certain. [The session record](../../src/dv/homebrew/README.md)
holds every script, every applied input and its dot, and what each game did.

Two of the eight are pinned to a third-party redistribution rather than an
author release, because their authors publish no release asset; each says so in
its own section and in the manifest.

| Game | Author | Licence | Result |
|---|---|---|---|
| [Airaki](#airaki) | furrtek | GPL-3.0-or-later | Boots and plays |
| [GB Wordyl](#gb-wordyl) | bbbbbr | GPL-3.0-only | Boots and plays |
| [Max Pirate](#max-pirate) | Marcel Wehrstedt | MIT | Boots and plays |
| [Alien Invasion](#alien-invasion) | NiliusJulius | GPL-3.0-only | Boots and plays |
| [Square Fall](#square-fall) | bjorn_nah | MIT | Boots and plays |
| [Unstoppable Knight](#unstoppable-knight) | Rafagars | MIT | Boots and plays |
| [Wyrmhole](#wyrmhole-and-rex-run-never-turn-the-lcd-on) | Quinn Painter | MIT | No frame: hangs before enabling the LCD |
| [Rex Run](#wyrmhole-and-rex-run-never-turn-the-lcd-on) | elseyf | GPL-3.0-only | No frame: hangs before enabling the LCD |

The two SPDX suffixes come from what each project declares, not from a
judgement made here. Airaki is `GPL-3.0-or-later` because its upstream
catalogue entry declares exactly that. The other three declare GPL version 3
with no "or any later version" statement, so they are recorded as
`GPL-3.0-only`, the narrower reading.

All three images that declare CGB flag `0x80` — Airaki, GB Wordyl and
Unstoppable Knight — boot and render on this DMG. Airaki is also catalogued
upstream as a GBC title; it plays here in the four DMG shades.

## Airaki

furrtek, **GPL-3.0-or-later**.
[Source](https://github.com/furrtek/Airaki) ·
[pinned artifact](https://raw.githubusercontent.com/gbdev/database/434b8d35af69d6bf8184fe1bc9a4c41294c8ad42/entries/airaki/airaki.gb).

A tile-matching RPG puzzle, written in assembly. The pinned bytes are a
**third-party redistribution**, not an author release: the artifact is the
`gbdev/database` blob `entries/airaki/airaki.gb` at commit
`434b8d35af69d6bf8184fe1bc9a4c41294c8ad42`, because furrtek publishes no
release asset. The licence text is pinned separately in furrtek's own
repository.

![Airaki captured on the DE10-Lite](homebrew-airaki.svg)

The intro, the title after the first Start, and the match board a second Start
and two A presses later: swords, shields and potions to match, with both
fighters' health bars and the round timer.

## GB Wordyl

bbbbbr, **GPL-3.0-only**.
[Source](https://github.com/bbbbbr/gb-wordle) ·
[pinned artifact](https://raw.githubusercontent.com/gbdev/database/434b8d35af69d6bf8184fe1bc9a4c41294c8ad42/entries/gb-wordyl/GBWORDYL_0.85_en.gb).

A word game with a full dictionary in 32 KiB. The pinned bytes are a
**third-party redistribution**, not an author release: the artifact is the
`gbdev/database` blob `entries/gb-wordyl/GBWORDYL_0.85_en.gb` at the same
commit, because bbbbbr publishes no release asset. GB Wordyl is itself an
expanded fork of stacksmashing's original; the licence text is pinned in
bbbbbr's repository.

![GB Wordyl captured on the DE10-Lite](homebrew-gb-wordyl.svg)

The title, the welcome and controls screen, and the guess grid with the
on-screen keyboard. Six A presses follow: the first leaves the controls screen
and the rest type from the cursor's starting key, four letters of which had
been entered when the captured frame completed.

## Max Pirate

Marcel Wehrstedt, **MIT**.
[Source](https://github.com/MWehrstedt/MaxPirate) ·
[pinned artifact](https://github.com/MWehrstedt/MaxPirate/releases/download/v1.0/maxpirate.gb)
(release `v1.0`, asset `maxpirate.gb`).

![Max Pirate captured on the DE10-Lite](homebrew-max-pirate.svg)

The title, the first room after Start with the hearts and item HUD, and the
same room with Right held: the pirate has walked to the crates on the right.

## Alien Invasion

NiliusJulius, **GPL-3.0-only**.
[Source](https://github.com/NiliusJulius/Alien-Invasion) ·
[pinned artifact](https://github.com/NiliusJulius/Alien-Invasion/releases/download/v1.0.0/Alien-Invasion.gb)
(release `v1.0.0`, asset `Alien-Invasion.gb`).

A Space Invaders variant built around 8x16 sprites so two enemies share one
hardware sprite, which is how it keeps a full formation on screen inside the
40-sprite limit.

![Alien Invasion captured on the DE10-Lite](homebrew-alien-invasion.svg)

The title, the formation with a shot in flight, and the ship moved right with
Right held.

## Square Fall

bjorn_nah, **MIT**.
[Source](https://github.com/bjorn-nah/square_fall) ·
[pinned artifact](https://github.com/bjorn-nah/square_fall/releases/download/v0.3/square_fall_v03.gb)
(release `v0.3`, asset `square_fall_v03.gb`).

The repository carried no `LICENSE` file at the release commit, so the pinned
licence text is the later commit that added it; the manifest records which.

![Square Fall captured on the DE10-Lite](homebrew-square-fall.svg)

The title, the rotated play field, and the field after A, Right and A: score
`00021`, chain `16`, and a different `NEXT` count.

## Unstoppable Knight

Rafagars, **MIT**.
[Source](https://github.com/Rafagars/Unstoppable-Knight-GB) ·
[pinned artifact](https://github.com/Rafagars/Unstoppable-Knight-GB/releases/download/2.2.2/knight.gb)
(release `2.2.2`, asset `knight.gb`).

![Unstoppable Knight captured on the DE10-Lite](homebrew-unstoppable-knight.svg)

The title, the forest with falling hazards above the knight, and the same run
with Right held: the score has gone from `0000` to `0010` and the coin count
from `0x00` to `0x01`, so the game is advancing, not just drawing.

## Wyrmhole and Rex Run never turn the LCD on

Wyrmhole (Quinn Painter, **MIT**,
[source](https://github.com/QuinnPainter/Wyrmhole),
[pinned artifact](https://github.com/QuinnPainter/Wyrmhole/releases/download/1.1/Wyrmhole.gb))
and Rex Run (elseyf, **GPL-3.0-only**,
[source](https://github.com/elseyf/rex-run-gb),
[pinned artifact](https://github.com/elseyf/rex-run-gb/releases/download/v1.0/rex-run.gb),
a Game Boy port of the Chrome offline dinosaur game) both load and both
execute, and neither ever produces a frame. Rex Run's repository carried no
`LICENSE` file at the release commit, so its pinned licence text is the later
commit that added it, exactly as Square Fall's is; the manifest records which. There is no
screenshot to publish, because the board completed no frame to capture:
`SNAPSHOT` answers `NO_FRAME`.

What the board reported, with the image loaded and verified and the core left
running:

| Game | Ran for | Retirements | `LCDC` | `STAT` | `LY` | `BGP` |
|---|---|---|---|---|---|---|
| Wyrmhole | 75,615,408 dots | 7,089,821 | `0x00` | `0x00` | `0x00` | `0x00` |
| Rex Run | 42,058,030 dots | 4,212,561 | `0x00` | `0x00` | `0x00` | `0x00` |

The CPU is running the whole time — retirements climb steadily, at the rate of
a tight polling loop — but `LCDC` never leaves `0x00`, so the PPU never starts,
no frame ever completes, and the VGA output stays blank.

Each game's own code says why. Both wait for the LCD **before** they enable it:

- Wyrmhole, at ROM `0x6370`, immediately before the `LCDC` write at `0x6377`
  that is first on its init path: `LDH A,[rLY]` / `CP 144` / `JR C,-6`, then
  `XOR A` / `LDH [rLCDC],A`. It waits for VBlank by polling `LY` until it
  reaches 144, so that it can safely switch the LCD off. With the LCD already
  off, `LY` is parked at 0 and the loop never exits. This is the ROM's only
  `LY` read; it writes `LCDC` in four other places, all past this point.
- Rex Run, at ROM `0x117A`: `LDH A,[rSTAT]` / `AND 3` / `CP 1` / `JR NZ,-8`,
  then `LDH A,[rLCDC]` / `AND 0x7F` / `LDH [rLCDC],A` at `0x1186`. It waits for
  `STAT` to report mode 1, VBlank, before clearing the LCD-enable bit. With the
  LCD off the mode field reads 0 forever. The three instructions immediately
  before it, at `0x1174`–`0x1179`, are `LDH A,[rIE]` / `AND 0` / `LDH [rIE],A`,
  so interrupts are masked and nothing can break the loop.

The retirement counters show that nothing but those loops ran. Wyrmhole's three
instructions cost 12 + 8 + 12 = 32 dots; Rex Run's four cost
12 + 8 + 8 + 12 = 40. Each sampling interval is 60 frames, 4,213,440 dots, and
each loop divides it with **remainder zero**: 4,213,440 ÷ 32 = 131,670 whole
Wyrmhole iterations, and ÷ 40 = 105,336 whole Rex Run iterations. Multiply by
the instructions per iteration and the predictions are 395,010 and 421,344. The
board reported exactly those numbers, on every interval — three for Wyrmhole,
two for Rex Run, with no variation.

A zero remainder leaves no room for a partial iteration or for any other
instruction anywhere in those 4.2 million dots. So this is not merely a rate
consistent with the loop: across the whole observation each CPU executed that
loop and nothing else. The two are also mutually exclusive. Had Wyrmhole been
in Rex Run's loop its counter would have read 421,344, and Rex Run in
Wyrmhole's would have read 395,010; each read its own figure.

Both are waiting for a condition a real DMG would already have satisfied. The
Nintendo boot ROM hands control to the cartridge with the LCD **running** —
`LCDC` = `0x91` — so on real hardware `LY` sweeps and `STAT` reports VBlank
before the game's first instruction. This platform has no boot ROM. The
`dmg-direct-v1` entry state is
[defined](../src/rtl/interfaces/MAS_interfaces.md#direct-entry-and-reset) as
"There is no boot ROM mapping ... LCD and audio are off", and is explicitly
"not a claim about DMG power-on or Nintendo post-boot state". These two games
are the first third-party code to depend on the difference.

So this is not a PPU, CPU or timing defect, and both games are behaving
correctly for the machine they were written for. It is the documented gap
between `dmg-direct-v1` and the post-boot state a cartridge normally inherits.
The six games above never wait on the LCD before enabling it themselves, which
is why they are unaffected.

Closing the gap would mean entering third-party images with the post-boot
register state rather than the project's own entry state. That is a change to
the entry contract, not a bug fix, and nothing here proposes it.

## Reproducing these images

The frames are not re-read from hardware when the page is regenerated. Each
session is ingested once into a committed archive under
`tools/wiki/board_frames/homebrew-<pin>.json`, which holds the provenance, the
pin and, per frame, its sequence, completion dot, applied JOYP mask, CRC32 and
the indexed-PNG payload the SVG embeds. See
[frame archives and encoding](README.md#frame-archives-and-encoding).

```text
python tools/wiki/board_frames.py homebrew-<pin> <session folder> --note "..."
python tools/wiki/showcase.py
```
