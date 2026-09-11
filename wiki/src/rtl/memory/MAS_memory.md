# Direct-profile memory

Implementation: [memory stores](../../../../src/rtl/memory/n2m_memory_stores.sv)
and [CPU dispatch](../../../../src/rtl/memory/n2m_memory_cpu_port.sv).
This owner connects storage to the CPU, PPU and host endpoint. It does not supply
missing peripheral or DMA behavior. The [shared interfaces](../interfaces/MAS_interfaces.md)
own numeric ranges, fills, profile and load semantics.

## Stores and ownership

| Store | Sole storage owner | Behavior owner and access |
|---|---|---|
| Direct ROM | Memory, generated exact profile size | Host endpoint validates LOAD_BEGIN/presence/CRC and controls loading; memory accepts bounded byte offsets and supports complete readback. CPU ROM writes never load bytes. |
| WRAM | Memory | CPU commits and the separately arbitrated DMA read port. Echo uses the same low thirteen address bits, with no second store. |
| HRAM | Memory | CPU commits; no alias at IE or the host address range. |
| VRAM | Memory | CPU access policy comes from PPU/arbitration; PPU reads the same store through its fixed service port. |
| OAM | Memory | CPU, DMA and corruption updates reach one resolved write port. The PPU receives the arbitrated pair from the [DMA owner](../dma/MAS_dma.md), not a second OAM array. |
| Wave RAM | Memory | The [audio gateway](../audio/MAS_audio.md) owns CPU wave-access semantics and offset selection; raw storage and generated reset fill belong here. An absent gateway is a service failure, not a synthetic audio register. |
| Peripheral registers and state | Their behavior owners | [Timer](../timer/MAS_timer.md), [DMA/arbitration](../dma/MAS_dma.md), [IF/IE](../interrupts/MAS_interrupts.md), [JOYP](../joypad/MAS_joypad.md), [PPU](../ppu/MAS_ppu.md), [serial](../serial/MAS_serial.md) and the [audio gateway](../audio/MAS_audio.md). The last two are present-but-unimplemented peripherals: they serve access and return DMG read values without transfer or synthesis. No generic shadow I/O register file. |

All RAM arrays initialize by a bounded sweep using the generated RAM fill.
ROM is retained across core reset and remains invalid until the endpoint's
complete load succeeds. The largest owned RAM determines the sweep length;
completion becomes true only after the final physical write edge. During reset
or initialization no CPU commit or PPU sample may advance emulated state.
Clear cancels pending responses and dominates owned writes. It does not reset
UART, PLL, VGA ownership or immutable frames. External register initialization
completion is a separate input to the system reset coordinator.

### Raw store service

[`n2m_memory_stores`](../../../../src/rtl/memory/n2m_memory_stores.sv) exposes
storage-local operations after arbitration; it is not the CPU address decoder.
Its internal store selector is defined in
[`n2m_memory_pkg`](../../../../src/rtl/memory/n2m_memory_pkg.sv), not the host ABI.
All ports use `clk_sys`. `reset_sys` and `core_reset` immediately cancel response
validity and suppress operations. Global reset initializes sweep state
asynchronously; a sampled core reset restarts the sweep at offset zero.

| Port | Request and bounds | Response |
|---|---|---|
| Resolved access | Read/write, store selector, fifteen-bit local byte offset and byte data. Offset must fit the selected generated region. | Registered byte and valid after a read edge. ROM writes have no effect. |
| OAM pair service | Package-owned read or two byte-write enables, pair index0-79 and sixteen-bit data. Mutually exclusive with a resolved OAM byte request. Other stores remain independent. | Registered pair and valid; both parity banks remain the sole authoritative storage. |
| Host ROM | Independently enabled read/write, bounded thirty-two-bit offset and byte data. The [UART endpoint](../uart/MAS_uart.md) must authorize writes. | Registered read byte and valid. RAM clearing alone does not block this port. |
| PPU VRAM | Read enable and thirteen-bit byte offset. | Registered byte and valid. |
| PPU raw OAM | Read enable and seven-bit pair index, zero through 79. | Registered sixteen-bit pair, lower-address byte in bits 7:0. DMA arbitration resolves the pair presented to PPU. |
| Wave access | Independently enabled read and write, four-bit byte offset and byte data. | Registered byte and valid after a read edge. The [audio gateway](../audio/MAS_audio.md) owns which CPU access reaches this port; clearing dominates its write. |
| Host peek | Read enable, wire store selector and thirteen-bit byte offset, for the five non-ROM stores. Accepted only while the core is paused, initialization is complete and the offset lies inside the selected store. | Registered byte and valid. Read-only: it is served from port B, which has no write. |

### Host peek on port B

