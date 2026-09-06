# DMG picture processing

Owner contract for [#120](https://github.com/amichai-bd/nand2mario/issues/120).
Detailed timing choices and their source limits are defined below.
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
| Fetch effects | Fine SCX is sampled at the first background map-fetch boundary; coarse scrolling, tile selection and each bitplane's Y address are sampled at their fetch stages |
| LCD startup | Mooneye `lcdon_timing-GS` specifies first enabled line mode 0 followed directly by mode 3, with timing two T-cycles later than the normal line; the first enabled frame is visibly blank |
| Coincidence | Mooneye `stat_lyc_onoff` requires the comparison flag to retain its value while LCD is off, including across LYC writes; comparison resumes on enable |
| Interrupts | STAT is an edge of the shared condition, not a pulse per enabled source; Mooneye `vblank_stat_intr-GS` also requires mode-2 selection at the line-144 VBlank edge |
| Window state | WY matching latches a frame condition; the internal window row advances on activation, including repeated enabled activations within one line; hiding it does not substitute LY-WY |

The sections below define LY153 comparison edges, STAT-write transient
alignment, startup dot numbering and WX boundary behavior with independent
expectations and explicit source limits. [DMA/access arbitration #132](https://github.com/amichai-bd/nand2mario/issues/132)
owns FF46 transfer scheduling and application of DMG-B OAM corruption from CPU
bus/IDU activity. [Memory #130](https://github.com/amichai-bd/nand2mario/issues/130)
owns the single backing store and routing. This PPU owns OAM scan timing and
explicit access/arbitration signals; mode blocking does not prove corruption.
The upstream DMA engine will be removed structurally, not silently omitted from
the product goal.

LCDC bit0 disabling BG/window selects raw background color0, which still passes
through BGP. [dmg-acid2's Hair explanation](https://github.com/mattcurrie/dmg-acid2/blob/8a98ce731f96dde032ffb22ec36dc985d78fdb18/README.md#hair)
explicitly states this palette behavior. It is distinct from LCDC bit7 disabling
the LCD and the first enabled frame's forced final shade0. Test a nonwhite BGP
color0 so an identity palette cannot hide this distinction. Objects can still
win over the disabled background regardless of their behind-BG attribute.

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

## Digital ports

All PPU logic uses `clk_sys`; `gb_tick` commits one emulated T-cycle. Host pause
removes ticks through the shared controller. CPU HALT is not an input and cannot
stop PPU progress. Core reset initializes writable state and execution state to
the generated direct-entry values, including LCD off. External VRAM/OAM clearing
belongs to the memory owner; reset completion waits for that owner before RUN.

The CPU boundary prepares address, direction and write byte before T1, holds
them through T3 and commits once on T4. Only the commit can change LCD registers.
A read exposes pre-edge state, with masks and blocked-access
results defined by this owner. Renderer fetch, shift and final-pixel sampling
also use pre-edge registers. A coincident write commits after those samples;
BGP/OBP writes affect the next pixel sampling edge, not the one already sampled.
LCDC-disable cancellation takes priority over forwarding that edge's source
pixel. The renderer sample can exist internally without becoming an accepted
source pixel. Reset cancels any not-yet-forwarded event. The PPU never stretches an emulated T-cycle.
The shared integration owner must define same-edge register/PPU update ordering.

The intended memory boundary requests one VRAM byte or one 16-bit OAM pair at a time,
with a fixed system-clock response that completes before the consuming dot.
There is no PPU backpressure. Missing or mistimed memory responses are integration
errors with named assertions, not permission to change mode length. CPU access
permission outputs follow the specified access windows, which can differ from
the delayed STAT mode bits. DMA arbitration is an explicit input; denied OAM
service during a legitimate DMA slot is distinct from a missing promised memory
response. Scan phase and address remain observable to the arbiter. No duplicate
OAM store is created in the PPU.

The source boundary emits final two-bit DMG shades, row-major start/valid,
core epoch and completed-dot identity. Registered output pulses are sampled by
the bridge on the following system edge with their associated metadata. Every
real complete source frame reaches the observer before presentation selection.
Neither display drops nor host snapshot activity feeds back into the PPU.

## Digital edge and memory table for review

`A` is the rising system edge carrying `gb_tick`. `B` is the following system
edge. These are pipeline names, not new clocks or emulated dots. An output
event sampled at A is held for the bridge to accept at B. Global/core reset at
B suppresses that pending event. Host pause prevents future A edges but does not
undo the already sampled event. No B action may perform another CPU access,
advance the PPU dot, or reread a palette to alter that event.

| Edge or event | Required ordering |
|---|---|
| Ordinary A | Read pre-edge LCD registers, memory response and renderer state; capture final shade and identity; advance rendering/timing state once |
| CPU read commit at A | Return pre-edge register/mode state; address preparation has no side effect |
| CPU write commit at A | Renderer sampling precedes register mutation; future samples see the write; a write to STAT creates its documented transient from the commit, not from address preparation |
| LCD disable at A | Cancel partial source progress and suppress A's otherwise valid pixel/completion; request white presentation; retain ownership of all complete/offered banks |
| Core reset at any system edge | Initialize PPU control and cancel pending source event without requiring a future tick; preserve VGA mailbox ends, desired presentation state and complete banks |
| Memory contract violation | Latch a visible PPU fault, suppress source publication and future memory side effects, and issue one partial abort; do not insert a wait dot or silently lengthen a mode |
| Interrupt publication | Changed condition after A contributes to the shared owner's combinational next-IF observation before B; CPU retirement captures that observation at B |

The CPU register port is `io_commit`, `io_write`, `io_address[15:0]`,
`io_wdata[7:0]`, and combinational `io_rdata[7:0]`/`io_selected`.
Commit is valid only with `gb_tick`. Generated addresses identify LCD registers;
FF46 belongs to #132. IRQ condition levels and one-system-cycle rising-edge
requests are exposed separately for trace and integration. Their same-edge
interaction with IF writes belongs to [the interrupt owner](https://github.com/amichai-bd/nand2mario/issues/133). That owner supplies the combinational post-event IF observation before B, including the A-updated PPU condition and its specified CPU-write/ack priority. CPU retirement samples that observation at B, rather than the pre-B stored IF. A registered pulse first visible after B cannot be the sole event input for this observation. Edge history prevents repeated requests; CPU dispatch retains its separately specified snapshot.

The VRAM port provides `vram_request`, `vram_address[12:0]` and receives
`vram_data[7:0]` plus `vram_data_valid`. The memory owner supplies a registered
one-system-cycle read response and holds the corresponding data/valid through
the consuming dot. The response belongs to the previously requested address and must be visible before A; registering it at A is too late for that consumption. A newly changed address has the intervening system cycles
to settle; a missing promised response on the consuming edge is a fault.

The OAM port provides a seven-bit pair address, scan-active/index and fetch-phase
observations, and receives the arbitrated sixteen-bit bus pair, data validity
and DMA-active state. There is one external OAM store. The arbiter owns which
bus data is presented during contention; DMA-active suppression of scan capture
is explicit and does not stretch scan time. It is distinct from a missing
promised bus response. The final named phase encoding must agree with #132
before the memory-facing module is frozen.

This table fixes the intended digital transaction abstraction. Directed
before/on/after register writes and imported-core phase comparison must establish
its behavior; it is not an assertion of cartridge-pin phase equivalence.

## STAT-write timing

The pinned [SameBoy DMG conflict implementation](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/sm83_cpu.c#L148)
models all STAT interrupt enables asserted for one T-cycle at a CPU write,
then restores the written enables. This supports the selected one-dot digital mapping;
it does not establish a four-dot pulse or a measured DMG-B half-phase.
Its special HBlank-to-OAM branch explicitly describes a timing approximation.
The approved compatibility projection below preserves that qualification without
moving the renderer's selected source timing.
The existing Mooneye DMG A/B/C blocking case proves shared-line edge behavior,
not the transient width. The older fork's STAT-write test is MGB-verified only.

The ordinary mapping is:

| Edge | Enable and shared-line observation |
|---|---|
| Before write A | Stored enables determine the old shared condition; address preparation has no effect |
| Write A | Renderer/read sampling uses old state; writable STAT bits commit, and a transient-enable flag becomes active after A |
| Before B | Effective enables include the transient; the resulting condition contributes to owner #133 next-IF before retirement capture |
| Following dot A | The transient expires after this edge; stored written enables then determine the condition |
| Pause after write A | No new emulated dot occurs, so the transient retains its emulated duration; edge history still prevents repeated requests |
| Reset | Clear transient and interrupt edge history without waiting for a tick |

A held shared condition must not retrigger because another source or write
joins it. A mode-3 write without coincidence must not invent an active source.
Directed checks must cover old/new enables, active and inactive coincidence,
write before/on/after a mode transition, and a natural STAT event coincident
with T4 retirement and an IF write. One CPU commit cannot write STAT and IF
simultaneously; the composed vector must not invent that stimulus.
At the ordinary OAM source's rising observation, a STAT write with
`old(STAT & 0x28) == 0x08` suppresses only the transient OAM enable for that
one-T interval. Other transient enables remain asserted; the next dot uses the
written enables. This predicate excludes VBlank. It is an approved compatibility
projection of the qualified SameBoy branch, not a measured DMG-B half-phase.
The renderer, readable modes, access gates and four-T OAM source stay unchanged.

At legal write edge452 of the selected startup-relative ordinary transition,
HBlank and OAM sources overlap. HBlank therefore masks this OAM-enable
suppression in the combined condition: old08 and old28 both remain high after
that edge. Writing zero then permits the condition to fall at453. A write at456
does not invent an OAM source after its four-T interval ends. The fixture checks
the internal compatibility qualifier separately and sensitizes its deliberate
fault; it does not claim an IRQ difference that this overlap masks. Public
452/456 mode/access observations and all-edge event counts remain checked.
Separate OAM-only cases compose the actual IF owner and verify a natural event
with and without a simultaneous IF clear, including the pre-B observation.
LCD-off retention is specified in the LCD-off section below.

## LCD cancellation and presentation

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

The [VGA LCD-control boundary](../vga/MAS_vga.md#lcd-cancellation-and-blank-control)
owns the persistent blank request, qualifying offer acknowledgement, crossing
latency and final aligned white mask. The PPU supplies one disable request and
marks only post-startup frames eligible to release it. Generation qualification
uses presentation ownership, never source epoch/sequence reuse.

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

### Pixel shift state

`n2m_ppu_shift` holds two background planes, two object planes, and object palette
and priority bits for eight pending pixels. The renderer samples their high bits
before A. On a tick, advance shifts toward that high bit; background reload wins
over advance. Object load fills only slots whose pre-edge raw object color is
zero, preserving the first object's priority. The fetch controller orders object
loads by X then OAM index. Line clear wins over all tick operations. System reset
clears all planes even without a tick. These controls do not add emulated dots.
The controller supplies already flipped tile bytes and keeps object fetching
paused against pixel advance in ordinary schedules. The shift module preserves
the pinned source's pre-edge slot test even for simultaneous load and advance;
independent vectors check that boundary and reset while paused before integration.
The shift helper reset is synchronous: the integration drives its reset from the released system-domain reset or local core reset, with reset priority over gb_tick. It does not itself provide asynchronous output masking; the existing global/domain reset boundary owns that protection.

### Fetch sequencing boundary

The selected renderer's fetch sequencer owns the three-bit background and object
fetch phases, shift position, first-background/window-fetch state, tile index,
and fetched plane bytes. Each map or plane read occupies two dots; the odd dot
captures the response already visible before A. Phase five can reload the high
background plane directly from that response, rather than its newly written
register. The sequencer emits load controls for the shift helper; it never
recomputes an A-captured pixel at B.

Background reload resets fetch phase, while a simultaneous unpaused shift-count
increment uses its pre-edge count as in the pinned implementation. Window start
and mode3 exit then override both fetch phase and shift position. Object fetch
starts only after the first background fetch and outside the first window fetch;
it returns to phase zero when no object is pending or that fetch completes.
All state has explicit synchronous system reset independent of gb_tick. Missing
promised VRAM data latches the common PPU fault and suppresses load publication;
the top-level owner performs the single source abort. This helper does not own
LCD startup, window trigger quirks, OAM selection or bus arbitration.

### Controller phase convention

The adapted timing controller retains the selected source's divide-by-four
phase and 114-quarter line counter. Phase zero advances the quarter counter;
phase two at quarter113 advances LY and begins the end-of-line history. LY read
state, comparison history, VBlank condition and CPU-visible mode are separate
signals. The controller does not turn a STAT condition level into repeated IRQ
requests. Its outputs feed the shared interrupt boundary described above.

Startup validation uses the pinned Mooneye equivalent sequence `LDH (LCDC),A`,
N NOPs, then `LD A,(DE)`. Relative to the LCDC T4 commit, the following read's
T4 commit is `4*N+8` ticks later. Verified mode reads bracket the first mode3
transition between 76 and 80 ticks; LY reads bracket the first increment between
448 and 452 ticks. These are observation brackets, not single-dot measurements.
The selected source's delayed mode signal fits the former bracket; the complete
controller is checked against the literal table with pre-edge CPU reads.
The LY153/comparison, STAT-write and window sections define their additional
directed boundaries.

### LY153 and ordered LYC comparison

This digital mapping uses the pinned
[SameBoy display sequence](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/display.c#L2217)
and its distinct readable flag and IRQ coincidence latch. SameBoy is Expat
licensed behavior research, not imported implementation. The DMG table on
page 32 of [TCAGBD](https://github.com/AntonioND/giibiiadvance/blob/ccb40c3cf7d9efec538858a36d4ab69bb4d0ce5c/docs/TCAGBD.pdf)
(CC-BY4.0) corroborates the four-dot readable interval and coarse comparator
samples. That document explicitly warns that it is old and contains errors;
it is corroboration, not the sole authority or an exact silicon claim.

A0 is the existing phase-two LY152-to-153 boundary. The first LY increment at
451 ticks after LCD enable fits the independent 448/452 read brackets; adding
152 lines of 456 dots places the first A0 at 69763. This is the declared project
phase mapping. It does not claim a measured sub-T hardware edge. Keep the
renderer line counter and the 70224-dot normal frame recurrence unchanged.

| Edge relative to A0 | Readable LY | Comparison value | Readable STAT2 | LYC IRQ latch |
|---|---|---|---|---|
| -2 |152 | Invalid |0 | Retain |
| 0 |153 | Invalid |0 | Retain |
| +4 |0 |153 | Equality with LYC | Equality with LYC |
| +6 |0 | Invalid |0 | Retain |
| +10 |0 |0 | Equality with LYC | Equality with LYC |

An invalid comparison clears only readable STAT2; it does not force a fall in
the coincidence IRQ source. The enabled mode sources still OR with that latch.
The [DMG LYC write path](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/memory.c#L1452)
recomputes after the write. At a legal T4/A commit, first advance the natural
comparison using old LYC, then apply the new LYC and recompute immediately if
the comparison value is valid. During an invalid interval, retain the IRQ
latch and keep readable STAT2 zero. Do not postpone this write response to the
next quarter. LCD-off retention and reset initialization remain separate rules.

Preserve both ordered changes in the shared STAT condition. Let S0 be the
preceding final condition, S1 the natural after-A condition with old LYC, and
S2 the final condition after the CPU write. The event is
`(!S0 && S1) || (!S1 && S2)`. Each condition includes the mode-source OR and the
appropriate ordinary STAT transient state. Thus 0-to-1-to-0 and 1-to-0-to-1 each
produce one event, while a continuously high mode source prevents a false
edge. Store final history S2, not S1. Publish the event during A-to-B for the
shared IRQ owner to sample before B, even if the final condition is low; clear
that one-system-edge event after B without needing another emulated dot.
Host pause after A must not lose or repeat the event. CPU retirement and IF
write priority remain owned by the shared interrupt boundary above.

Before accepting this timing implementation, directed tests must check LYC 0,
152,153 and nonmatching values; legal T4 writes around each interval; both
ordered rise/fall cases; a held-high mode source; pause/reset; and unchanged
normal frame recurrence. The controller keeps the ordinary quarter comparison history outside this
window. Its readable and IRQ histories are separate, and valid CPU writes
update both histories so a later sample cannot restore a stale comparison.

### OAM scan and fetch port

The scanner exposes a seven-bit pair address and a phase: 0 idle, 1 Y/X scan,
2 tile/attribute fetch. The sixteen-bit response places the lower-address byte
in bits7:0. A scan examines forty OAM entries in order, retaining at most the
first ten Y matches, including hidden X positions. Matching the current pixel
position chooses the lowest retained index; finishing that fetch removes that
match. The renderer's increasing X position supplies DMG X priority.

Phase1 alternates request/capture dots and saves the captured Y/X on the next
dot. DMA-active suppresses the Y/X capture as in the selected source; its
existing captured pair is retained. Phase2 samples the arbitrated pair at object
fetch phase1. The external owner #132 controls the actual bus pair during DMA;
these scan observations do not themselves implement or prove OAM corruption.
A promised sample without response-valid faults without stretching a dot.
There is no local OAM RAM, FF46 register or DMA engine. Reset initializes all
scan state independently of gb_tick; LCD-off tick handling retains the selected
source's first-line scan behavior. Mode/startup integration must validate the
result against the instruction-relative observation table.

CPU T4 remains aligned across HALT, wake and interrupt entry: the CPU advances its
four-phase bus cycle on every emulated tick even while inactive, and activates
wake only after T4. Host pause holds both domains' emulated phase. LCDC enable at
T4 starts PPU quarter0 on the following T1. While LCDC is enabled, a CPU commit
therefore occurs at PPU quarter3. The integrated wrapper asserts this invariant;
`io_commit && gb_tick` alone is insufficient. Core reset clears both phases and
LCDC, so a new enable establishes alignment again. A stopped system preserves
phase; it does not independently restart either counter.

LCD disable follows the natural A observation with old LCDC/LYC/enables. It
retains the resulting readable coincidence, coincidence IRQ latch and combined
STAT line, including a natural rising event for B. Readable LY/mode become zero
and the comparison value resets to zero; these do not recompute the retained
flag or interrupt histories.

While LCD is off, STAT/LYC writes store their writable values without changing
those histories or generating an interrupt. Enable preserves the prior combined
line. The first T1 captures LY0 versus current LYC through the ordinary comparison
phase, including its early falling and delayed rising rules. No synthetic low
level creates a restart edge. This phase is the declared project mapping;
Mooneye on/off checks establish instruction-scale behavior, not a sub-T anchor.
Global/core reset initializes histories to zero independently of the dot enable.
Host pause preserves retained state; an A event still clears after its B sampling.

The pinned [SameBoy LCD update and shutdown model](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/display.c#L523)
returns before updating coincidence/shared IRQ state while disabled. Its shutdown
resets readable LY/mode and comparison value separately. This is model
corroboration, not an additional silicon measurement. The pinned
[Mooneye on/off checks](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/ppu/stat_lyc_onoff.s)
distinguish retained coincidence, equal-to-equal restart without an interrupt,
and unequal-to-equal restart with an interrupt.

The register helper stores LCDC, SCY, SCX, LYC, BGP, OBP0/1, WY, WX and STAT
interrupt enables using generated addresses and direct-entry peripheral fill.
LY and STAT mode/coincidence readback come from timing; writes to LY have no
stored effect. FF46 is not selected. It exposes qualified LCD on/off transitions
and the STAT-write commit to integration; the STAT glitch's duration and IRQ
ordering belong to the timing/interrupt contract, not an unqualified address
level. Every stored write uses the existing A-edge commit and shared macros.

The position controller counts raw X from0 through167, including the eight
leading positions used for clipped objects/window fetches. Visible X is raw X
minus8. Fine SCX is latched at the first background map-fetch boundary; later coarse
SCX still contributes to map addressing. Background first-fetch, window first-
fetch, object fetch and line end pause pixel advance. The terminal rawX167 has
one explicit source event even though advance is paused on that edge; otherwise
the last visible pixel would be lost. No other paused edge publishes a pixel.
The A-edge source snapshot therefore contains exactly X0 through159 before a
line completes. Composed tests, rather than the position counter itself, check
that ordering and frame size.

The pinned [Mealybug SCX probe](https://github.com/mattcurrie/mealybug-tearoom-tests/blob/70e88fb90b59d19dfbb9c3ac36c64105202bb1f4/src/ppu/m3_scx_low_3_bits.asm) reports that low SCX bits appear to
be sampled at the start of the first B01s map fetch. This refines the earlier
shorthand “line start”; it is not an asserted direct single-dot measurement.
The controller latches on its first map-fetch phase0 using the A pre-edge
convention. With the continuous CPU phase, startup first-map sampling is T3 and
normal-line sampling is T2; CPU writes occur only at T4. Composed checks therefore
use the nearest legal T4 before and after sampling. A simultaneous helper input
would use its pre-A value, but it is not a reachable CPU write under this phase
binding. Later low-bit writes cannot change the selected fine-scroll delay.

WY matching is qualified by Window enable before being latched. The pinned
MiSTer qualification is independently corroborated by [GateBoy CPU-B gate PALO](https://github.com/aappleby/metroboy/blob/36797ad4cf77b3e04ffe45716218a79b5280076a/src/GateBoyLib/GateBoyPixPipe.cpp) feeding
SARY/REJO; Pan Docs' short Y-condition description omits that qualification.
The selected digital controller maps this to quarter phase0 (an integration inference, not a measurement from gate names) and retains it
until VBlank/LCD reset. Tests distinguish changing WY/enable before and after
that sample, rather than assuming only a scanline-boundary comparison.
For static WX0 with Y qualified before mode3, BG/window enabled, and no object
stalls or midline writes, first visible window columns for fine SCX0..7 are
7,9,10,11,12,13,14,14. At fine7, the old WX match delays the second pipe load;
load priority then places column8 at internal pixel2 and column14 at visible0.
This follows the selected [MiSTer reload ordering](https://github.com/MiSTer-devel/Gameboy_MiSTer/blob/7a5ff50528cd9c1d13ffb675e7df8506bffaa078/rtl/video.v#L842)
and independently ordered [GateBoy pixel gates](https://github.com/aappleby/metroboy/blob/36797ad4cf77b3e04ffe45716218a79b5280076a/src/GateBoyLib/GateBoy.cpp#L1064).
Pinned SameBoy213a gives column15 for fine7; that model discrepancy remains
explicit. This rule defines the selected digital spatial result, not measured
LCD latch phase or a mode3-duration claim.

For WX166 after a new WY match, the trigger line remains background but advances
the internal window row. With no object stalls and fine SCX0, the next line
starts at window column8,row1. If WX becomes255 before the following line,
the retained match still produces column8,row2 once; the next line is background.
This selected carry behavior follows the retained match in the same MiSTer
source and [SameBoy's carry path](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/display.c#L2080),
whose timing approximation does not establish an exact physical edge.

A retained WY match can also suppress a normal BG reload when Window enable is
off. The selected DMG reload rule still uses that WX match; a suppressed load
allows an emptied shift pipe to emit raw BG color0 before the delayed tile.
For fine SCX0 and WX47 held through the line, pixels0..39 use BG columns0..39,
pixel40 uses raw0 through BGP, and pixels41..159 use BG columns40..158. This
is the disabled-window reload effect explicitly described by the pinned MiSTer
source, separate from LCD-off blanking or clearing the WY latch.

### Renderer composition

`n2m_ppu` connects the owned register, timing, position, window, fetch, object,
shift and mixer blocks. Its VRAM address mux retains map, background low/high,
then object low/high priority. Responses are associated with the preceding
request before the capture edge; overlapping phase flags do not grant multiple
independent memory responses. The first mode3 map-fetch phase0 qualifies the
fine-scroll latch before that line's first fetch completes. An explicit sampled
bit prevents a window-induced phase0 restart from recapturing it in the same line.

The public source carries valid/start/shade, X/Y, epoch and dot, plus abort,
blank-assert and display-eligible events. Epoch and dot-before are supplied by
the shared system owner. The source tag captures dot-before plus1 at A, the
completed-T count required by the shared frame interface. A captures all source fields;
they are consumed on B without palette or coordinate recomputation. LCD-disable
or a newly detected memory fault wins over a would-be pixel at A. The first
complete enabled frame forwards shade0 and is not display-release eligible;
only subsequent complete rendered frames qualify. Core reset cancels pending
pixels; an already committed blank assertion is retained through B so resetting
PPU control cannot silently undo a presentation request. VGA owns the persistent
blank state, qualifying acknowledgement, actual swap and public observer.
