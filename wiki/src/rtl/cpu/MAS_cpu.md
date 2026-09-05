# SM83 CPU

Status: design in progress for [#118](https://github.com/amichai-bd/nand2mario/issues/118).
The CPU is not implemented or verified yet. The open modeling decisions below
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

The planned module is `n2m_cpu` under `src/rtl/cpu/`. Every signal is synchronous
to `clk_sys`; the wrapper synchronizes external inputs. CPU state uses shared
register macros and local properties use named assertion macros. Declarations
are separate from assignments, including power-up initialization. A tick is an
enable, never a generated CPU clock.

| Signal group | Direction | Rule |
|---|---|---|
| `clk_sys`, `reset_sys`, `core_reset` | Input | Reset has priority over emulated activity. Core reset aborts the current instruction and bus attempt and applies the generated profile. Global reset additionally clears any observation history. |
| `gb_tick` | Input | One enabled system edge advances one emulated T-cycle. No missing response may stretch or drop this edge. |
| `epoch` | Input, 32 bits | Current initialization epoch, supplied by the system owner. The CPU does not invent a second epoch counter. |
| `ie`, `iflags` | Input, 8 and 5 bits | Live interrupt enable and request state, including changes caused by CPU writes and peripherals. These are not frozen at interrupt-entry start. |
| `buttons`, `joyp_selected_active` | Input | Public latched button snapshot and selected active-low JOYP-line reduction from the JOYP owner; physical buttons alone do not determine STOP wake. |
| Memory request | Output | Address, read/write direction, write byte and access kind: opcode, operand, data, stack or idle. Idle is observable without issuing a memory transaction. |
| Memory response | Input | Read byte and response-valid by the specified emulated sampling edge. There is no unbounded ready/wait protocol. |
| Memory commit | Output | One pulse per committed access. Preparation must not cause peripheral side effects; reset before commit cancels the attempt. |
| Interrupt acknowledge | Output, 5 bits | At most one selected request cleared at the specified entry edge; the peripheral owner combines acknowledgement and its own event/write priority. |
| STOP coordination | Output | CPU stopped and divider-reset request, distinct from host pause and CPU HALT. The enclosing system owns oscillator/peripheral gating. |
| Retirement | Output | One-cycle valid pulse and generated `retirement_t`, describing the completed event. No backpressure may change emulated CPU timing. |

The final port names and exact bus phases will be frozen with the timing decision
below. These are product-facing signals, not a test-only register-write port.
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
M-cycles, two stack writes and the vector-fetch cycle. Selection and cancellation
during entry require the explicit timing decision below.

HALT preserves peripheral time. With IME clear and an enabled request already
pending, it suppresses one following opcode-fetch PC increment instead of
sleeping. Without such a request it sleeps until an enabled request appears;
wake without IME resumes without servicing. With IME set, wake services an
interrupt before executing the following instruction. EI/HALT and changed
pending state at entry/wake are separate directed cases.

## Time, bus and retirement

Instruction manuals count execution M-cycles with the final opcode fetch
overlapping the next instruction. Startup requires one initial fetch and no
synthetic retired NOP. The implementation and scoreboard must distinguish this
startup from an extra cycle charged to every instruction. Fetched instruction
bytes are retained when read, so later memory changes cannot rewrite a trace.
A branch's final fetch uses the branch target; a HALT fetch can leave PC
unadvanced. An interrupt can discard an already fetched opcode without retiring
that instruction.

The external timing reference places read sampling at T4 rising. This is an
inference from its matching half-cycle labels and sampling marker, not evidence
that all internal peripherals have the same side-effect edge. The CPU's digital
bus uses the four T-cycle enables; it does not reproduce analog cartridge pins.
The final request/response/commit mapping must preserve ordered reads/writes and
state which bus-owner behavior remains outside this module.

Retirement records post-event architectural state, actual fetched bytes and the
public IE/IF/button snapshot. A CB instruction produces one event, interrupt
entry produces its own kind, and HALT/STOP/lock idle produces none. Event sequence
starts at zero after initialization. Dot counts all completed emulated T-cycles,
including HALT time; host pause contributes none. The input epoch is copied,
not generated. The generated field widths and wrap rules remain authoritative.
No event from an aborted pre-reset instruction may leak after reset.

Host pause freezes the supplied tick, CPU state and emulated bus progress at a
T-cycle boundary. A prepared transaction is retained without committing twice.
Resume continues that transaction once; it does not refetch committed operands,
repeat a stack write, or invent elapsed dots. Reset while paused still takes
priority. The system must not use CPU HALT as host pause.

## Design gates before dependent RTL

1. Freeze the four-phase memory contract, including internal-memory side effects
   and IRQ acknowledgement timing. External read sampling alone is insufficient
   evidence for every MMIO owner.
2. Reconcile interrupt selection after the high stack write, including an IE
   write through a wrapping SP, late higher-priority requests, cancellation and
   the resulting vector/acknowledge. Expectations must be independently sourced.
3. Resolve STOP's deterministic held/pending combinations and the documented
   nondeterministic oscillator-glitch case under the charter's model policy.
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
