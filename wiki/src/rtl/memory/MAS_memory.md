# Direct-profile memory

Status: proposed under [#130](https://github.com/amichai-bd/nand2mario/issues/130).
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
| OAM | Memory | CPU, DMA and corruption updates reach one resolved write port. The PPU receives the arbitrated pair from #132, not a second OAM array. |
| Wave RAM | Memory | An APU gateway owns CPU wave-access semantics and playback addressing; raw storage and generated reset fill belong here. An absent gateway is a service failure, not a synthetic audio register. |
| Peripheral registers and state | Their behavior owners | Timer #128, DMA/arbitration #132, IF/IE #133, JOYP #134, PPU #120, and future serial/APU owners. No generic shadow I/O register file. |

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
| Host ROM | Independently enabled read/write, bounded thirty-two-bit offset and byte data. Endpoint #91 must authorize writes. | Registered read byte and valid. RAM clearing alone does not block this port. |
| PPU VRAM | Read enable and thirteen-bit byte offset. | Registered byte and valid. |
| PPU raw OAM | Read enable and seven-bit pair index, zero through 79. | Registered sixteen-bit pair, lower-address byte in bits 7:0. #132 resolves the pair presented to PPU. |
| Wave playback | Read enable and four-bit byte offset. | Registered byte and valid. The APU gateway owns playback and CPU access restrictions. |

RAM ports are unavailable while clearing; the upstream router must suppress
their requests, with a named invariant detecting a violation. Host ROM requests
remain independent. This boundary prevents a quiet fixture from standing in for
the eventual CPU/PPU reset-coordinator wiring.

The sweep performs 8192 write edges after reset release. WRAM and VRAM write
every edge. HRAM writes offsets 0 through 126, OAM offsets 0 through 159, and
wave RAM offsets 0 through 15. OAM uses two eighty-byte parity banks for the
same single logical store; its raw resolved write remains one byte per edge.
The completion edge writes offset 8191 before asserting `init_done`. A repeated
sampled core reset restarts this schedule. No ROM array clear is performed.
DMA/corruption write granularity remains a #132 integration gate.

## Fixed service and CPU commit

CPU #118 at `9a984d0` agrees that request fields are prepared before T1 and held
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

PPU #120 proposes `vram_request`, thirteen-bit byte address, and a registered
one-system-edge data/valid response. That response must already exist before
the consuming A dot; a response first registered at A is too late. The OAM
raw store reads a seven-bit pair address and returns lower-address byte in
bits7:0. PPU phase0 is idle, phase1 scans Y/X, and phase2 fetches tile/attribute.
Phase1 suppresses capture during DMA; phase2 uses the actual arbitrated pair.
No missing-response fallback or PPU backpressure is allowed.

The PPU owner agrees to the previous-request registered response and pre-A
sampling boundary. The raw RAM follows the shared Intel primitive contract;
contested-bus selection and access-gating corner traces remain separate gates.
#132 owns CPU bus conflicts,
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

Absent cartridge RAM is an explicit unresolved bus-value policy. Sources call
disabled/unmapped RAM open bus, often but not guaranteed FF; the pinned
reference uses retained bus data and labels its approximation uncertain.
No constant-FF replacement or analog decay rule is authorized by these sources
alone. Storage/echo/service development can continue, but complete #130
read-value acceptance requires this policy to be resolved.

Unimplemented I/O addresses also need an exact DMG-B source-backed table.
Recognized but not-yet-implemented peripheral registers must remain routed to
their explicit owner, regardless of what unused registers return. FF50 belongs
to the direct-profile boot-mapping policy, not a mutable generic RAM byte.

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