Every store is an [`n2m_intel_ram`](../common/MAS_memory_primitives.md) with two
ports. Port A is the core's path: CPU and DMA traffic, the OAM pair port, the
sweep, and ROM's host load. Port B carries the host peek, under one rule for all
five non-ROM stores: **read-only, and rejected unless the core is paused.**

Read-only is structural, not a convention. The shared primitive exposes
`b_read`, `b_address`, `b_rdata` and `b_valid` and has no `b_write` or
`b_wdata`, so a host peek is physically incapable of writing. This preserves the
principle that the product has no register-write test port. ROM is not a peek
target: loading needs writes that port B cannot perform, so ROM keeps port A for
both its host load and its readback.

WRAM and HRAM need no arbitration, because nothing else uses their second port.
VRAM, both OAM parity banks and wave RAM mux the host against their existing
port B consumer, and each mux also withholds the owner-facing valid so a peek
response is never presented to the PPU or the audio reader as its own service.
An OAM peek addresses a byte as pair `offset[7:1]` with `offset[0]` selecting
the parity bank.

Pause is what makes this safe rather than merely documented. The PPU, audio,
DMA and timers all advance on `gb_tick`, which the system derives from
`emulated_tick && !cpu_stopped`, so pausing idles every port B consumer and a
host read displaces nothing. This matters concretely for OAM: mode-3 length
depends on sprite X values fetched out of OAM, so a displaced OAM fetch would
change CPU-visible STAT timing. Requiring pause removes that hazard instead of
documenting it. A displaced VRAM fetch would corrupt only displayed pixels, but
the same single rule covers it.

Named invariants detect a caller that violates the contract: peek activity
implies a paused core and completed initialization, implies an in-range known
store, implies the target is not ROM, and implies no owner request is in flight
on the same edge.

RAM ports are unavailable while clearing; the upstream router must suppress
their requests, with a named invariant detecting a violation. Host ROM requests
remain independent. This boundary prevents a quiet fixture from standing in for
the eventual CPU/PPU reset-coordinator wiring.

The sweep performs 8192 write edges after reset release. WRAM and VRAM write
every edge. HRAM writes offsets 0 through 126, OAM offsets 0 through 159, and
wave RAM offsets 0 through 15. OAM uses two eighty-byte parity banks for the
same single logical store; its resolved CPU write remains one byte per edge, while the OAM service can
write either or both bytes of one pair.
The completion edge writes offset 8191 before asserting `init_done`. A repeated
sampled core reset restarts this schedule. No ROM array clear is performed.
The [DMA owner](../dma/MAS_dma.md) arbitrates pair operations and PPU collisions.

### Direct-path late OAM writes

