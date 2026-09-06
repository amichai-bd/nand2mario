# DMG interrupt registers

Status: proposed under [#133](https://github.com/amichai-bd/nand2mario/issues/133).
This owner stores IF/IE and resolves requests, CPU writes and acknowledgement.
CPU owns priority selection, IME, delayed EI and dispatch timing. Numeric
addresses and direct-profile reset fill belong to the
[generated interfaces](../interfaces/MAS_interfaces.md).

## Sources and scope

The [source record](references.md) distinguishes documented request edges and
read masks from the inferred collision projection below. No external RTL is
imported. No timer, PPU, JOYP or serial behavior is synthesized here. Each
peripheral owns its request condition and timing; this owner detects request
rises once and stores their flags independently of IE or IME.

## Registers and ports

One module, `n2m_interrupts`, uses `clk_sys`. `reset_sys` asserts asynchronously;
core reset is sampled by the system, with immediate output/capture cancellation.
Both apply the generated peripheral fill to IF's five stored bits and IE's
eight bits, and clear pending operations/history. IF reads force bits7:5 high;
only bits4:0 are writable. IE retains all eight written bits, but CPU selection
uses only bits4:0. Global boot-era register defaults are not the direct profile.

| Port group | Meaning |
|---|---|
| `gb_tick`, `io_commit`, `io_write`, `io_address`, `io_wdata` | A is a system edge with an emulated T enable. An accepted CPU register write occurs only at its T4 A edge. Reads are side-effect free and do not require commit here. |
| `io_selected`, `io_rdata` | Exact IF/IE address selection and current pre-edge read value for the selected-owner memory service. No bus address aliases. |
| `source_level[4:0]` | Qualified request levels, bit order from the generated interrupt interface. PPU supplies its combined STAT condition and VBlank condition, not a private IF register. A timer/serial one-event pulse must remain visible through a consuming system edge. |
| `irq_ack[4:0]` | CPU's one-hot-or-zero selected acknowledgement, captured at its A boundary. A zero-vector canceled entry sends zero. |
| `ie_stored[7:0]`, `if_stored[4:0]` | Stored state before the current A transaction, available to ordinary service and phase reasoning. |
| `ie_observe[7:0]`, `if_observe[4:0]` | Resolved state including pending A write/ack and peripheral transitions visible before B. This is the CPU retirement observation, not a new interrupt selector. |

No duplicate IF/IE shadow exists in memory or PPU. All state uses package-owned
records where it crosses the capture boundary and shared register macros.

## A/B collision projection

This reviewed internal system-clock mapping preserves the CPU's A/B contract.
It does not assert a measured physical write-pulse width or analog collision rule.

A captures the committed CPU write and acknowledgement. B is the following
system edge, before another emulated T enable. The captured operation remains
active during A-to-B resolution. Peripheral conditions updated after A are
therefore included in `if_observe` before B; B stores that same resolved value.
This avoids a nonblocking-assignment delay in CPU retirement. Capture/bookkeeping
finishes even if host pause suppresses future emulated dots. A and B cannot be
the same system edge and a new A cannot overwrite an unconsumed capture.

For each IF bit, reset applies profile state first. Otherwise an active
acknowledgement clears that bit; otherwise a captured IF write supplies its
written bit; otherwise a new source rise sets the bit; otherwise it holds.
IE changes only for reset or its captured committed write. Multiple independent
source rises set their bits together; IE never suppresses flag storage.

Source history samples actual levels even when a write or acknowledgement
overrides that edge. Clearing IF while a source stays high must not create a
new request. A later low-to-high transition can set it again. Reset clears
history; all peripheral owners must reset their request outputs consistently.
A level high after reset release is a new request, not silently forgotten.

Events already stored before A are subject to the newly captured write/ack.
An event appearing between A and B collides with that same active operation.
An event appearing after B is a subsequent event and may set the flag after
the write has completed. These are named digital boundaries, not inferred
from statement execution order. Committed reads never alter flags/history.

## CPU and peripheral observations

CPU captures enabled requests immediately before each T3. Feed the agreed
current resolved observation there, when no A-to-B write remains pending.
Its frozen enabled vector, not live IF, controls later dispatch. A high stack
write to IE finishes before the following T3 and can cancel/reselect entry;
a low stack IF/IE write occurs after that snapshot and cannot replace it.
Do not add a live re-AND inside this module or reconstruct dispatch from
post-write IF. CPU retirement at B independently samples `if_observe` and
`ie_observe`, which include that event's completed effects.

PPU combined STAT/VBlank conditions may change after A. The source rise and
any A write/ack must resolve before CPU B capture without adding an emulated
cycle. Held STAT conditions retain the shared-line blocking behavior when
software clears IF. A synthetic source fixture proves this owner interface,
not the pending PPU STAT-write or timer reload behavior.

## Required verification

Independent literal tests cover every IF bit, all32 source masks, IE disabled
and reenabled, software set/clear, full-byte IE retention, IF upper masks,
held-high suppression and low/high rearming. Enumerate per-bit write0/write1,
ack0/ack1 and new-edge0/new-edge1 against a literal truth table, then exercise
the same combinations through actual A/B captured operations.

Directed schedules place events before/on/after A and B; they distinguish
stored state from B observation, pause after A, core/global reset cancellation,
and no stale response/capture. A composed CPU-boundary fixture checks high-stack
IE cancellation/reselection, low-stack IF prewrite selection, simultaneous
sources, and a retirement snapshot differing from its T3 vector. Do not copy
CPU next-state into the oracle or claim these scripts execute the full CPU.

Actual source/ack/observed-state faults must cause exact nonzero named mismatch
diagnostics. Retain positive and negative Questa logs, source/tool identities,
public waveforms, sequence/counts and expected/actual register traces. This
acceptance does not close any peripheral or whole-system issue.
