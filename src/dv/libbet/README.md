# Libbet physical play

[Libbet and the Magic Floor](../../../tools/n2m/dependencies.json) v0.08 is the
pinned Zlib-licensed third-party image that `host load --external libbet`
uploads. This record shows it played over UART on the DE10-Lite: Start leaves
the title screen, a directional press rolls Libbet on the first floor, and
Select runs its attract demo for 30 s. It is bounded original-game evidence
under the [host commands](../../../wiki/tools/n2m/host/SPEC.md); it is not a
milestone gate, physical-control or connected-monitor proof.

## Driver

[play.py](play.py) opens one ordinary host session (device lock, durable
sequence journal, machine mutex, verified wire build, paused valid image with
neutral UART input). `RESET`, `RUN`, a wall-paced wait, `HALT` and a snapshot
reach the title. Every later step is exact: `INPUT` with the generated mask,
`RUN_DOTS 70224` per frame, `INPUT 0`, `SNAPSHOT`. [frame_png.py](frame_png.py)
decodes each packed frame to PNG and marks pixels that differ from the previous
snapshot. Frames, diffs, CRC32, shade histograms and `result.json` stay in the
ignored `workdir/libbet-play/`; the transaction journal stays under the build
tag. The session ends paused with input released.

```text
python src/dv/libbet/play.py play --uart-port <verified-port> --expected-build-id <reviewed-wire-id>
python src/dv/libbet/play.py demo --uart-port <verified-port> --expected-build-id <reviewed-wire-id>
```

## Input behavior from the source

At tag v0.08 (`46a765a2`), `pads.z80` `read_pad` polls both JOYP rows once per
vblank without a debounce timer. `new_keys` is the set pressed now and not at
the previous read, so a press held across two consecutive vblank reads
registers once; release is not required. The title loop in `instructions.z80`
returns on `new_keys & (Start|Select)`; `main.z80` then enters attract mode
when Select closed it. In play, `try_move` reads held `cur_keys`, faces the
pressed direction, and starts a roll only for a freshly changed direction
onto a valid neighbour: in bounds and `(destination - source) mod 4 < 2`
(same shade or one brighter). An invalid direction plays the wrong-move sound
and busts the combo. The rule is not symmetric: after a one-shade roll, the
reverse direction is `3 mod 4` and invalid. `intro.z80` shows the copyright card for 120 unskippable
vblanks and then up to 180 more that Start or A can skip.

Host masks are active high: Right 1, Left 2, Up 4, Down 8, A 16, B 32,
Select 64, Start 128 ([JOYP](../../../wiki/src/rtl/joypad/MAS_joypad.md)).

## Recorded sessions

Wire build `bb02588d127b72ce6458a07ff1145c57` (the post-#359 `v05-board` fit),
ABI 1, the pinned image already loaded and valid. Each session began and ended
paused, `INPUT 0`, `INPUT_SOURCE 0`, `INPUT_EFFECTIVE 0`, session certain.
Snapshot `dot` is the frame's completion; `seq` counts frames since the reset
epoch. Each `RESET` advanced the snapshot epoch (7, 8, 9).

### Start at 3 s: copyright card, ignored as the source predicts

`play --hold 3 --intro-seconds 3`: halt at dot 12647612 (frame 180). The
snapshot (seq 166, CRC32 `2f13676b`, 468 dark pixels) is the copyright card,
not the title. Start (128) applied at dot 12647612, held three frames,
released at 12858284; then Left, Up, Right and Down each held three frames.
All 16 snapshots through seq 369 (dot 26865111) are identical. The card
starts after the roll-in, so frame 180 lies inside its 120 unskippable
vblanks and its 180-vblank timeout had not expired by frame 383. No
divergence.

### Start at 8 s: title, play, one roll

`play --hold 3 --intro-seconds 8`, wall 34.4 s, halt at dot 33631192.

| Snapshot | seq | dot | CRC32 | Changed | Content |
|---|---|---|---|---|---|
| title | 456 | 33605475 | `c05d7d63` | | Title: "Libbet and the Magic Floor v0.08", story, "Select: demo \| Start: play" |
| after-start-release | 457 | 33675699 | `c05d7d63` | 0 | Last title frame; LCD off while the floor loads |
| start+10 | 463 | 34503311 | `12947b17` | 2755 | Fade-in beginning (739 light pixels) |
| start+60 | 513 | 38014511 | `edf319b6` | 13157 | 2x2 tutorial floor, Libbet on the bottom-right cell, HUD `0 Combo 0% 0/04` |
| left-held | 516 | 38225183 | `c4edbdc5` | 28 | Libbet faces left; no roll |
| left+8, left+32 | 524, 548 | 38786975, 40472351 | `c4edbdc5` | 0, 0 | Unchanged |
| up-held | 551 | 40683023 | `2761bee7` | 261 | Roll starts; HUD `1 Combo 25% 1/04` |
| up+8 | 559 | 41244815 | `3665d188` | 14 | Rolling |
| up+32 | 583 | 42930191 | `8e5a9220` | 82 | Libbet on the top-right cell; bottom-right cell marked |
| right-held | 586 | 43140863 | `215d6acf` | 52 | Faces right (off the floor); still `1 Combo 25% 1/04` |
| right+8, right+32 | 594, 618 | 43702655, 45388031 | `5a6b2249` | 133, 0 | Wrong-move settle; combo busts to `0 Combo`, then unchanged |
| down-held | 621 | 45598703 | `7cb4a859` | 8 | Faces down; no roll, as the reverse of a one-shade roll is invalid |
| down+8, down+32 | 629, 653 | 46160495, 47845871 | `7cb4a859`, `cab1534d` | 0, 16 | Idle animation |

Inputs (applied dot): Start 128 at 33631192, 0 at 33841864; Left 2 at
38055304, 0 at 38265976; Up 4 at 40513144, 0 at 40723816; Right 1 at
42970984, 0 at 43181656; Down 8 at 45428824, 0 at 45639496. Each hold is
exactly 3 x 70224 dots. Final counters: dot 47886664, retirements 688776.

### Select at 8 s: attract demo for 30 s

`demo --hold 3 --intro-seconds 8`, wall 42.9 s. Title at seq 456, dot
33605475, CRC32 `c05d7d63` (identical to the play session). Select (64)
applied at 33625032, released at 33835704. Free run with snapshots at 2, 5,
10, 15, 20, 25 and 30 s: seq 572, 751, 1051, 1350, 1647, 1946, 2245 (dots
42318419 to 159803171, exactly 70224 per frame), CRC32 `6abff5b9`,
`a1a10df8`, `a60ad811`, `5e62db86`, `ab868d62`, `4bf8bbd1`, `c299658d`, every
pair different. The 4x4 attract floor plays itself with the tutorial captions:
`0/20` at 2 s, `4 Combo 20% 4/20` at 15 s, `3 Combo 60% 12/20` at 30 s.
Halt at dot 164423563, retirements 2907450.

The retained artifacts and their ignored paths are listed in the delivering
pull request.