The v05 and integration-smoke paths share `n2m_oam_late_write` over the same
pair-A port; the [late-write fixture](../../../../src/dv/memory/tb_oam_late_write.sv) checks this schedule.
The [combined DMA schedule](../dma/MAS_dma.md#qualified-late-writes) consumes
the same class using its existing service slots. Both owners use the shared
combinational transform; the direct schedule below remains unchanged.

At the legal final scan T4, the selected digital extension transforms the
addressed eight-byte row. Other words copy the last OAM row. Each byte of the
addressed word becomes the bitwise majority of its old byte, byte FE9C, and
the corresponding last-row byte. The explicit CPU byte replaces its result
last. This qualifies the allowed A0 write path in pinned SameBoy Core
`213a12ce93d66b105a113debd9396306066a7cfc` (`memory.c`), not a universal
silicon data claim. The primary LCD-on permission table and its revision
limits remain in the [PPU contract](../ppu/MAS_ppu.md).

Prepare four last-row pairs and the addressed pair before accepted T4 A.
Five requests plus the final response fit the stable prepared CPU write;
require complete operands and matching address/data at A. Write the addressed
pair, including the final CPU byte, at A. Drain the other three pairs at
A+1 through A+3, prioritizing a requested PPU pair. Suppress B requests only
on an actual same-pair write. A fresh B read at A+4 supplies the earliest
next capture at A+5. Do not change CPU T4 or renderer clocks and timestamps.

Pair work excludes raw OAM preparation, including its CPU response-valid
capture. A following CPU request may appear immediately after A; resume its
qualified raw read after the drain, before its next T4. Invalidate operands
after every commit, including repeated identical writes. Preparation while
paused has no memory effect; an accepted job drains on system edges without
inventing ticks. Reset cancels the job and the existing store clear owns RAM.
Missing operands or overlapping commits are fatal integration faults, never
permission to stretch or replay the CPU cycle.

## Fixed service and CPU commit

### Address ownership decoder

`n2m_memory_decode` maps the sixteen-bit CPU address to a named destination and,
for storage-backed regions, a local byte offset. ROM, WRAM and its echo, and
HRAM select direct storage. VRAM, OAM and the unusable range select the
arbitration/access-policy boundary. Wave RAM selects the APU gateway rather
than bypassing its access rules. Numeric ranges and register addresses come
from the generated interface package.

JOYP, serial, timer, IF/IE, APU, PPU and DMA registers retain distinct behavior
owners. FF46 selects DMA, independent of its neighboring PPU registers. FF50
selects the direct-profile boot policy. A000–BFFF and unassigned I/O each have
an explicit destination. The CPU port implements the exact fixed-I/O rule
below and the approved absent-cartridge rule.
Store/offset outputs for non-storage destinations are unused. The decoder has
no state or commit effects. Its fixture independently enumerates all 65,536
addresses, including all 7,680 echo offsets, and injects a wrong echo offset.

### Prepared and committed operations

`n2m_memory_cpu_port` dispatches the prepared CPU request. Direct ROM/WRAM/HRAM
reads request the raw store each system edge; writes reach it only with
`bus_commit`. A complete sixteen-bit tag from the preceding enabled read must
match the current address before a raw response is exposed to CPU. A changed
address cannot reuse the previous response. Owner destinations receive address,
direction, data, prepare and commit separately; their current pre-T4 read data,
validity and fixed-service availability return through the selected-owner
boundary. Fixed unused/boot I/O and absent cartridge RAM are handled locally without an owner commit or
storage operation. This dispatch does not implement the DMA resolved-access mux.

Reset or incomplete initialization suppresses dispatch and masks all CPU
responses. The CPU owns cancelling read completion when `response_valid` is
absent. A commit nevertheless presented without active service triggers a
named assertion and latches `contract_fault`. Effects are suppressed on that
same unavailable-service edge, and the sticky fault suppresses later dispatch
and responses until reset. An external write owner must
guarantee service at commit; availability is an integration invariant, not a
new CPU write handshake. The system fault coordinator remains responsible for
reporting the sticky fault; this slice does not invent a later replay.

The CPU-port fixture composes the real shared Intel-backed raw stores with
this dispatch. It checks bidirectional echo, held read preparations, ignored
CPU ROM writes, stale address rejection and reset cancellation. Its selected
owner endpoint is explicitly synthetic and proves dispatch only. Normal
fault targets require named fatal diagnostics. A separate compilation wrapper
defines `SYNTHESIS` around the same product and test sources to observe the
hardware sticky fault after a missing-owner write: no same-edge commit,
subsequent dispatch suppressed, and reset recovery. This complements, and
does not replace, the assertion-enabled runs.
The normal positive also cancels a prepared read and write at each T1–T4
boundary under both core and global reset. Held system edges before each
boundary check pause behavior; T4 reset overlaps the commit input. Every
case waits for the complete clear and checks that no cancelled byte effect
or stale response survives.
The same fixture holds CPU request/commit inactive during an interrupted
public-port ROM load, resets after seventeen written bytes, verifies those
bytes through permitted incomplete-load readback, then fills the remaining
direct image. This models only the endpoint's stop/reset coordination. The UART endpoint
still owns image completeness, CRC/presence and RUN authorization; raw memory
does not invent an image-valid flag or define unwritten-byte read values.

The [CPU bus contract](../cpu/MAS_cpu.md) requires request fields to be prepared before T1 and held
through T4. `read_data` and `response_valid` are consumed before the T4 edge;
T3 samples IE/IF only, not memory data. A synchronous RAM result from a preceding
system edge therefore meets the read boundary. Read preparation has no side
effect. Only `bus_commit` at the agreed T4 edge changes storage or commits a
peripheral command. Missing response cancels that same edge and latches a named
contract fault; no stretched T-cycle is inserted.

Host pause holds a prepared request, but produces no commit. Core/global reset
at any phase cancels response validity and wins over a coincident commit.
CPU addresses stay sixteen bits; host ROM offsets stay separately bounded and
host status addresses never enter the CPU decoder.

Sleeping HALT may retain a next-PC opcode preparation without a commit. The
memory service can refresh this side-effect-free read; only the CPU's qualified
wake-T4 completion creates `bus_commit`. A missing response on that attempted
completion cancels the same edge. Sleeping preparation alone requires no read
effect and does not authorize an emulated state transition.

I/O prepare routes address/direction/data to the selected behavior owner before
T4. Its read result may reflect the current pre-edge register value; memory
does not snapshot it prematurely or apply read effects during preparation.
The owner receives a commit pulse only for the accepted CPU access. Unknown
service must fail, not be replaced by a convenient constant.

## PPU and arbitration boundary

The [PPU port](../ppu/MAS_ppu.md#digital-ports) uses `vram_request`, thirteen-bit byte address, and a registered
one-system-edge data/valid response. That response must already exist before
the consuming A dot; a response first registered at A is too late. The OAM
raw store reads a seven-bit pair address and returns lower-address byte in
bits7:0. PPU phase0 is idle, phase1 scans Y/X, and phase2 fetches tile/attribute.
Phase1 suppresses capture during DMA; phase2 uses the actual arbitrated pair.
No missing-response fallback or PPU backpressure is allowed.

The composed `memory-service` fixture connects actual CPU dispatch and Intel
stores to an independent PPU request driver. Its pre-A checks compare each
response with the previous request while the next address is already present.
It performs concurrent WRAM/echo effects, permitted CPU VRAM/OAM reads and
both PPU reads, then checks blocked writes/FF reads and accessible unusable
zero reads through a synthetic selected-policy adapter. The adapter supplies
ordinary access gates explicitly and permits only one resolved A writer.
These traces prove storage/routing boundary composition. They do not implement
the PPU fetcher, DMA engine, corruption algorithm or transition-edge policy.
The companion fault target corrupts the actual returned VRAM byte before a
known pre-A observation; the independent previous-request data oracle must
fail with the exact nonzero mismatch diagnostic.

The PPU owner agrees to the previous-request registered response and pre-A
sampling boundary. The raw RAM follows the shared Intel primitive contract;
contested-bus selection and access-gating corner traces remain separate gates.
The [DMA owner](../dma/MAS_dma.md) owns CPU bus conflicts,
OAM write priority, corruption rows and the pair presented to PPU. Its resolved
raw-store operations may be implemented independently of its engine; a tied-off
DMA fixture cannot claim arbitration acceptance. Pending behavior is not
silently encoded as a denied access or a fabricated FF response.

## Source-backed access and open gates

The pinned [source record](references.md) supports bidirectional WRAM echo,
ignored ordinary writes into prohibited storage, PPU-owned VRAM/OAM gating,
and the DMG-B unusable range: zero when OAM is accessible, FF when blocked.
Access to that range can still participate in the separately owned OAM
corruption behavior. Treat its read result and corruption event independently.

### Absent cartridge RAM in the direct profile

The approved digital profile returns FF for every A000-BFFF read and ignores
all writes to that range. It allocates no cartridge RAM and sends no prepare
or commit to an external owner. Read service is combinational, with the same
reset, initialization and sticky-fault masking as other CPU responses.

This is an explicit digital approximation, not a claim that real unmapped
cartridge buses always read FF. The pinned sources describe open bus and a
reference retained-bus approximation; this profile does not model analog decay
or retained bus data. The CPU fixture writes and reads all 8192 addresses with
an unavailable external owner and independently checks FF and zero effects.

### Fixed unused I/O and disabled boot mapping

The pinned [I/O sources](references.md) establish this exact DMG-B table:

| CPU addresses | Read | Committed write |
|---|---|---|
| FF03; FF08–FF0E | FF | No effect |
| FF15; FF1F; FF27–FF2F | FF | No effect |
| FF4C–FF4F; FF51–FF7F | FF | No effect |
| FF50 in this direct profile | FF | No effect; boot mapping stays disabled |

These 71 addresses have combinational read service and no writable state.
They do not send a prepare/commit to a peripheral or touch raw memory. Reset,
initialization and contract-fault masking still apply. The CPU-port fixture
writes and reads every entry, checks FF independent of written data, and
checks that no owner or storage effect escapes.

All other defined DMG registers retain their explicit behavior owner and its
read masks/effects. Readable-FF write-only audio registers are not unused
addresses; the [audio gateway](../audio/MAS_audio.md) owns their read-back
masks. Wave RAM remains behind that gateway. A000–BFFF is outside this
I/O table and follows the separate approved digital rule above.

## Shared primitive and verification

All backing stores use the [shared Intel memory wrapper](../common/MAS_memory_primitives.md).
The identical explicit instances and parameters are used by the installed
Intel model in Questa and by MAX 10 synthesis. This owner does not duplicate
the shared reset/read-hold, byte-enable or collision rules. Resolved A reads
and writes may coincide with full-lane new-data service. A write may not target
the address of an active B read; arbitration must schedule it separately.
Clearing uses ordinary public A writes and never accesses a vendor-private array.

Independent Questa checks cover all region endpoints, complete reset sweeps,
ROM loading/readback/retention across core and global reset, interrupted-clear
restart, bidirectional echo, per-phase pause/reset, prepared versus committed
I/O, and simultaneous permitted CPU/PPU service. The raw-store fixture observes
every clear write at the public primitive ports and independently reads every
owned byte. Deliberate alias, duplicate commit and early-initialization defects
must fail with exact nonzero diagnostics. Macro assertions supplement traces.

A separate constrained MAX 10 fit retains the actual store configurations and
service paths, with concrete primitive/resource and timing evidence. Source-size
arithmetic is only a design estimate. Historical inferred-RAM runs are not
acceptance evidence for the current implementation.
