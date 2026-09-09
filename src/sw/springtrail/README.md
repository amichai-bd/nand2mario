# Springtrail source

Original SM83 code and hand-drawn monochrome lettering, courier, enemy, seeds,
flag and terrain. No external game, font, sprite, level or sound source is used.
The silent image uses the existing32 KiB mapperless profile and standard JOYP.

`tiles.json` contains42 tiles. Its first16 tiles retain the foundation artwork;
the added pairs provide the enemy, items, goal, score digits and mode marks.
The [literal scene artwork](../../dv/springtrail/scene_art.py) records their
independent expected pixels. Eight-pixel objects have a blank lower tile in
8x16 mode. Palette E4 maps shades directly. The atlas occupies672 bytes at
0C00; the title map follows it. World collision terrain is unchanged.

Movement and scrolling are implemented. The shared interaction and renderer
routines have bounded CPU proofs, but their live game-loop integration remains
in progress under#262. No added frame of display latency is active. The numeric
world and mechanics contract belongs to the [game spec](../../../wiki/src/sw/springtrail/SPEC.md).

Build: `python tools/build.py sw build springtrail --tag <fresh-tag> --json`.
