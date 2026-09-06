# DMG picture processing

Contract preparation for [#120](https://github.com/amichai-bd/nand2mario/issues/120).
Detailed timing choices below are under source review before dependent RTL.
This owner covers LCD registers, background/window/object rendering, mode and
interrupt timing, and the final source-pixel boundary. It does not claim a
complete Game Boy or connected-monitor acceptance.

The [charter](../../project-charter.md) selects the original DMG family without
claiming universal silicon identity. Revision-dependent rules use the DMG-B
digital model, consistent with the CPU owner. Mooneye shared A/B/C expectations
support this choice; the documented DMG-0 STAT-blocking divergence is outside
this model. This does not waive DMG-B quirks or release criteria. The [clock contract](../../clocks-resets-cdc.md)
owns emulated dots, pause and reset. The [interface contract](../interfaces/MAS_interfaces.md)
owns direct-entry initialization and frame identity. The
[VGA owner](../vga/MAS_vga.md) owns presentation banks and scanout; dedicated host
snapshot stores remain #93.

## Sources and evidence boundary

[Pan Docs](https://github.com/gbdev/pandocs/tree/fe246067b695b5404a4a6a47efb4fd6d921ececb/src)
is pinned at `fe246067b695b5404a4a6a47efb4fd6d921ececb`, under CC0-1.0.
Rendering, LCDC, STAT, Scrolling, Window, OAM, palette, tile/map and access
chapters supply the shared DMG rules. Its mixed DMG/CGB FIFO prose is not by
itself a complete cycle oracle.

Independent hardware-tested expectations come from
[Mooneye](https://github.com/Gekkio/mooneye-test-suite/tree/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/ppu)
at `31510e12eea6286d36eea060a6adde755e1067aa`, and
[Mealybug](https://github.com/mattcurrie/mealybug-tearoom-tests/tree/70e88fb90b59d19dfbb9c3ac36c64105202bb1f4)
at `70e88fb90b59d19dfbb9c3ac36c64105202bb1f4`. Both use MIT licenses.
These are behavior research sources. Original asymmetric scene fixtures and
public-boundary checks will be independently authored; no test ROM or expected
image has been imported. Exact downloaded text hashes and notices are retained
in the issue's research artifacts. The older [Wilbert Pol fork](https://github.com/wilbertpol/mooneye-gb/tree/b78dd21f0b6d00513bdeab20f7950e897a0379b3/tests/acceptance/gpu)
at `b78dd21f0b6d00513bdeab20f7950e897a0379b3` is GPL-3.0-or-later research
only. Its LY153 cases identify MGB verification and explicitly unchecked DMG;
those results must not be relabeled direct DMG-B measurements.

| Boundary | Source-backed requirement |
|---|---|
| Steady raster | 154 lines of 456 dots, 144 visible lines of 160 pixels; mode 2 uses 80 dots; mode 3 varies with scroll, window and object fetches |
| Objects | Select the first ten Y-overlapping OAM entries, including X-hidden entries; smaller X wins, then lower OAM index; apply BG priority after selecting the winning nontransparent object |
| Fetch effects | Fine SCX is sampled at line start; coarse scrolling, tile selection and each bitplane's Y address are sampled at their fetch stages |
| LCD startup | Mooneye `lcdon_timing-GS` specifies first enabled line mode 0 followed directly by mode 3, with timing two T-cycles later than the normal line; the first enabled frame is visibly blank |
| Coincidence | Mooneye `stat_lyc_onoff` requires the comparison flag to retain its value while LCD is off, including across LYC writes; comparison resumes on enable |
| Interrupts | STAT is an edge of the shared condition, not a pulse per enabled source; Mooneye `vblank_stat_intr-GS` also requires mode-2 selection at the line-144 VBlank edge |
| Window state | WY matching latches a frame condition; the internal window row advances on activation, including repeated enabled activations within one line; hiding it does not substitute LY-WY |

Exact LY153 comparison edges, STAT-write transient alignment, startup dot
numbering and WX boundary behavior must be reconciled with independent timing
expectations before their state transitions are implemented. DMA/OAM collision
behavior needs a named boundary with the later bus owner; ordinary mode access
blocking alone does not establish the OAM corruption quirk.

## Licensed implementation basis

Selected MiSTer renderer, OAM selection and timing logic is approved for private
adaptation. The [upstream manifest](../../../../src/rtl/ppu/upstream.json) owns
its exact pin, file hashes, import state and local changes; the
[notices](../../../../src/rtl/ppu/THIRD_PARTY.md) retain its GPL terms.
Derived files remain GPL-covered. The public wiki contains original explanatory
prose and links, not copied HDL. No source/bitstream release or visibility change
is part of this issue. Independent DMG-B behavior and integration evidence remain
required after adaptation.

The upstream output register samples pixel, validity and palettes together on
its enabled rising edge. A coincident palette write therefore cannot change
that sampled pixel. Adaptation must snapshot raw color, final shade, validity
and metadata from pre-edge state at the emulated-dot edge; later output staging
may only forward that event. The upstream `ce_n` path belongs to excluded extra
sprites, not the normal pixel-output phase.

The actual negedge LCDC/LYC write block still requires an explicit relative-order
mapping: renderer sampling precedes those register changes. No generated clock,
blind same-edge substitution or extra emulated dot is allowed. CPU reads,
mode/access visibility and before/on/after write vectors must corroborate the
digital commit mapping before it is frozen.

## Proposed digital ports

All PPU logic uses `clk_sys`; `gb_tick` commits one emulated T-cycle. Host pause
removes ticks through the shared controller. CPU HALT is not an input and cannot
stop PPU progress. Core reset initializes writable state and execution state to
the generated direct-entry values, including LCD off. External VRAM/OAM clearing
belongs to the memory owner; reset completion waits for that owner before RUN.

The CPU boundary prepares address, direction and write byte before T1, holds
them through T3 and commits once on T4. Only the commit can change LCD registers.
A read exposes the state sampled at that edge, with masks and blocked-access
results defined by this owner. The PPU never stretches an emulated T-cycle.
The shared integration owner must define same-edge register/PPU update ordering.

The intended memory boundary requests one VRAM byte or one OAM entry at a time,
with a fixed system-clock response that completes before the consuming dot.
There is no PPU backpressure. Missing or mistimed memory responses are integration
errors with named assertions, not permission to change mode length. CPU access
permission outputs follow PPU mode; DMA arbitration remains a separate input
contract to settle before memory-facing RTL.

The source boundary emits final two-bit DMG shades, row-major start/valid,
core epoch and completed-dot identity. Registered output pulses are sampled by
the bridge on the following system edge with their associated metadata. Every
real complete source frame reaches the observer before presentation selection.
Neither display drops nor host snapshot activity feeds back into the PPU.

## Proposed LCD cancellation and presentation

LCD disable can interrupt a partial source frame without resetting the CPU,
source epoch, completed-frame sequence, or VGA ownership handshake. An explicit
source-abort event clears only partial writer/observer progress and wins over
a same-edge pixel, including the would-be final pixel. The public observer exposes an abort event with the current epoch and next
completed-frame sequence; abort suppresses same-edge valid/complete. A snapshot
assembler drops only its unpublished partial assembly on that event. Published
frames and existing snapshots remain untouched. An aborted frame emits
no completion and consumes no completed-frame sequence number. Offered and
displayed banks remain immutable.

LCD-off presentation is white within the scaled DMG image, using shade 0 and
RGB F/F/F, while existing borders and blanking remain black. This is the
representable digital mapping; it cannot reproduce an analog white brighter
than the existing maximum. No synthetic complete frame is created merely to
request blank presentation.

The first complete enabled frame is a real blank source frame: every observed
pixel has final shade 0, including through the independent every-frame observer
and future snapshot assembly. Internally rendered colors from that startup
frame are not exposed as final source shades. Subsequent frames expose rendered
shades. Partial disable interrupts either kind of frame in the same way.

A presentation blank request must survive old pending offers and rapid
LCD disable/enable/disable sequences. Only an acknowledged complete frame from
the latest eligible post-startup generation can release it, and release occurs
at a permitted display boundary. Generation qualification belongs to the
presentation adapter, not the host epoch or completed-frame sequence. The
implementation protocol and crossing constraints require review before RTL.
Blank control is persistent, not a pulse or an unacknowledged toggle. Old offers
continue normal acknowledgement and recycling even while white is selected.
Rapid intermediate presentation states may coalesce while the newest blank
request remains pending; a stale offer cannot release that request.

The candidate protocol holds a system-domain blank level until acknowledgement
of an eligible post-startup offer. Each disable or core reset invalidates any
pending release qualification before processing an acknowledgement. It preserves
the blank level itself on core reset. The existing one-outstanding-offer phase
may identify the qualifying offer only after its predecessor has been recycled;
source sequence/epoch reuse is not a qualification token. A separate synchronized
blank level must be observed before that frame's capture/swap acknowledgement.
That ordering needs an explicit invariant and adversarial checks before reuse.

For review, blank assertion overrides the image pixels after its synchronized
pixel-domain arrival, including during active scanout, with global-reset black
having higher priority. Only the scaled image is white. Unblank waits for a
permitted swap boundary; simultaneous blank assertion wins. The exact pipeline
edge and stopped-clock resumption bound must be fixed with the adapter.

Core reset retains the existing last-image rule. Initializing LCDC to zero is
not a software LCD-disable request and must not erase a retained display image.
Global reset keeps the existing invalid-bank black startup behavior.

The [test plan](../../../../src/dv/ppu/README.md) maps these obligations to
independent checks.

## Verification obligations

An independent source model determines expected pixels from original VRAM/OAM
scenes and timed CPU writes. A separate timing model derives expected mode,
access and interrupt traces from externally scheduled dots and pinned tests,
without reading DUT counters, decoded fetch state or frame_done.

Checks cover signed/unsigned tiles, wrap and fine scroll, window activation and
row state, object selection/order/size/flips/transparency and palette effects;
mid-fetch register writes; variable transfer duration; LCD startup/off/on;
LY/LYC and combined STAT edges; core reset, pause and HALT. Composed bridge tests
exercise disable on first/last pixels, pending offers, acknowledgements and
swap boundaries, including repeated toggles before acknowledgement.

Positive and deliberate pixel/timing/interrupt faults must compile, elaborate
and run in Questa through the shared builder, with exact expected nonzero
negative diagnostics. Source-pixel and timing/interrupt traces, original scenes,
commands, seeds and waves remain tagged artifacts. None establishes physical
monitor or complete-system acceptance.
