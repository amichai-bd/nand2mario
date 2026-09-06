# SM83 CPU

Status: design in progress for [#118](https://github.com/amichai-bd/nand2mario/issues/118).
The byte ALU, instruction cycle planner, digital bus and retirement recorder
have component Questa evidence. The integrated controller has checked programs,
selected instruction vectors and directed control-state fixtures; the public
wrapper and remaining acceptance boundaries are unfinished. The open modeling decisions below
must be settled before their dependent RTL. This owner covers the complete legal
base and CB instruction sets; a subset does not complete the issue.

## Authority and model

The [charter](../../project-charter.md) selects original DMG-family behavior.
The CPU uses the [clock and reset contract](../../clocks-resets-cdc.md) and the
[generated direct profile and retirement ABI](../interfaces/MAS_interfaces.md).
CPU work does not change that ABI or claim a stock boot-ROM state. The
[source record](references.md) distinguishes instruction facts, measured timing,
reverse-engineering evidence and remaining uncertainty. No external CPU HDL,
boot contents, or decode implementation is imported.

The intended digital model follows documented DMG-B instruction behavior. It
includes the HALT bug, delayed interrupt enabling, interrupt priority changes
during entry and deterministic STOP cases. It does not claim analog oscillator
or exact silicon identity. The STOP uncertainty is an explicit design gate,
not an exemption from instruction coverage.

## Boundary

The planned module is `n2m_cpu` under `src/rtl/cpu/`. Inputs are synchronous
to `clk_sys` except `reset_sys`, which asserts asynchronously and releases
through the shared domain synchronizer. CPU registers use asynchronous global
reset assertion through the shared macros. `core_reset` is synchronous and has
priority over tick-enabled updates; the wrapper synchronizes external inputs. CPU state uses shared
register macros and local properties use named assertion macros. Declarations
are separate from assignments, including power-up initialization. A tick is an
enable, never a generated CPU clock.

| Signal group | Direction | Rule |
|---|---|---|
| `clk_sys`, `reset_sys`, `core_reset` | Input | Reset has priority over emulated activity. Core reset aborts the current instruction and bus attempt and applies the generated profile. Global reset additionally clears any observation history. |
| `gb_tick` | Input | One enabled system edge advances one emulated T-cycle. No missing response may stretch or drop this edge. |
| `profile_id` | Input, generated profile-ID width | Core reset accepts only the generated direct-profile ID and applies every generated CPU register/control field. An unknown ID is a named contract failure; it cannot select a test state. |
| `epoch` | Input, 32 bits | Current initialization epoch, supplied by the system owner. The CPU does not invent a second epoch counter. |
| `dot_before` | Input, 64 bits | System count of completed emulated T-cycles before the current edge. An event on `gb_tick` records this count plus one. The system count includes HALT, freezes with host pause, and follows the agreed STOP oscillator gating; it is not a CPU-running counter. |
| `ie`, `iflags` | Input, 8 and 5 bits | Live interrupt enable and request state, including changes caused by CPU writes and peripherals. These are not frozen at interrupt-entry start. |
| `buttons`, `joyp_selected_active` | Input | Public latched button snapshot and selected active-low JOYP-line reduction from the JOYP owner; physical buttons alone do not determine STOP wake. |
| Memory request | Output | Address, read/write direction, write byte and access kind: opcode, operand, data, stack or idle. Idle is observable without issuing a memory transaction. |
| Memory response | Input | Read byte and response-valid by the specified emulated sampling edge. There is no unbounded ready/wait protocol. |
| Memory commit | Output | One pulse per committed access. Preparation must not cause peripheral side effects; reset before commit cancels the attempt. |
| Interrupt acknowledge | Output, 5 bits | At most one selected request cleared at the specified entry edge; the peripheral owner combines acknowledgement and its own event/write priority. |
| STOP coordination | Output | CPU stopped and divider-reset request, distinct from host pause and CPU HALT. The enclosing system owns oscillator/peripheral gating. |
| Contract fault | Output | Latched on missing response or invalid initialization profile; suppresses further commits and retirement until reset. Simulation additionally emits the corresponding named fatal assertion. |
| Retirement | Output | One-cycle valid pulse and generated `retirement_t`, describing the completed event. No backpressure may change emulated CPU timing. |

The final port names follow this boundary. The digital memory phases below do
not depend on implementing future peripherals first. These are product-facing signals, not a test-only register-write port.
Tests establish non-reset register states through executed instructions and
observe public bus transactions and retirement. An observation port cannot
change architectural state.

## Instruction and state rules

All addresses wrap to 16 bits. Byte arithmetic wraps to 8 bits. The low nibble
of F is always zero, including after POP AF. Addition H and C describe carries
out of bit 3 and bit 7; subtraction uses borrows at those boundaries. ADC/SBC
include the input carry in both boundaries. INC/DEC preserve C. ADD HL preserves
Z and derives H/C at bits 11/15. Signed SP-offset instructions clear Z/N and
compute H/C from the unsigned immediate's low nibble/byte addition to SP, while
the resulting address uses signed extension. These operations must not borrow
host-language signed overflow behavior.

Accumulator rotates clear Z; CB rotates/shifts derive Z from the byte result.
BIT preserves C, sets H and clears N; RES/SET preserve all flags. DAA respects
the preceding N/H/C state, including non-BCD input combinations. Its exhaustive
independent check includes every A value and all N/H/C combinations. Unused
flag inputs are also varied to verify preservation rules.

A CB prefix and its following byte form one non-interruptible instruction.
Memory BIT reads without writing; other CB memory operations read and then
write in separate M-cycles. Stack pushes write high byte before low byte while
decrementing SP; pops read low byte before high byte while incrementing SP.
Conditional instructions have separate taken and untaken bus/idle sequences.
The eleven illegal base encodings enter a CPU lock state until reset; they do
not become NOPs or dispatch interrupts. Lock idle does not retire instructions.

EI enables interrupts after the following instruction, not between EI and that
instruction. DI disables immediately and cancels pending enable. Consecutive EI
must not postpone the first EI's scheduled enable. RETI enables before the next
instruction can execute. Pending enabled interrupts are prioritized from the
lowest numbered request. Interrupt entry is a separate event, with two idle
M-cycles, two stack writes and the vector-fetch cycle. The CPU captures `IE & IF` immediately before each T3 rising enable (bus phase
2) and holds that vector through T4. Final-fetch recognition and low-stack
vector selection use this snapshot, not live T4 or post-commit IF. A peripheral
request resolved before T3 participates; a request produced at or after that
edge participates in the next M-cycle. Host pause preserves the snapshot;
reset cancels it. This digital mapping follows the PHI latch and clock-phase
inference in the [source record](references.md), not a claim of measured
half-cycle accuracy for every peripheral.

At low-stack T4, the lowest captured bit selects the vector and acknowledgement.
A high-byte write to IE has committed before the following T3 snapshot and can
cancel or reprioritize entry. A low-byte write to IE or IF occurs after that
snapshot and cannot replace it. No selected bit gives vector zero, no IF
acknowledgement, and IME remains clear. This selection observation is separate
from the resolved post-event IF snapshot captured for retirement. The future IF
owner resolves register/event/ack collisions; this CPU contract does not invent
their priority from HDL scheduling.

Once asleep, HALT wakes from the captured enabled request at the next T4
boundary. With IME set it enters the interrupt sequence directly, preserving the
same subsequent stack/ack/vector timing as NOP waiting under the identical
request schedule. No extra fetch M-cycle may be unique to that path. This follows
Mooneye's DMG timing comparison; it does not establish every physical pin edge.
At wake T4 both IME states consume a fresh next-opcode read, prepared throughout
sleep. IME clear executes that byte immediately in the following M-cycle; IME
set discards it into interrupt entry. Six NOPs and interrupt entry plus JP HL
therefore reach a following read at the same relative edge. No extra refetch
M-cycle or stale pre-sleep byte may substitute for the wake read. STOP's stopped-clock wake
continues to use its separate power-policy input.

HALT preserves peripheral time. With IME clear and an enabled request already
pending, it suppresses one following opcode-fetch PC increment instead of
sleeping. Without such a request it sleeps until an enabled request appears;
wake without IME resumes without servicing. With IME set, wake services an
interrupt before executing the following instruction. EI/HALT and changed
pending state at entry/wake are separate directed cases.

## Arithmetic datapath

`n2m_cpu_alu` is a combinational byte datapath. Its operation enum belongs to
`n2m_cpu_pkg`; the controller owns cycle timing and destination writeback.
Inputs are two bytes, input F and a three-bit CB bit index; outputs are the
result byte and F with its low nibble cleared. CP returns the unchanged left
byte with subtraction flags. BIT returns the unchanged byte with tested flags.
SCF/CCF change only their specified flags. Unused operation codes return the
unchanged byte and masked F; the controller must never issue them.

The directed datapath fixture uses a separate integer reference and its own
operation mapping. It enumerates every byte pair and carry state for the eight
binary operations, every input byte and flags nibble for unary operations, and
every bit index for BIT/RES/SET: 1,220,608 legal-operation cases. A further
12,288 cases check the three unused operation values. All 1,232,896 cases and the actual DUT-output fault injection have run in
Questa. This proves the byte datapath boundary, not instruction sequencing or
full CPU coverage. A sampled trace and early
waves are retained; any later mismatch includes its complete expected/actual
inputs even after routine waveform recording ends.

## Time, bus and retirement

Instruction manuals count execution M-cycles with the final opcode fetch
overlapping the next instruction. Startup requires one initial fetch and no
synthetic retired NOP. The implementation and scoreboard must distinguish this
startup from an extra cycle charged to every instruction. Fetched instruction
bytes are retained when read, so later memory changes cannot rewrite a trace.
A branch's final fetch uses the branch target; a HALT fetch can leave PC
unadvanced. An interrupt can discard an already fetched opcode without retiring
that instruction. The internal fetch cursor is not architectural `pc_after`:
that field identifies where the next instruction would execute after this event.
In particular, a completed final fetch does not add one to `pc_after`.

With initial PC `0100`, memory `0100:00, 0101:00, 0102:00` and uninterrupted ticks:

| Completed dot | Access | Event |
|---|---|---|
| 4 | Fetch `00` at `0100` | None: initial fetch only. |
| 8 | Fetch `00` at `0101` | Sequence 0, NOP, before `0100`, after `0101`; cursor may already be `0102`. |
| 12 | Fetch `00` at `0102` | Sequence 1, NOP, before `0101`, after `0102`. |

For `0100:C3, 0101:00, 0102:02` (JP `0200`), accesses occur at dots 4, 8 and 12;
dot 16 is idle and dot 20 fetches `0200`. The JP event at dot 20 has before
`0100`, after `0200`, and fetched bytes `C3 00 02`. It must not report `0201`.
A suppressed HALT-bug cursor increment is tracked independently: consecutive
instructions may legitimately have the same first-opcode address. A discarded
interrupt fetch cannot become a fabricated instruction event.

The external timing reference places read sampling at T4 rising. This is an
inference from its matching half-cycle labels and sampling marker, not evidence
that all internal peripherals have the same side-effect edge. The CPU's digital
bus uses the four T-cycle enables; it does not reproduce analog cartridge pins.
The digital CPU bus uses this fixed mapping:

| Phase | CPU and bus action |
|---|---|
| Before T1 | The next M-cycle address, direction, write byte and kind are available. The bus owner may prepare data; preparation has no architectural side effect. |
| T1 through T3 | Request fields remain stable. The bus owner resolves its bounded internal service and arbitration. Idle cycles issue no transaction. |
| T4 | Exactly one commit pulse for an access. Reads require valid data at this edge; writes take effect at this edge in the digital bus abstraction. A missing read response latches the contract fault and emits a named fatal assertion in simulation. It consumes no read byte, commits no access and never becomes a wait state. |
| Following system edge | Bounded bookkeeping observes bus-side IE/IF updates and publishes any completed retirement event with its captured T4 dot. It adds no emulated cycle. It must finish before the next T-cycle enable. |

This T4 write commit is the digital transaction boundary, not a claim to
reproduce the cartridge's falling-edge WR pin pulse. Future bus/peripheral
owners map their pin, DMA, blocked-access and register conflict behavior into
this boundary and may not acknowledge preparation as a write. The CPU does not
resolve unimplemented peripheral conflicts by extending instruction timing.
Reset before T4 cancels an uncommitted request; reset at T4 wins over commit.
A prepared request may remain stable across host pause without side effects.

The bus M-phase runs through HALT cycles. HALT keeps a side-effect-free opcode
read prepared at the next PC. The internal `complete_enable` permits consumption
only when the T3 snapshot enables wake; it gates missing-response faults as well
as commit. A response is not required for an unused sleeping preparation.
Memory continuously services preparation and applies effects only on commit. The front end may change
bus-active state only at phase zero, after a completed T4; a named assertion
rejects activation partway through an M-cycle. In particular, a wake observed
while inactive cannot immediately commit a new request at phase three. STOP
freezes the system T-cycle supply at the agreed boundary; host pause preserves
the current phase and active request. Directed checks vary inactive/reactivation
and pause at all four phases. Reset resets phase to zero regardless of activity.

Retirement records post-event architectural state, actual fetched bytes and the
public IE/IF/button snapshot. A CB instruction produces one event, interrupt
entry produces its own kind, and HALT/STOP/lock idle produces none. Event sequence
starts at zero after initialization. Dot is supplied by the system owner and counts completed emulated T-cycles,
including HALT time; host pause contributes none. CPU STOP reports its clock
request to that owner rather than maintaining a competing time counter. The input epoch is copied,
not generated. The generated field widths and wrap rules remain authoritative.
Interrupt events have opcode and opcode length zero. Instructions retain only
their one to three fetched bytes, with unused high bytes zero; CB remains one
event. IME_DELAY and HALT_BUG describe the post-event pending-enable and
suppressed-increment states, not historical triggers. No event from an aborted
pre-reset instruction may leak after reset.

Host pause freezes the supplied tick, CPU state and emulated bus progress at a
T-cycle boundary. A prepared transaction is retained without committing twice.
Resume continues that transaction once; it does not refetch committed operands,
repeat a stack write, or invent elapsed dots. Reset while paused still takes
priority. The system must not use CPU HALT as host pause.

## Internal-address observation

A committed read/write trace is insufficient for DMG-B OAM corruption. The
pinned Pan Docs OAM-corruption chapter identifies IDU activity that exposes a
16-bit register value even without read/write strobes, including INC/DEC pairs,
postincrement/decrement HL, stack operations and PC increments. POP/RET have a
specific difference between their first and second read; stack pushes can merge
IDU and ordinary write activity within one M-cycle.

The planned typed `address_effect` observation is separate from the memory
request and retirement ABI. It describes additional write-like address activity
within the current M-cycle, including cycles with no ordinary transaction. It
never asks the memory owner to perform a second architectural write.

| Field | Meaning |
|---|---|
| `valid` | This M-cycle has a modeled additional address effect. Zero means no effect within the implemented contract, not an unknown effect silently accepted as absent. |
| `address[15:0]` | Pre-operation address bits justified by the source mapping. Bits outside `known_mask` are canonical zero and carry no physical claim. |
| `known_mask[15:0]` | One marks a justified address bit. The consumer must not interpret a zero-mask bit as a known zero. |
| `write_effect` | Additional write-like OAM effect, to be combined with any ordinary read/write in this M-cycle. It does not indicate an architectural memory write or its data. |

The current internal controller exposes `address_effect_phase`,
`address_effect_sample` and `address_effect_resolved` alongside the payload.
The sample pulse occurs only on the shared T4 rising enable, with reset and
fault suppression; a missing response suppresses the sample on the failed T4
itself, before the registered fault changes. It can accompany idle rather than a memory commit.
`resolved` is an explicit completeness qualifier: a consumer must reject an
unresolved sample rather than interpreting its payload as no effect. In this
incomplete integration, STOP execution and its oscillator-wake address activity
remain unresolved. Ordinary HALT preparation is resolved but is sampled only
when its fresh wake read completes. Sourced ordinary fetch/operand/stack/planner
cycles are resolved. This qualifier changes observation only, not CPU execution,
and cannot waive the remaining full-CPU acceptance gate.

The public bus phase identifies T1 through T4 for this observation. Fields are
prepared before T1 and stable through T4, including host pause. The owner samples
one M-cycle observation at the shared T4 rising enable; it must not apply one
effect per system clock while `valid` remains asserted. Reset or a canceled bus
attempt suppresses the observation. HALT preparation may expose a valid payload
through sleep without a sample pulse; it causes no increment effect until wake.
STOP/lock idle has no fabricated PC increment. This is an M-cycle digital abstraction, not a claimed pin waveform.

A valid write-like observation must have every high-byte mask bit set; the
producer enforces this with a named assertion. Unknown high bits are not an
allowed output of the settled mapping. For OAM qualification the consumer requires `(known_mask & FF00) == FF00` and
`(address & FF00) == FE00`. An incomplete high byte is insufficient to decide
whether an effect qualifies; it cannot be treated as outside OAM. The pinned
Pan Docs corruption patterns depend on the scanned PPU row and combined access
type, not the lower address bits or written byte. Therefore a justified high
byte alone is sufficient for that consumer. The OAM owner qualifies each ordinary access and additional effect using its
own address before combining their types. For example, an SP decrement from
FE00 must not lose its effect because a later stack write addresses FDFF.
It combines ordinary read/write and this additional write-like effect within one M-cycle; two writes
in that cycle do not become two separate corruption applications.

The implementation and directed proof must follow this mapping:

| Operation | Additional effect and address observation |
|---|---|
| INC/DEC 16-bit pair | Internal update M-cycle; full pre-operation BC, DE, HL or SP. |
| HL postincrement/decrement load | Memory-access M-cycle; full old HL, combined with that access. |
| POP and RET family | First stack read: full old SP and additional effect. Second read: ordinary read only, despite its SP update. |
| PUSH, CALL and RST | First decrement before the high write, then the decrement overlapping the high write; full old SP for each. The low write has no additional decrement effect. |
| Ordinary opcode/operand PC increment | Same M-cycle as the read, with the full old PC. A suppressed increment or HALT dummy fetch must not inherit this rule merely because its access kind is opcode. |
| HALT wake and ordinary IRQ repair | Wake read: full next PC with increment. Following IRQ repair: full prefetched cursor before decrement. STOP-origin wake remains separately unresolved. |
| ADD HL,rr; ADD SP,e; LD HL,SP+e | Internal arithmetic cycles have no additional write-like effect (`resolved=1`, `valid=0`). Their operand reads and final fetches retain ordinary PC-increment effects. This does not describe floating pin voltage. |
| LD [a16],SP | Low-byte write cycle: full temporary address before its increment, combined with the ordinary write. High-byte write: ordinary write only. |
| LD SP,HL | Internal transfer cycle; full old HL, following the register-file address-drive inference and independent emulator corroboration. |
| Taken JR, conditional or unconditional | Internal adjustment cycle: pre-adjustment PC high byte, mask `FF00`. Low bits remain unclaimed. Final target fetch is a separate ordinary fetch. |

The shared JR mapping follows the die-model datapath inference in the
[source record](references.md#internal-address-evidence). It deliberately does
not choose different unconditional and conditional addresses from emulator
shortcuts. Each row requires checked observation traces before full readiness; an invalid observation is not a waiver for those effects.
OAM storage and corruption belong to their separate owner. The current planner's
idle address remains unrelated to a physical address claim.

## STOP entry policy

For the DMG model there is no KEY1 speed-switch request. The pinned Pan Docs
chart's no-speed-switch path gives these entry results. Its IME/glitch diamond
belongs to the speed-switch path and is not used as a DMG entry condition.

| Selected JOYP line active | Enabled request pending | Length | Entry mode | DIV reset |
|---|---|---|---|---|
| Yes | Yes | 1 byte | Continue; ordinary enabled interrupt recognition still applies. | No |
| Yes | No | 2 bytes | HALT | No |
| No | Yes | 1 byte | STOP | Yes |
| No | No | 2 bytes | STOP | Yes |

The combinational `n2m_cpu_stop_policy` receives the selected-line
reduction, the CPU's T3 enabled-request snapshot and the STOP execution pulse.
It drives the existing internal action/padding seams and a divider-reset pulse
only on the completed STOP T4. The selected-line input is observed before that
T4 edge, consistent with the synchronous digital input boundary; a newly
resolved post-edge input belongs to subsequent wake handling. This mapping
states the digital sampling convention, not measured analog pin timing. The
second byte is the actual byte read from memory, retained in a two-byte event
but not executed; a one-byte event leaves it as the next instruction address.

The system completes the following bookkeeping edge before withholding further
emulated ticks for STOP. HALT does not withhold peripheral ticks. Neither host
pause nor a canceled/reset STOP attempt may create a divider-reset pulse. The
future timer and JOYP owners consume these boundaries; the CPU does not add
another divider counter or duplicate selected-line computation.

These entry rows do not resolve oscillator restart. The separately pinned
SonoSooS notes describe an interrupt with IME set during DMG STOP wake as an
unstable-clock case. That wake model remains an explicit pending decision;
it is not silently converted into a fault, a repeatable analog result or an
exemption from the complete CPU acceptance gate.

## Design gates before dependent RTL

1. Resolve the documented nondeterministic STOP oscillator-restart case under
   the charter's model policy; the deterministic entry rows are separate above.
   A deliberate model fault or a deterministic digital approximation must be
   explicit and reviewed; neither may be silently presented as exact silicon.

These gates do not authorize a reduced opcode implementation. Remaining
instruction datapath and independent test design can proceed from their pinned
sources while the affected behavior waits.

## Verification

The [CPU test plan](../../../../src/dv/cpu/README.md) owns case structure and
coverage. Actual Questa evidence must cover every legal base and CB encoding,
flag and arithmetic boundaries, exact access and idle cycles, control-flow paths,
reset interruption, pause/resume, IRQ/HALT/STOP and all retirement fields.
Expected state, bus schedules and coverage identifiers are independent of DUT
decode and next-state logic. Assembler encoding data is not a CPU oracle.

State, timing and retirement mutations must each produce their intended fatal
failure and a nonzero raw simulator exit through the shared builder. Retain
source hashes, commands, seed, expected/actual transactions, traces and waves.
Host checks, full external adapters and physical acceptance remain separate.


## Module and state ownership

The CPU follows the [typed boundary convention](../../rtl-reference-style.md#typed-module-and-timing-boundaries).
`n2m_cpu_pkg` owns execution request/result, bus plan and T4 retirement-capture
records and the finite STOP action enum. Generated profile and published record
encodings remain in their existing interface owner.

| Module | Responsibility and state |
|---|---|
| `n2m_cpu` | Explicit composition and unchanged scalar CPU boundary; no state. |
| `n2m_cpu_control` | Architectural registers, instruction/IRQ steering and T3 snapshot; sole steering owner. |
| `n2m_cpu_execute` / `n2m_cpu_alu` | Combinational execution result and arithmetic; no state. |
| `n2m_cpu_bus` | Sole T-phase/fault owner; prepared plan, completion and commit. |
| `n2m_cpu_retire` | T4/A capture, following-edge B publication and sequence state. |
| `n2m_cpu_stop_policy` | Combinational deterministic entry action, padding and divider request. |

The top connects `u_control`, `u_execute`, `u_bus`, `u_retire` and
`u_stop_policy`. Typed boundaries add no registers or clock domains. Control
emits a prepared plan and architectural capture record; it does not duplicate
bus phase or recorder state. IE/IF/buttons still enter the recorder at B.
The STOP oscillator-wake seam remains incomplete; composition alone does not
resolve that behavior or close the issue.

## Integration status

The `n2m_cpu` wrapper composes the owners above. Its checked original program
covers 18 events and 50 M-cycles. The component owns deterministic STOP entry from `joyp_selected_active`
and its frozen enabled-request snapshot. The remaining `wake_request` input is
an internal policy seam, not an addition to the host initialization ABI; the
final wrapper must own its resolved logic.

The T3 request snapshot mapping is specified above; its contrasted IRQ/HALT
fixtures have bounded checked evidence; full readiness still requires the remaining gates. The current HALT return-to-HALT
branch matches the pinned SameBoy model for pending requests with IME set,
including delayed EI. An earlier inference that ordinary IME alone proved this
branch wrong was withdrawn after source comparison. Requests before the latch
closes and arrivals after HALT enters sleep need separate checked expectations.
STOP wake policy, its remaining IDU observation, and final composed acceptance
remain unfinished; this snapshot cannot close
#118. The selected 498-form state/access evidence below remains valid within
its declared flat-RAM exclusions.


The selected flat-RAM vector layer now checks 498 forms with all 16 initial flag
combinations. Its data and exclusions are owned by the CPU test plan. It does
not complete STOP/HALT, full reset/wake interruption, physical IDU observations
or integrated peripheral timing acceptance. Arbitrary state setup belongs only
to the simulation wrapper; the public direct-profile contract is unchanged.
