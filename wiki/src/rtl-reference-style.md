# RTL register convention and reference style

Use the references' explicit stages, typed boundaries, and small memory wrappers
to guide original RTL. Their text engines illustrate indirection and scanout;
they do not define Game Boy behavior. The register convention below is adopted for product RTL; the reference
analysis does not select a Game Boy microarchitecture. The [current phase](../agents/bootstrap-plan.md#current-phase)
and [gap register](../preflight-gaps.md) still govern implementation.

## Separate declarations and assignments

Product RAM and ROM backing stores use the
[shared Intel memory boundary](rtl/common/MAS_memory_primitives.md), with the
same explicit `altsyncram` instance in Questa and MAX 10 synthesis. Its owner
contract distinguishes ordinary flop state and independent reference arrays,
and tracks existing-store migrations. Portable DUT arrays are not replacement
acceptance for the installed vendor model.

Use `logic` for SystemVerilog signals; do not declare them with `wire` or `reg`.
Use `input var logic` when an explicit input port kind is needed under
`default_nettype none`. Preserve widths, signedness, single runtime drivers and
appropriate counter, string, enum and record types. The compiler directive
`default_nettype wire` restores compiler state; it is not a signal declaration.
Generated vendor Verilog and its netlist-parser fixtures retain vendor syntax.

Declare signals without assignments. This applies to
product RTL, FPGA wrappers, DV, shared headers and generated SV. Put continuous
drivers in separate `assign` statements. Put procedural assignments after
all declarations in the containing block; declare loop variables before the
`for` statement, including genvar declarations. Parameter/localparam values
and enum members are compile-time definitions, not signal assignments.

Preserve required power-up values with separate constant `initial` assignments,
including reset-controller state and assertion history. Preserve register names,
widths, signedness and synchronizer attributes. Do not replace a continuous
driver with initialization or add initialization to previously unknown state.
An `initial` block runs at time zero rather than before procedural execution;
keep testbench defaults and their immediate consumers in one startup process,
and check reset/clock transitions and configuration startup in Questa. Prove
FPGA power-up inference in Quartus when moving product initialization.

Run `python .agents/skills/rtl-coder/scripts/check_sv_style.py` before review.
The required Wiki check runs this source guard and its negative fixtures.

## Product register convention

Use the original [shared register header](../../src/rtl/common/macros.svh) for
ordinary product registers. Include it with the literal repository path
`src/rtl/common/macros.svh`; the [builder](../tools/n2m/SPEC.md#hdl-includes)
owns resolution and dependency checks. Keep combinational calculations separate
and give each output exactly one runtime driver; the initialized forms below
add only their required constant power-up assignment. Macro calls are module items, without
an extra semicolon. Parenthesize argument expressions containing commas.

| Form and argument order | Rising-edge update |
|---|---|
| `DFF(Q, D, CLK)` | Capture D |
| `DFF_RST(Q, D, CLK, RST)` | Clear to zero on reset; otherwise capture D |
| `DFF_RST_VAL(Q, D, CLK, RST, RESET_VAL)` | Capture RESET_VAL on reset; otherwise D |
| `DFF_EN(Q, D, CLK, EN)` | Capture D when enabled; otherwise hold |
| `DFF_RST_EN(Q, D, CLK, EN, RST, RESET_VAL)` | Reset value takes priority; otherwise capture D when enabled or hold |

The five forms above use synchronous active-high reset. Their assignments are
nonblocking; input
changes between positive edges do not update Q. Q's declared width controls the
assignment width. Use explicitly sized reset values where nonzero and make
signedness and truncation intentional. Forms without reset have no defined
initial value. Controls must meet the consuming module's known-value contract.

Use `DFF_ARST_VAL(Q, D, CLK, RST, RESET_VAL)` for asynchronous active-high
reset, and `DFF_ARST_N_VAL(Q, D, CLK, RST_N, RESET_VAL)` for active-low reset.
Reset immediately assigns the explicit value and takes priority over D; otherwise
Q captures D on the rising edge. Preserve power-up values using the [separate assignment rule](#separate-declarations-and-assignments),
register names and synchronizer attributes. These forms cover reset synchronizers, qualification
counters and domain state; asynchronous reset or attributes alone are not an
exception. Keep next-state hold and priority explicit in combinational logic.

`DFF_INIT_ARST_VAL` and `DFF_INIT_ARST_N_VAL` use the same argument order
and reset behavior as their asynchronous counterparts, and initialize Q to
RESET_VAL in a separate `initial` statement. Use them only for state whose
contract already requires that power-up value. They use edge-triggered `always`
because Questa rejects another procedural writer alongside `always_ff`
(vopt-7061). Ordinary register forms retain `always_ff`. The initialized forms
are the reviewed inference exception for configuration state and assertion
history; callers must retain exactly one runtime driver.

An explicit sequential block needs a concrete inference requirement that the
shared forms cannot express, such as a memory write port. Document that reason
beside the block and in its owner contract, and review the synthesized result.
Never replace asynchronous reset with synchronous reset. Testbench stimulus, reference models
and scoreboards remain independent; this convention does not require rewriting
them with product macros.

The vocabulary and argument order follow the inspected committed
frog-bui header `src/rtl/common/macros.svh` at local unpublished commit
`da16dc841d50c6c48827225b91dac6b8716b4311`. These are originally written
nand2mario definitions of the specified register operations, not an imported
header. The asynchronous forms are original project extensions; the inspected
reference defines synchronous register forms. No memory macro library is adopted. The
[source policy](../tools/provenance.md) still prohibits unlicensed source reuse.
The [directed test plan](../../src/dv/common/README.md) verifies the register and assertion forms,
and the [tile contract](rtl/display/MAS_display.md) retains its independent oracle.

The owner supplied this local reference checkout. Its inspected files matched
the commit; this revision is not available through an upstream GitHub permalink.
Reproduce inspection from that checkout with
`git show da16dc841d50c6c48827225b91dac6b8716b4311:src/rtl/common/macros.svh`.
This local register inspection is separate from the published historical study below.

## Named assertion convention

Use the shared header for local sampled invariants in product RTL and DV.
These module-item macros follow the inspected frog-bui argument order with
project names and original implementations:

| Form | Check |
|---|---|
| `N2M_ASSERT(NAME, CLK, RESET, PROPERTY)` | Property on rising CLK, disabled while RESET is high |
| `N2M_ASSERT_NO_RST(NAME, CLK, PROPERTY)` | Property on every rising CLK, including reset |
| `N2M_ASSERT_NEVER(NAME, CLK, RESET, CONDITION)` | CONDITION must be false |
| `N2M_ASSERT_KNOWN(NAME, CLK, RESET, SIGNAL)` | SIGNAL has no X or Z bits |
| `N2M_ASSERT_STABLE_WHEN(NAME, CLK, RESET, HOLD, SIGNAL)` | Prior sampled HOLD requires SIGNAL to remain stable |

Failures use `$fatal(1)` with the assertion name and `%m` instance hierarchy.
Choose meaningful unique names within each scope. RESET is active high even when
the checked register has an active-low reset; pass its inverted reset signal.
The stable helper initializes history invalid and clears it asynchronously on
RESET. It skips the first sampled edge after reset, including a pulse wholly
between clocks. Its prior-edge HOLD rule permits an update preceding entry into
hold. The consuming contract must establish which edge owns a control.

`SYNTHESIS` removes all assertion declarations, checks and history state. The
[FPGA builder](../tools/n2m/SPEC.md#hdl-includes) explicitly defines it; simulation
normally does not. Prove both exclusion and an exact named nonzero failure in
Questa. The [test plan](../../src/dv/common/README.md) covers each helper.
Transaction scoreboards retain independent expected/actual diagnostics; these
local helpers do not replace the oracle or require a procedural-check macro.

The reference's sampled-hold idea and names are process observations. Its helper
uses `$error`; this project deliberately requires fatal raw exits and adds reset
history validity. No reference source is copied or licensed by this convention.

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
| Logic | Both use `assign`/`always_comb` for calculations and `DFF*` macros for state. [FROG_FS MMIO][fs-mmio] and [frog-bui MMIO][bui-mmio] default next state to current state before writes. | Keep next-state logic complete and register updates obvious. Use the adopted register convention above; define and test its semantics independently. |
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
