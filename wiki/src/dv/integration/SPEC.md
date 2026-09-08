# Integration smoke

This bounded simulation implements [#140](https://github.com/amichai-bd/nand2mario/issues/140).
It does not replace the complete release acceptance in
[#88](https://github.com/amichai-bd/nand2mario/issues/88) or any component's acceptance.
Runtime evidence and measured regression tiers are recorded in
[PR159](https://github.com/amichai-bd/nand2mario/pull/159).

## Original program and oracle

The [original program](../../../../src/dv/integration/program.asm) uses the
delivered assembler, linker and direct-profile packager. Its separate literal
instruction table verifies all bytes, including the entry stub and eight-byte
VBlank handler. No DUT array initializes ROM or RAM. The real Python Client
identifies the endpoint, loads all32768 bytes, reads every byte back, verifies
the paused profile, applies INPUT0 and sends RUN.

The [complete retirement oracle](../../../../src/dv/integration/retirement.json)
contains68 instruction events and one interrupt event. It fixes every48-byte
ABI field before simulation. Exactly LOAD_BEGIN and LOAD_END reset the core,
so these events use epoch2. The frontend consumes four initial dots; the149
instruction/entry M cycles then finish at dot600. NOP retires at8, interrupt
entry at212, RETI at280 and terminal HALT at600. The IRQ's final cycle fetches
the handler; it does not add another preparation cycle.

The program writes3C toC000, reads its E000 echo, adds05 and writes41 toC001.
It enables and requests VBlank through real IE/IF, executes EI/NOP and services
one interrupt. Stack writes are02/22/01/20 atDFFD/DFFC/DFFB/DFFA. The handler
writesA7 toC002, restoresAF and returns. The main program disables IE, writes
eight tile rows55/33 with LCD off, sets identity paletteE4 and enables LCDC91.
Terminal state is A91/F80, BC3355, DE0000, HL8010, SPDFFE, PC025C, IME0 and
HALT1. PPU requests may later set IF, but IE0 keeps this CPU asleep.

## Pixel interval

The LCDC write completes at dot592; its pre-edge dot identity is591. Its LDH
instruction retires at596 after the next fetch. Under the delivered PPU digital
mapping, the first normal frame starts at591+70317=70908. For every x0..159 and
y0..143, require dot70908+456*y+x, shade x modulo4, exact coordinates and epoch2.
The last selected pixel is at136275. Check all23040 pixels and the single start
indication. Also check the preceding complete startup frame's23040 forced-white
pixels and ineligible display status. This preserves the PPU startup contract;
the timing anchors are a selected digital projection, not new silicon measurements.

## Composition

The DV composition instantiates the real UART, timebase, CPU, memory CPU port,
explicit Intel stores, interrupt owner and PPU. CPU video service honors the
PPU's access permission and tags registered data before the later T4 consumer.
PPU VRAM/OAM responses use the shared stores' read ports. CPU ROM preparation is
disabled until image validation, avoiding read/write collisions while loading.
Memory initialization and CPU initialization jointly acknowledge core reset.

IF stored data serves register reads; resolved observation serves CPU T3 and
post-A/before-B retirement under the existing CPU contract. No private IF model
or forced acknowledgement is used. The selected program needs neither DMA,
timer overflow, JOYP selection nor snapshot commands. Unsupported owner requests
fail service, and assertions reject STOP, nonzero input and snapshot commands.
This is a bounded DV composition, not a new full board implementation.

## Execution modes

Use the accepted [continuous Python Client modes](../../../../src/dv/python/integration/README.md#continuous-real-uart-mode)
for current delivery. Shared preload initializes the actual Intel model from the
exact software-produced ROM and establishes the loaded-and-paused contract;
record its hash. Subsequent memory latency, arbitration, reset and execution
remain real. Preloaded execution proves execution, not UART loading. Real-UART
mode uploads and reads back the full image before the same execution checks.

## Legacy live transport and completion

The following finite-Tcl transport describes the historical target. It is not
the default delivery path or a prerequisite for unrelated continuous Python work.

The target uses a 25 MHz system clock and an eight-system-edge serial bit
period (3.125 Mbaud) for bounded simulation;
the real receiver/transmitter and packet/command/load owners remain active.
A builder-owned Python peer runs the product Client. A target-local Tcl driver
bridges encoded request bytes into a DV serial transmitter and returns bytes
captured from UART TX. It never decodes commands, supplies expected responses
or writes product storage. Its loopback channel is not a physical serial port.

Peer readiness has a five-second wall bound. Reply waiting and simulation
progress use a120-second wall tolerance, checked between simulation chunks.
The Client's simulated response deadline is unchanged. The target's outer
runtime bound is 300 seconds, subject to the total supervisor deadline. Its simulated watchdog is500 ms, preserving the
12.5-million-system-edge budget while the slower test UART loads and reads back
the complete image. Emulated instruction and frame bounds below are unchanged. The
builder reaps the peer after success, simulator failure or timeout, retaining
both outcomes. Success requires the live Client's successful exit and the DUT
checker signature. The Client checks response deadlines in simulation time.

After the selected frame the Client sends HALT and verifies paused state. Require
69 records, three RAM writes, four stack writes, sixteen tile writes and two
complete frames. The CPU-dot watchdog is220000 after RUN. All selected records,
bus transactions and pixels are retained with explicit public wave signals.

## Bounded integration target acceptance

One full positive is followed by actual returned-data, IRQ-connection and pixel
mutations. Expected records/pixels remain unchanged. A second clean run must
match the selected retirement, bus and pixel observations. Preserve exact source,
configuration, Python, simulator and Intel model identities; missing or shadow
models fail through the shared builder.

## Verification tiers

All simulations obey the [300-second total wall budget](../../../tools/n2m/SPEC.md#test-wall-budget).
Prefer the [authorized bounded FPGA/UART game checks](../../../agents/bootstrap-plan.md#verification-and-hardware-authorization)
after their build and setup gates pass. Required affected simulation and named
milestones use explicitly declared complementary simulation/physical matrices.

Select gates by affected behavior and the scoped issue. Use existing preload,
continuous Python, Intel models, builders, validators and targets; no additional
regression framework is required. Required CI remains in force. Evidence reuse
requires unchanged relevant source, configuration, tool and model identities;
record why retained coverage still applies. Independent expectations come from
the contract and original program, never DUT internal results.

### Fast development and ordinary PR acceptance

Run affected unit tests and a short composed smoke when the changed behavior
warrants it. Use a deterministic original software-built ROM through Intel-model
preload. Check selected instructions, memory operations, an interrupt, bounded
pixel activity and clean completion against independent expectations. Full-frame
rendering and UART ROM upload are not universal gates for each edit. Select
fault tests for affected behavior and stop at the shortest meaningful failure
witness. Recheck mutations when relevant checking infrastructure changes.

Target at most 120 seconds per simulation and 300 seconds aggregate for ordinary
pre-merge checks. These are goals, not coverage waivers or a reason for prolonged
harness optimization. Report the measured total and any unmet target. Use
`python-v05-timer` as a bounded short composed candidate: [PR235](https://github.com/amichai-bd/nand2mario/pull/235)
measured 21.250 seconds for 110 retirement records with all 26 fields, 16 selected
register/RAM bus transactions, timer overflow, IRQ entry, CPU HALT wake, a handler
RAM marker and final host pause. It checked 510 ordered startup white pixels
against a criterion of at least 320; it does not prove a complete normal frame or
UART ROM upload. Keep `python-integration-client-preloaded` when its broader
69-record, 145-bus-observation RAM/IRQ and two-full-frame coverage is relevant
([PR179](https://github.com/amichai-bd/nand2mario/pull/179#issuecomment-5573412250)).
Its measured stage runtime was 96.987663 seconds. These targets have different
coverage; their runtimes are not a matched speed comparison. A shorter selection
must still meet its own stated criteria. Neither individual result measures a
whole 300-second suite; add affected units to the reported total.

### Transport and integration acceptance

Run focused UART, protocol and loading tests when those behaviors change.
Require full upload/readback and UART-versus-preload comparison when the changed
behavior affects loading or startup equivalence. Label each mode's proof and
reuse valid evidence for unrelated unchanged paths. The matched real-UART
baseline in PR179 took 439.684165 seconds versus 96.987663 seconds preloaded;
these are one measured pair, not a guaranteed runtime. The bounded integration
target's full oracle and faults above remain available acceptance, not mandatory
transport work for every unrelated PR.

### Milestone acceptance

The revised [v0.5 matrix](../v05/SPEC.md#revised-milestone-matrix) combines precise
bounded startup/cross-frame observation, timer/DMA proofs, real UART loading and
all prescribed inputs, with separately bounded FPGA endurance. It replaces the
former 600-continuous-interval criterion, which was never passed. #88 tracks
the revised milestone; [PR246](https://github.com/amichai-bd/nand2mario/pull/246)
records window, fault and endurance qualification. No exhaustive physical retirement/pixel or
600-frame claim follows from this revision. Declare each broader milestone's
test selection, total expected cost, physical duration/inputs/sampling and
reset/hang checks before execution. Later release matrices remain separate.
These are milestone gates, not automatic implementation-PR gates.
Broader regressions belong to scheduled or milestone runs; this policy does not
create a scheduler. Before an expensive run, exercise the complete harness at
a short duration, including final pause, completion and watchdog handling. A
startup-only slice does not test that complete path. Short success never counts
as full milestone acceptance; leave unmet requirements in named open issues.
