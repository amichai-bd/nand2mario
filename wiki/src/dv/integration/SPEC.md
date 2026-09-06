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

## Live transport and completion

The target uses an eight-system-edge serial bit period for bounded simulation;
the real receiver/transmitter and packet/command/load owners remain active.
A builder-owned Python peer runs the product Client. A target-local Tcl driver
bridges encoded request bytes into a DV serial transmitter and returns bytes
captured from UART TX. It never decodes commands, supplies expected responses
or writes product storage. Its loopback channel is not a physical serial port.

Peer readiness has a five-second wall bound. Reply waiting and simulation
progress use a120-second wall tolerance, checked between simulation chunks.
The Client's simulated response deadline is unchanged. The target's outer
runtime bound is600 seconds. The
builder reaps the peer after success, simulator failure or timeout, retaining
both outcomes. Success requires the live Client's successful exit and the DUT
checker signature. The Client checks response deadlines in simulation time.

After the selected frame the Client sends HALT and verifies paused state. Require
69 records, three RAM writes, four stack writes, sixteen tile writes and two
complete frames. The CPU-dot watchdog is220000 after RUN. All selected records,
bus transactions and pixels are retained with explicit public wave signals.

## Final acceptance and regression tiers

One full positive is followed by actual returned-data, IRQ-connection and pixel
mutations. Expected records/pixels remain unchanged. A second clean run must
match the selected retirement, bus and pixel observations. Preserve exact source,
configuration, Python, simulator and Intel model identities; missing or shadow
models fail through the shared builder.

Use measured compile and execution durations to propose merge smoke plus affected
units, milestone broad suites and full #88 runs. Recheck relevant mutations when
their observation/checking infrastructure changes. Record queue/review time
separately when available. No speedup claim or recurring schedule is implied.
