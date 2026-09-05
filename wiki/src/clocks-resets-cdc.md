# Clocks, resets, and CDC

Status: planned implementation contract for
[#29](https://github.com/amichai-bd/nand2mario/issues/29). This defines requirements;
PLL generation, RTL simulation, fit, timing closure, and physical proof remain
outstanding in [GAP-006](../preflight-gaps.md#gap-006-clock-reset-and-cdc-plan).

## Clock domains

Target DE10-Lite `10M50DAF484C7G`. Use `MAX10_CLK1_50` on `PIN_P11`, nominal
50 MHz, as `clk_sys` and the PLL reference. These are manual-derived design
constraints, not verification of the connected board. The second 50 MHz input,
ADC clock, SDRAM, and physical audio are unused in the initial fixed-ROM design.
Adding SDRAM requires a separate storage/timing contract before integration.

| Name | Nominal rate | Consumers | Required accuracy |
|---|---|---|---|
| `clk_sys` | 50,000,000 Hz; 20 ns | Host UART/control, memories, DMG logic, frame writes | Board reference within +/-100 ppm; prove before board acceptance |
| `gb_tick` | 4,194,304 enables/s | One DMG dot/T-cycle per enabled rising `clk_sys` edge | Exact average relative to nominal reference; bounded quantization below |
| `clk_pix` | 25,200,000 Hz; 39.68253968 ns | VGA counters, frame reads, registered RGB/sync | Exact PLL ratio 63/125 relative to reference; inherits its ppm error |

Only `clk_sys` and `clk_pix` clock sequential logic. `gb_tick`, UART baud ticks,
and memory completion are enables, never fabric-generated clocks. CPU, PPU,
timers, DMA, and host registers share `clk_sys`; their synchronous arbitration
must finish before the applicable emulated edge without silently stretching DMG
time. Missing service is an assertion/error, not a dropped tick.

Generate the pixel clock through MAX 10 ALTPLL on a global network, nominal
50% duty and zero requested phase. The candidate counters `M=63, N=5, C=25`
give 630 MHz VCO, 10 MHz PFD, and 25.2 MHz output by the vendor ratio equation.
This is a feasibility candidate, not a proven IP configuration. The pinned
Quartus generation and fit must confirm legal counters, routing, duty, jitter,
and the requested output ratio; record the actual generated settings. Do not
silently substitute 25 MHz. No clock switching or dynamic PLL reconfiguration.

The +/-100 ppm reference bound is a project acceptance requirement, not a
claimed oscillator specification or measurement. It puts `gb_tick` within
+/-419.4304 Hz and `clk_pix` within +/-2,520 Hz. Simulation uses nominal clocks;
board clock verification and monitor acceptance remain separate evidence.

## Exact emulated time

At each active `clk_sys` rising edge, calculate `sum = phase + 32768` from the
old unsigned phase. If `sum >= 390625`, assert the enable for this edge and set
`phase = sum - 390625`; otherwise do not enable and set `phase = sum`. Reset
sets phase to zero. Use at least 19 bits for phase and a sum wide enough for
423392. Consumers see this edge's carry; do not accidentally add a pipeline dot.

From reset, after N active system edges the tick count is exactly
`floor(N * 32768 / 390625)`. The first tick is edge 12; subsequent gaps are 11
or 12 edges. Each 390625-edge period emits 32768 ticks. Each tick arrives less
than one system period late relative to its ideal continuous edge: less than
20 ns nominal. This quantization has zero cumulative average error and preserves
DMG event order; it is not a claim of original crystal waveform identity.

A normal-speed M-cycle spans four dot enables. One acceptance frame interval
is 456 * 154 = 70224 dots, nominally 16.74270630 ms (about 59.72750057 Hz).
This interval exists even when the emulated LCD is disabled. PPU mode timing,
LCD enable behavior, STOP, and instruction semantics belong to their own
contracts; they must not redefine the acceptance time unit.

Run a separate system-cycle watchdog, not one driven by DUT frame_done. For K
frame intervals from phase zero, the required elapsed active edges are
`ceil(K * 70224 * 390625 / 32768)`. Account explicitly for startup/reset edges
outside that interval. Instruction HALT must not halt this timebase or PPU.
A deliberate host pause freezes emulated state and phase at a dot boundary;
UART, CDC handshakes, and VGA continue. Resume starts from retained phase with
no catch-up ticks. Acceptance runs prohibit host pauses during their run bounds.

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

## Reset and run control

A small always-running `clk_sys` reset controller uses the board reset request
and FPGA configuration startup. Configuration must initialize PLL reset asserted,
qualification counters and readiness to zero, and both domain reset-release
chains to the asserted state, even if the button is never pressed. Generated
implementation must prove a supported MAX 10 power-up initialization or wrapper
reset source establishes these values without a running pixel clock.
The board wrapper maps the active-low manual
reset input; #28 must verify its pin/polarity on hardware. Assert reset without
waiting for a clock. After release, synchronize the raw input through two flops
and require 500000 consecutive released system edges (10 ms nominal) before
releasing PLL `areset`. Any reassertion restarts the qualification.

Keep PLL reset independent of `locked` to avoid a circular reset dependency.
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
or equivalent reviewed virtual-clock I/O constraints. #28 owns pin, I/O standard,
board electrical proof and any additional external budget. Unused board ports
are absent from the top. SDRAM constraints cannot be inferred from this plan.

## Required verification

- Tick simulation checks the first edge, 11/12 spacing, full 390625-edge count,
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
A contract merge closes #29's design
criteria; it does not close GAP-006 or GAP-012 implementation evidence.
[Timebase/reset implementation](https://github.com/amichai-bd/nand2mario/issues/79)
and [VGA/frame bridge implementation](https://github.com/amichai-bd/nand2mario/issues/80)
own the remaining generated design, simulation, and timing evidence.

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
