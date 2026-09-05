# RTL reference style for the display

Use the references' explicit stages, typed boundaries, and small memory wrappers
to guide original RTL. Their text engines illustrate indirection and scanout;
they do not define Game Boy behavior. This is an analysis, not an approved
microarchitecture. The [current phase](../agents/bootstrap-plan.md#current-phase)
and [gap register](../preflight-gaps.md) still govern implementation.

## Sources and limits

Inspected committed sources in [frog-bui at 311e64d6][bui] and
[FROG_FS at 69e2cabd][fs], including RTL, board reset wrappers, and display tests.
These findings concern root `src/`, not FROG_FS workshop copies. Both commits
were verified through GitHub. Neither tree lists a `LICENSE`, `COPYING`, or
`NOTICE` file; reuse rights remain unresolved under
[GAP-002](../preflight-gaps.md#gap-002-license-rom-policy-and-provenance).
No HDL, font, or game assets are imported.

This is source inspection, not a simulation, synthesis, timing, or hardware
result. Test code establishes intended checks, not their passing status.

## Observed style

| Aspect | Shared pattern and differences | Lesson for nand2mario |
|---|---|---|
| Boundaries | Both separate text/font storage, bus adaptation, graphics, and raster timing. FROG_FS nests timing inside [graphics][fs-graphics]; frog-bui passes coordinates and sync/status into [graphics][bui-graphics]. | Give each module one timing or storage responsibility; choose boundaries from the future contract. |
| Names and types | Both use `rv_` modules, `u_` instances, `logic`, uppercase constants, and `t_` packed records/enums in [packages][fs-types]. FROG_FS imports `rv_pkg::*`; frog-bui [qualifies package types and widths][bui-types]. | Preserve recognizable naming and typed interfaces; define only shared concepts in packages. CPU-specific widths and names are not a Game Boy contract. |
| Stages | CPU memory paths use `Q103H` request and `Q104H` response suffixes. FROG_FS graphics uses `V0H` address, `V1H` character/font address, and `V2H` font data. frog-bui uses `Q1H`/`Q2H` for pixel metadata. | Make cycle ownership visible in names and carry validity, coordinates, and sync beside data. Do not inherit CPU stage numbers mechanically. |
| Logic | Both use `assign`/`always_comb` for calculations and `DFF*` macros for state. [FROG_FS MMIO][fs-mmio] and [frog-bui MMIO][bui-mmio] default next state to current state before writes. | Keep next-state logic complete and register updates obvious. Preserve the concise macro idiom if adopted; independently define and test its semantics. |
| Reset | Shared [DFF macros][macros] use positive clock edges: `DFF_RST` is synchronous, active high, clearing to zero; `DFF_RST_VAL` chooses the value; `DFF_RST_EN` gives reset priority over enable. Board wrappers differ: [FROG_FS][fs-reset] synchronizes/debounces a button; [frog-bui][bui-reset] asserts reset asynchronously and releases through two destination flops. | State reset semantics per domain; similarly named modules need not have equivalent contracts. |
| RAM and ports | [FROG_FS][fs-ram] directly instantiates dual-port MAX 10 `altsyncram`, with debug access selecting the scan port. [frog-bui][bui-ram] separates portable byte RAM from a Quartus wrapper and keeps scanout independent of the CPU/host port. | Put vendor implementation behind a small boundary. Specify latency, arbitration, byte lanes, and collisions before choosing RAM. |

## Graphics and memory timing

Both use an 80 by 30 text grid of 8 by 16 glyphs. A cell selects a character;
the character and glyph row select a font byte; one bit selects a pixel. Two
memory reads require two pixel stages. [FROG_FS's wrapper][fs-wrap] delays the
byte selector with the returned word, illustrating why data and address
metadata must advance together.

Their visible behavior differs. FROG_FS selects one 12-bit foreground color or
black; its exported status is at `V0H`, while RGB/sync use `V2H`.
frog-bui delays status with RGB/sync and decodes foreground/background indices.
Its color crossing relies on software holding a multibit value stable and
applies the sampled value at a frame boundary. That documented assumption is
not a general coherent-bus CDC protocol. These details are visible in the two
graphics sources above.

Cautions: FROG_FS exposes glyph-size parameters but slices coordinates for
8 by 16 cells. Parameter names alone do not prove supported configurations.
frog-bui's portable and Quartus RAM branches need equivalent latency and
collision evidence; reading either branch cannot prove that equivalence.
Neither reference's clock rate, frame-boundary color update, or RAM arbitration
settles [GAP-006](../preflight-gaps.md#gap-006-clock-reset-and-cdc-plan) or
[GAP-012](../preflight-gaps.md#gap-012-vga-frame-crossing).

## Validation patterns

[frog-bui's display smoke][bui-test] initializes memory through host accesses,
checks byte writes/readback and CPU/host contention, then checks expected
foreground/background pixels, blanking/sync boundaries, known outputs, and a
timeout. This is useful layered evidence, although it also reads DUT hierarchy.

[FROG_FS's pixel tracker][fs-test] emits a raster trace and checks output color,
but derives expected activity from the DUT's own `glyph_pixel` and forces scan
counters near the origin. Its [software stimulus][fs-stimulus] exercises text
and MMIO. Useful diagnostics are not an independent rendering oracle: a wrong
glyph lookup can agree with itself.

For future verification, retain assertions and small directed checks, with
expected pixels derived independently from test-owned data. Check memory
responses and timing as well as the final image. Use asymmetric patterns to
expose bit order and stage shifts; add behavior-specific cases once specified.

## What belongs to the DMG contract

Pan Docs at [fe246067][pandocs] is the behavior reference for this distinction:

- [Tile data][tiles]: 8 by 8, two bitplanes, two bytes per row, bit 7 leftmost.
  Both FROG graphics engines select bit 0 first. Preserve staged lookup style,
  not their glyph format or bit order.
- [Background/window maps][maps]: two 32 by 32 tile maps, scrolling and tile
  addressing rules. [Objects][objects] add OAM selection, transparency, and
  priority; a programmable font grid does not supply these behaviors.
- [Palettes][palettes] map pixel indices to four DMG shades. VGA colors are
  an output presentation choice, not permission to add CGB or NES behavior.
- [Rendering][rendering] produces 160 by 144 visible pixels progressively,
  with mode-dependent memory access and variable pixel-transfer timing.
  A final image alone cannot establish raster-write compatibility.

The game supplies its tiles and maps through emulated machine behavior; this
study does not select a commercial ROM or authorize importing its assets.

## Next design decisions

The [tile pixel contract](rtl/display/MAS_display.md) defines the first isolated stage.
Before proposing integrated microarchitecture, define the display's observable contract:
DMG target/timing fidelity, register and VRAM/OAM access rules, tile/object
priority, and reset behavior. Then compare memory schedules and Game Boy-to-VGA
buffering against that contract, including frame-rate mismatch and CDC. Choose
independent pixel/timing acceptance cases alongside those decisions. Existing
product prerequisites and the
[current authorization](../agents/bootstrap-plan.md#verification-and-hardware-authorization)
remain in force.

[bui]: https://github.com/amichai-bd/frog-bui/tree/311e64d6e7e54db682e515f51aef92c083a32d5a
[fs]: https://github.com/amichai-bd/FROG_FS/tree/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5
[bui-graphics]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/rv_cpu/rv_vga_subsystem/rv_graphics_engine.sv#L8-L94
[fs-graphics]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/rtl/rv_cpu/rv_vga_subsystem/rv_graphics_engine.sv#L11-L115
[bui-types]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/rv_cpu/rv_pkg.sv#L452-L488
[fs-types]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/rtl/rv_cpu/rv_pkg.sv#L104-L122
[macros]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/rtl/common/macros.svh#L16-L47
[bui-mmio]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/rv_cpu/rv_mmio.sv#L212-L278
[fs-mmio]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/rtl/rv_cpu/rv_mmio.sv#L161-L219
[bui-reset]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/fpga/rv_cpu/de10_lite/rv_button_reset_sync.sv#L7-L25
[fs-reset]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/fpga/rv_cpu/de10_lite/rv_button_reset_sync.sv#L3-L49
[bui-ram]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/rtl/rv_cpu/rv_vga_subsystem/rv_vga_text_ram.sv#L31-L101
[fs-ram]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/rtl/rv_cpu/rv_vga_subsystem/rv_vga_text_ram.sv#L53-L109
[fs-wrap]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/rtl/rv_cpu/rv_vga_subsystem/rv_vga_text_mem_wrap.sv#L62-L143
[bui-test]: https://github.com/amichai-bd/frog-bui/blob/311e64d6e7e54db682e515f51aef92c083a32d5a/src/dv/rv_cpu/smoke/tb_vga_smoke.sv#L164-L345
[fs-test]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/dv/rv_cpu/tb_files/rv_cpu_vga_post_process.svh#L13-L106
[fs-stimulus]: https://github.com/amichai-bd/FROG_FS/blob/69e2cabdb6c2c633cdb7cebda05a2c8b309dfbc5/src/dv/rv_cpu/tests/vga_pixel_smoke/vga_pixel_smoke.c#L4-L16
[pandocs]: https://github.com/gbdev/pandocs/tree/fe246067b695b5404a4a6a47efb4fd6d921ececb
[tiles]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Tile_Data.md
[maps]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Tile_Maps.md
[objects]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/OAM.md
[palettes]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Palettes.md
[rendering]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Rendering.md
