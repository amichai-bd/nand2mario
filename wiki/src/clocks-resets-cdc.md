# Clocks, resets, and CDC

[Clocking and timebase](rtl/clocking/MAS_clocking.md), frame crossings and bounded
composed verification have simulation and generated FPGA timing evidence.
The remaining physical limits are recorded in
[GAP-006](../preflight-gaps.md#gap-006-clock-reset-and-cdc-plan).

## Clock domains

The [clocking implementation](rtl/clocking/MAS_clocking.md) supplies the
25 MHz system domain. Timing acceptance must use this clock configuration.

Target DE10-Lite `10M50DAF484C7G`. Use `MAX10_CLK1_50` on `PIN_P11`, nominal
50 MHz, as `clk_reference` for reset bootstrap and both system/pixel PLLs. These are manual-derived design
constraints, not verification of the connected board. The second 50 MHz input,
SDRAM and physical audio are unused in the initial fixed-ROM design. The
[board controls contract](fpga-controls.md) adds the independent N5 ADC clock
and its dedicated PLL for physical input acquisition.
Adding SDRAM requires a separate storage/timing contract before integration.

| Name | Nominal rate | Consumers | Required accuracy |
|---|---|---|---|
| `clk_sys` | 25,000,000 Hz; 40 ns | Host UART/control, memories, DMG logic, frame writes | Board reference within +/-100 ppm; prove before board acceptance |
| `gb_tick` | 4,194,304 enables/s | One DMG dot/T-cycle per enabled rising `clk_sys` edge | Exact average relative to nominal reference; bounded quantization below |
| `clk_pix` | 25,200,000 Hz; 39.68253968 ns | VGA counters, frame reads, registered RGB/sync | Exact PLL ratio 63/125 relative to reference; inherits its ppm error |

Product logic uses `clk_sys` and `clk_pix`; the Intel ADC hard block additionally
uses its dedicated clock and vendor crossing defined by the board contract.
`gb_tick`, UART baud ticks,
and memory completion are enables, never fabric-generated clocks. CPU, PPU,
timers, DMA, and host registers share `clk_sys`; their synchronous arbitration
must finish before the applicable emulated edge without silently stretching DMG
time. Missing service is an assertion/error, not a dropped tick.

Generate system and pixel clocks through two parallel MAX 10 ALTPLLs from
the same 50 MHz reference. The system PLL divides by 2. The
[dedicated clock-pin connections](https://docs.altera.com/r/docs/683047/21.1/max-10-clocking-and-pll-user-guide/clock-pin-to-pll-connections)
support two PLLs from the reference group. Use no PLL cascade. Generate the
pixel clock on a global network, nominal
50% duty and zero requested phase. The candidate counters `M=63, N=5, C=25`
give 630 MHz VCO, 10 MHz PFD, and 25.2 MHz output by the vendor ratio equation.
The system PLL uses `M=104, N=8, C=26`, with 650 MHz VCO and
6.25 MHz PFD. Each pinned Quartus generation and fit must confirm counters, routing, duty, jitter,
and the requested output ratio; record the actual generated settings. Do not
silently substitute 25 MHz. No clock switching or dynamic PLL reconfiguration.

The +/-100 ppm reference bound is a project acceptance requirement, not a
claimed oscillator specification or measurement. It puts `gb_tick` within
+/-419.4304 Hz and `clk_pix` within +/-2,520 Hz. Simulation uses nominal clocks;
board clock verification and monitor acceptance remain separate evidence.

## Exact emulated time

At each active `clk_sys` rising edge, calculate `sum = phase + 65536` from the
old unsigned phase. If `sum >= 390625`, assert the enable for this edge and set
`phase = sum - 390625`; otherwise do not enable and set `phase = sum`. Reset
sets phase to zero. Use at least 19 bits for phase and a sum wide enough for
456160. Consumers see this edge's carry; do not accidentally add a pipeline dot.

From reset, after N active system edges the tick count is exactly
`floor(N * 65536 / 390625)`. The first tick is edge 6; subsequent gaps are 5
or 6 edges. Each 390625-edge period emits 65536 ticks. Each tick arrives less
than one system period late relative to its ideal continuous edge: less than
40 ns nominal. This quantization has zero cumulative average error and preserves
DMG event order; it is not a claim of original crystal waveform identity.

A normal-speed M-cycle spans four dot enables, requiring 23 or 24 system edges.
Every memory service must finish within 23 edges; the shortest single-dot
interval is 5 edges. Pipelining cannot borrow an extra emulated cycle. One acceptance frame interval
is 456 * 154 = 70224 dots, nominally 16.74270630 ms (about 59.72750057 Hz).
This interval exists even when the emulated LCD is disabled. PPU mode timing,
LCD enable behavior, STOP, and instruction semantics belong to their own
contracts; they must not redefine the acceptance time unit.

Run a separate system-cycle watchdog, not one driven by DUT frame_done. For K
frame intervals from phase zero, the required elapsed active edges are
`ceil(K * 70224 * 390625 / 65536)`. Account explicitly for startup/reset edges
outside that interval. Instruction HALT must not halt this timebase or PPU.
A deliberate host pause freezes emulated state and phase at a dot boundary;
UART, CDC handshakes, and VGA continue. Resume starts from retained phase with
  no catch-up ticks. Acceptance runs prohibit host pauses during their run bounds
  except the explicitly approved [v0.9 full-frame acquisition](dv/springtrail/SPEC.md#v09-milestone).

## VGA timing

Use the board manual's 640 by 480 count geometry, with a selected 25.2 MHz
pixel clock: 800 pixels per line, 525 lines per frame, exactly 60 nominal frames
per second. This deliberate rate selection is separate from DMG timing and
must pass the actual monitor test before board acceptance.

| Axis | Active | Front porch | Active-low sync | Back porch | Total |
|---|---|---|---|---|---|
| Horizontal pixels | 640 | 16 | 96 | 48 | 800 |
| Vertical lines | 480 | 10 | 2 | 33 | 525 |

Counters start at active coordinate (0,0). HSync is low at x=656..751; VSync
is low at y=490..491. RGB is zero outside active video. Use three-times scaling
of 160 by 144, centered at x=80..559 and y=24..455; border RGB is zero. Register
RGB, sync, and valid with matching memory-read latency. Pixel shade conversion
belongs to the VGA implementation contract; this page specifies its timing.

## System service budgets

The minimum five-edge dot interval and 23-edge M-cycle are hard deadlines.
The following bounds count system edges from acceptance or a stable request;
none depends on average tick spacing. Owner contracts retain the detailed
ordering, collisions and cancellation rules.

| Owner | Required service | Worst bound at 25 MHz | Deadline and independence |
|---|---|---|---|
| [CPU memory port](rtl/memory/MAS_memory.md#prepared-and-committed-operations) without DMA | Tagged synchronous store response | One read edge; response valid before the following edge | Request is prepared before T1 and consumed at T4; no added T-cycle |
| [DMA and OAM](rtl/dma/MAS_dma.md#corruption-qualification-and-combined-service) | Three corruption rows, uncovered DMA byte, next operands/source/destination and CPU response | Last tagged CPU capture at A+22 | Next T4 cannot precede A+23; source and destination pair read at A+20 use distinct banks |
| [PPU](rtl/ppu/MAS_ppu.md) VRAM and OAM | Read/tag the requested byte or pair | One read edge; two edges allowed for requester observation | Before the next dot at least five edges away; dedicated B ports, same-pair collision gating and pending-pair forwarding preserve ownership |
| [Interrupts](rtl/interrupts/MAS_interrupts.md) and JOYP | Resolve same-edge events, writes and acknowledgement | Combinational next-state observation | CPU samples IF/IE before T3; independent of the raw memory service slot |
| UART ROM, packet and response memories | Tagged synchronous reads and whole-byte writes | One read edge | Transport state waits for valid; ROM loading holds emulation reset, packet stores do not share CPU RAM ports |
| [Frame bridge](rtl/vga/MAS_vga.md) | Write one completed shade | One system edge | At most one shade per dot; pixel reads use the separate clocked port |
| [Snapshot](rtl/snapshot/MAS_snapshot.md) | Copy 5760 packed bytes into immutable host storage | Two system edges per byte, 11520 edges (460.8 us), plus command completion | Background copy has dedicated banks and cannot stall Game Boy ticks; host reads take one edge |
| Physical controls | Debounce, pair acquisition and freshness | 125000 / 25000 / 500000 system edges | Preserve 5 ms / 1 ms / 20 ms durations; ADC hard-block clock stays independent |

UART phase accumulators use 25000000 Hz and preserve the configured baud rate.
The packet timeout remains derived from milliseconds. The physical default is
115200 baud; accelerated verification uses at most 3125000 baud to retain the
minimum eight system clocks per bit. Reference reset qualification remains
500000 raw 50 MHz edges (10 ms); lock qualification remains 1024 system samples
(40.96 us), followed by each destination's two release edges. Host pause stops
only Game Boy enables. Already accepted services may drain; reset cancels them.

The [system composition](rtl/system/MAS_system.md) includes the timer.
Serial-transfer and audio owners are still incomplete in the bounded v0.5
composition. Their existing milestone requirements remain open; this table
does not invent a service guarantee for missing implementations.

## Reset and run control

A small always-running 50 MHz `clk_reference` reset bootstrap uses the board reset request
and FPGA configuration startup. Configuration must initialize PLL reset asserted,
qualification counters and readiness to zero, and both domain reset-release
chains to the asserted state, even if the button is never pressed. Generated
implementation must prove a supported MAX 10 power-up initialization or wrapper
reset source establishes these values without a running pixel clock.
The board wrapper maps the active-low manual
reset input; [board bring-up](board-bring-up.md) records its verified pin and
polarity on hardware. Assert reset without
waiting for a clock. After release, synchronize the raw input through two flops
and require 500000 consecutive released reference edges (10 ms nominal) before
releasing PLL `areset`. Any reassertion restarts the qualification.

Both PLLs share the reference-qualified reset. Readiness requires both raw
lock signals; either loss resets both product domains. Keep PLL reset independent of `locked` to avoid a circular reset dependency.
Synchronize `locked` through two system flops; require 1024 consecutive asserted
samples before readiness. A raw lock loss asynchronously clears readiness and
asserts both domain resets. Each domain has its own two-flop reset-release
chain: asynchronous assertion, deassertion only after two rising destination
edges with readiness continuously true. The always-running reset controller
must not depend on readiness for its own release. Never gate a clock with reset.

Global reset clears transport state, frame ownership, mailbox request/ack
phases, valid flags, counters, and emulated state. RAM contents need not be
cleared; invalid banks cannot be displayed. Drive black until the first complete
frame; reset drives RGB zero and sync inactive. Wait for both domain-ready
levels, each synchronized into the peer domain, before offering or consuming a
frame. A pixel clock stopped during reset cannot complete reset release or grant
a bank. A clock stopped after readiness while PLL lock remains high is not
detected by this controller: ownership remains held, no acknowledgement occurs,
and presentation may freeze while emulation continues. This contract provides
lock-loss reset, not a separate clock-failure detector.

A host emulated-core reset is synchronous in `clk_sys`; it clears DMG state,
tick phase, and any partial writer frame, but keeps UART, PLL, VGA and frame
ownership handshakes alive. Already completed pending/displayed frames remain
immutable until normal release. Keep the last complete image until replacement.
A host load stops execution and resets the core before resume; ROM writes while
running are rejected by the host interface contract. Distinguish CPU HALT from
host pause and from either reset. The host protocol must acknowledge completion
only after the requested core transition, not on packet reception.

## Crossing and ownership inventory

Use three independent dual-clock frame banks, each 160 * 144 * 2 bits, with
system-clock write and pixel-clock read ports. Store final DMG shade indices.
A bank has exactly one owner: writer, pending immutable offer, display, or free.
The CDC mailbox carries a bank ID and frame sequence as stable bundled data;
it does not synchronize each data bit independently.

On global reset, bank 0 belongs to the writer, bank 1 to the invalid display,
and bank 2 is free. At completion of all 23040 pixels, if no offer is pending,
the writer holds the bank ID/sequence stable and toggles request. It switches
to a free bank before the next frame. With an offer still pending at the next
completed frame, discard that newly completed writer frame and reuse its bank;
never overwrite the offered or displayed bank, and never stall emulation.
Count discarded presentation frames. Every source frame remains available to
the verification observer before presentation selection, so VGA drops cannot
hide a v0.9 reference mismatch.

The pixel side passes request through two flops, then waits one further pixel
edge before capturing its stable bundle. At the first x=0,y=480 boundary after
capture, swap the display bank and acknowledge by copying the request phase.
Do not swap in active video. If there is no request, repeat the previous complete
frame. The acknowledge returns through two system flops; only then does the
producer free the previous display bank and allow another offer. Process reset before acknowledgement, and acknowledgement before same-edge
frame completion. Keep bundle stable until acknowledgement. The producer tracks the old display bank from
the last acknowledged offer, so no unsynchronized bank-return bus is needed.

| Crossing | Structure and ownership rule |
|---|---|
| Raw board reset -> reset controller | Async assertion; two-flop release sampling plus qualification |
| PLL lock -> reset controller/domains | Async reset assertion; two-flop status sampling and lock qualification |
| UART RX -> system | Two-flop level synchronizer before baud sampling; no use of first stage |
| Domain-ready -> peer | Two-flop level synchronizer; global reset clears both |
| Frame offer system -> pixel | Two-flop toggle plus delayed stable-bundle capture; one outstanding offer |
| Frame acknowledgement pixel -> system | Two-flop toggle; source frees prior display only on acknowledgement |
| Frame pixels system -> pixel | Dual-clock RAM; read/write ownership disjoint for each bank |
| Pixel status/counters -> host | Separate request/ack snapshot mailbox, stable bundle until ack; never sample a live multi-bit counter |
| Host commands/input -> DMG | Same system domain; ordered synchronous handshakes, no CDC |

No other crossing is permitted without updating this inventory. Host frame
readback must take a stable snapshot or explicit bank lease in its contract;
it may not read a changing writer bank or steal display ownership. Do not add
a second writer or a reset that independently clears one end of a live mailbox.

## Timing constraints

Use Quartus Prime Lite/Standard TimeQuest for the exact MAX 10 part. Define the
50 MHz input with `create_clock -period 20.000`, derive ALTPLL clocks with
`derive_pll_clocks`, then `derive_clock_uncertainty`. Also analyze the upper
reference bound with input period 19.998 ns. Generated clocks must retain the
actual input/output relationship; tick enables get no clock declaration.

Keep both related domains timed by default. Do not apply a blanket asynchronous
clock-group exception: that can hide the frame bundle's physical settling bound.
Cut only each asynchronous input/control launch to its named first synchronizer
D pin. Time all subsequent synchronizer stages normally; preserve/identify the
chains for Quartus metastability analysis. For the frame bundle, require source
register Q to destination capture D maximum datapath delay 20 ns, with no
false-path exception overriding it. The two synchronizer stages plus extra
capture edge provide settling time; this is a bundled-data requirement, not
independent-bit synchronizers. Use the analogous 20 ns bound on status snapshots.

Reset exceptions cover raw asynchronous assertion into reset synchronizers;
check recovery/removal from synchronized domain reset release to consumers.
Require every timing exception's endpoints to match nonempty exact collections,
with a stated crossing and rationale. Never silence all paths from a clock or
all registers matching a broad wildcard. Review dual-clock RAM read-during-write
behavior and prove ownership excludes same-bank cross-port collisions.

For each board output, require an explicit register-to-pin bound: VGA RGB/sync
maximum 10 ns and skew between those outputs at most 2 ns; UART TX maximum
20 ns. These are internal design budgets, not measured cable/monitor guarantees.
Constrain them with explicit datapath max/min (minimum 0 ns) and skew checks,
or equivalent reviewed virtual-clock I/O constraints.
[Board bring-up](board-bring-up.md) records the pin, I/O standard and board
electrical proof; any additional external budget stays with it. Unused board ports
are absent from the top. SDRAM constraints cannot be inferred from this plan.

## Required verification

- Tick simulation checks the first edge, 5/6 spacing, full 390625-edge count,
  exact formula over multiple periods, reset phase, and pause/resume. An
  independent integer oracle computes cumulative ticks; an altered numerator
  and a dropped tick each fail for the expected mismatch.
- VGA simulation checks every coordinate, sync width, porches, 420000-edge frame,
  matched RGB/control latency, black border, and source coordinate mapping.
- Reset simulation varies assertion/release phase, bounces the button, removes
  PLL lock, stops/restarts the pixel clock, and resets with an offer outstanding.
  No early release, stale acknowledgement, partial-frame display, or write to
  a non-owned bank is allowed. Model asynchronous arrival with variable phase;
  digital simulation does not establish analog metastability performance.
- Frame tests use distinguishable pixels/sequence IDs, faster and slower producer
  rates, delayed acknowledgement, pause, and core reset. Check every displayed
  pixel belongs to one completed frame, swaps occur only at the stated boundary,
  and repeats/discards leave DMG time uninterrupted. Illegal bank reuse and a
  mid-active swap must fail deliberately. All bounds have independent watchdogs.
- Generate the actual PLL and fit the reset/tick/frame design for the exact part.
  Retain tool version, settings, commit, input hashes, seeds, PLL/clock reports,
  RAM inference/resource use, exceptions, CDC/metastability report, and TimeQuest
  setup/hold/recovery/removal/minimum-pulse reports through the builder. Both
  nominal and upper-frequency analyses require nonnegative slack and no
  unexplained warnings, ignored constraints, or unconstrained paths. Prove
  frame RAM inference rather than assuming bit count establishes fit.

Questa simulation must compile, elaborate, run, and check both positive and
negative results. Questa and physical execution follow the
[current authorization](../agents/bootstrap-plan.md#verification-and-hardware-authorization).
The [clocking](rtl/clocking/MAS_clocking.md) and [VGA/frame bridge](rtl/vga/MAS_vga.md)
contracts own generated design, simulation and timing requirements. These checks
do not establish the remaining physical acceptance in GAP-012 and
[#417](https://github.com/amichai-bd/nand2mario/issues/417).

## Primary references

- [Terasic DE10-Lite manual][board], version 1.7, October 17, 2022, clock table
  3-2 and VGA tables 3-9/3-10. Download SHA-256:
  `ab2c47e5a7e4ac26874013bfe05df31e2d498bc9a7f9f6b33bd931c64db848ac`.
- [Pan Docs rendering][pan-render] and [specifications][pan-spec], commit
  `fe246067b695b5404a4a6a47efb4fd6d921ececb`, CC0-1.0; research only, no imported
  code. These establish dot/frame units, not a complete PPU contract.
- [MAX 10 clocking/PLL guide][pll], document 683047, version 21.1, sections 2.3
  and 2.3.6; ratio/VCO limits and reset/lock controls. Vendor documentation is a
  reference, not redistributed source.
- [Quartus Standard Timing Analyzer][timing], document 683068, version 18.1,
  section 2.3.8; base/generated clocks, uncertainty, and endpoint constraints.
  Apply the actual installed tool's reports before accepting implementation.

[board]: https://www.terasic.com.tw/cgi-bin/page/archive_download.pl?Language=English&No=1021&FID=a13a2782811152b477e60203d34b1baa
[pan-render]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Rendering.md
[pan-spec]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Specifications.md
[pll]: https://docs.altera.com/r/docs/683047/21.1/max-10-clocking-and-pll-user-guide/pll-control-signals
[timing]: https://docs.altera.com/r/docs/683068/18.1/intel-quartus-prime-standard-edition-user-guide/example-circuit-and-sdc-file
