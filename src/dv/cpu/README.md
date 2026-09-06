# CPU verification plan

Status: CPU verification for [#118](https://github.com/amichai-bd/nand2mario/issues/118).
[MAS_cpu](../../../wiki/src/rtl/cpu/MAS_cpu.md) owns behavior. The complete
acceptance combines component and integrated fixtures below; current review and
retained run evidence are linked from [PR131](https://github.com/amichai-bd/nand2mario/pull/131).

The harness separates program and interrupt stimulus, a passive public bus and
retirement monitor, an independent reference model, and typed scoreboards.
Reference code must not import product decode, assembler opcode tables, internal
next-state logic or DUT register hierarchy. State setup uses original executed
instructions; their events remain checked. Memory stores expected bytes and
models agreed bounded service, with side effects only at committed accesses.

| Layer | Required cases | Observable checks |
|---|---|---|
| Opcode coverage | Every legal base encoding and all 256 CB encodings; eleven illegal base locks | Independently enumerated bins; fetched bytes, instruction length, event kind and absence of idle events |
| Arithmetic | All byte input pairs and carry choices for ALU reference checks; directed DUT boundary matrix; all A/N/H/C DAA combinations | Result and every preserved/changed flag, F low nibble, accumulator/CB rotate Z distinction |
| Memory/control | Every addressing form; taken/untaken conditions; signed displacement extrema; PC/SP/address wrap; CB memory BIT versus read/modify/write | Address, direction, byte, access order, idle M-cycles and exact T-cycle commits |
| Interrupts | Every priority, simultaneous/late requests, IE changes during stack writes, cancellation, EI/EI, EI/DI, RETI, EI/HALT | Live request sampling, acknowledgement, pushed PC, vector, IME/delay and separate entry event |
| Low power | HALT pending/not pending with both IME states; wake timing; STOP selected-held/pending branches and resolved model boundary | CPU sleep versus peripheral time, padding fetch, divider reset, no idle retirement |
| Reset/pause | Reset at every transaction phase and state family; pause before/after commits; reset while paused | No stale event or duplicated/lost access; generated profile and epoch; dot/sequence progression |
| Proof failures | Deliberate state, bus-timing and retirement corruptions | Three exact named diagnostics with nonzero raw Questa exit; positive wrapper success does not conceal raw failure |

Retain seed, source hashes, command lines, raw tool exits, transaction CSV,
retirement records, expected/actual mismatch detail, coverage and waves beneath
the shared builder tag. Bound each case and the complete suite by independent
watchdogs that fail nonzero. Final acceptance requires actual Questa execution;
host-only checks and prior software encoding proofs cannot substitute.

No full external adapter, integrated PPU/loader, commercial ROM or physical
compatibility result is claimed. Those remain separate issue acceptance.

## Checked components

- `cpu-alu` compares 1,232,896 byte/flag cases with an independent integer model,
  including unused operation passthrough. `cpu-alu-corrupt` forces the actual
  DUT result at the named case, rather than changing the expected/observed word.
- `cpu-execute` checks all base classifications and execution M-cycle counts
  across 16 flag sets against a separate manual count table. It also checks
  every CB memory operation with every byte/flag set through read, optional
  write and final fetch: 135,168 cases in total. The final RL/RR flags must
  retain the write-cycle result rather than recompute with the new carry.
- `cpu-bus` checks 13 commits with pause and reset at all four phases, plus
  inactive M-cycles and boundary reactivation. Missing response and activation
  partway through an M-cycle produce their exact named fatal assertions. A third
  negative changes the prepared address immediately after T1 and must fail
  before that altered request could commit.

These targets have actual Questa positive/negative evidence retained under the
author build tags. The cycle-count table does not prove every base instruction's
state or access address; the integrated public-bus/state oracle remains required.
The component state ports are datapath interfaces, not arbitrary register writes
on the public CPU module.

- `cpu-retire` checks six recorded events against independent literal ABI byte
  offsets, including instruction lengths, zero IRQ opcode, post-bus snapshots,
  idle non-repetition and reset cancellation/sequence restart. Its negative
  forces an actual output opcode field and must fail the record comparison.


## Integrated program slice

`cpu-program` executes an original literal program through the control, execution,
bus and retirement modules. Its independent tables compare all 50 M-cycles and
18 complete retirement records, followed by idle HALT observation through dot
220. The program covers register/memory loads, CB memory rotation, stack transfer,
taken and untaken branches, CALL/RET, JP and HALT. Separate state, commit-timing
and retirement-output faults force actual DUT signals and must fail with the
registered exact diagnostic and raw exit 1.

Separate fixtures below establish IRQ/HALT corner timing, the selected STOP
policy, opcode state/access coverage and digital IDU observations. The HALT
checks distinguish already enabled IME, delayed EI and wake after actual sleep.


`cpu-irq` adds 14 independent literal program/transaction cases. Requests before,
on and after T3 prove the closed request window. Cases cover all priorities and
simultaneous requests, high-stack IE cancellation, a low-stack IE write too late
to change selection, and a low-stack IF write that preserves the selection
snapshot. Separate EI/HALT and already-enabled HALT execution cases check return
PC. A 20-system-edge host pause after T3 removes the live request while preserving
the captured decision; a forced snapshot fault must fail the public bus schedule.
Separate wake, reset and STOP fixtures below cover those paths; the two HALT
execution cases alone do not establish them.


## Selected independent instruction vectors

The [selected fixture](singlestep/README.md) retains pinned MIT data, source
hashes, original case names/indexes and reproducible generation. `cpu-vectors`
checks 7,968 selected cases: 498 forms with all 16 initial flag combinations,
full architectural retirement state, expected read/write cycles, exact write
footprint and final listed RAM. The documented extra pipeline fetch is checked.
This is not all upstream vectors. STOP/HALT's 32 source cases are excluded in
favor of independent power/timing cases; source interrupt fields are excluded.

Initial arbitrary register/RAM state is loaded only by the simulation wrapper.
It constructs a literal fetch-state setup and forces whole packed variables,
then releases before the first T-cycle. No expected value comes from DUT state
or its profile helper. The internal control type is shared for that setup, not
exposed as a product port. Whole-variable setup avoids Questa's warning about
forcing a variable member from a nonconstant expression.

The state negative forces actual architectural A after the first opcode fetch;
the missing negative forces the actual recorder valid output. Expected upstream
state is unchanged. Both require their exact diagnostic and raw exit 1. Initial
setup attempts with warning/type errors are retained as failures, not accepted
proof. This layer does not prove physical IDU address exposure or future MMIO.


The IRQ fixture now has 18 cases. A sleeping IME1 HALT and a NOP waiting program
use the same request time and assert identical stack/ack/vector times, with their
separate correct return PCs. A request during a CB prefix must wait for the one
combined instruction event. Consecutive EI must mature without postponing a
pending request. The earlier 14-case records remain retained; these additions do
not alone establish IME0 wake latency or reset/STOP acceptance.


`cpu-reset` checks ten cancellation/reinitialization cases: synchronous core and
asynchronous global reset at each phase of a paused prepared write, plus each
reset between retirement capture and publication. It checks no partial write or
old event escapes, the global public state clears before core initialization,
and five full fresh-profile events per case restart sequence/epoch correctly.
Twenty idle system edges preserve each paused request and dot. The lost-write
negative forces actual commit low and must fail at the exact missing write.
The initial oracle omitted the generated profile's FFFE stack pointer; those
failed records remain retained, and the corrected literal checks all 48 bytes.
IRQ and power reset fixtures below cover the other state families.


The 20-case IRQ fixture additionally proves pending EI→DI cancellation and RETI
chaining to a remaining STAT request. The latter checks both stack entries,
acknowledgements, seven full events and the intervening RETI reads/idle/fetch;
no ordinary instruction may retire between RETI and the second entry. These
original cases supplement the upstream interrupt-field exclusions.


The DI cancellation case continues five literal NOPs through the would-be IRQ
completion time with IF still pending. It rejects any stack/ack/vector sequence,
not merely an incorrect IME bit. `cpu-irq-di-fault` forces actual interrupt mode
after DI and must fail the next public bus cycle. The shorter intermediate case
ended at DI and did not establish this behavioral cancellation; its evidence is
retained with that review limitation.


`cpu-halt-lock` checks pending-IME0 HALT followed by an immediate load and by RST.
The first reads the opcode byte again as its immediate value; the second pushes
the RST address itself. Literal bus and full retirement records prove both.
All eleven illegal base encodings then enter lock without retirement or further
access, stay locked across pause and pending requests, and recover through core
reset with a fresh epoch/sequence/profile NOP. Wrong-PC and invented locked-event
faults force actual DUT signals and must fail their exact public checks. These
cases are separate from the IME0 wake-after-sleep latency fixture below.


## STOP entry fixture

`cpu-stop` specifies eight original cases: the four selected-JOYP/pending-request
rows with both IME states. EI/NOP setup establishes IME through instructions.
The fixture checks actual one-byte versus two-byte retirement, ignored nonzero
padding, one-byte continuation executing that byte, ordinary interrupt entry
from the continuation row, divider-reset timing, held stopped-clock dots and
HALT's continuing ticks. Expected bus/stack schedules and complete 48-byte
records are literal and separate from the product policy. The policy inputs
come from public JOYP/IE/IF stimulus, not private controller readback.

The two negative targets force the actual policy's divider pulse or entry action;
expected records stay unchanged. This fixture covers deterministic entry only.
It does not settle analog wake, IME0 HALT wake latency, physical STOP IDU activity,
or the pending full-system clock/timer/JOYP integration. Actual run evidence and
its exact producing sources belong in the PR and build records.


### HALT fresh wake

`cpu-wake` uses an original six-NOP versus IRQ-entry/JP-HL stream. Both IME
states must reach the subsequent DIV read at wake plus 32 T-cycles. Literal
public schedules and complete retirement records cover interrupt arrival before,
on and after T3. Prepared reads persist through every-phase host pause; unused
sleep responses may be invalid without fault. A changed next opcode must execute
fresh after wake. `cpu-wake-stale` forces the actual captured opcode to its old
value, and `cpu-wake-missing` removes the required wake response, checking sample
suppression and the named fatal. These checks do not close STOP oscillator wake
or all sleep/reset-interruption acceptance.


`cpu-wake-reset` separately cancels sleeping preparation at all four M-phases,
for both reset types and IME states. Phase three has already captured a pending
request. It checks quiet held preparation, no reset-edge bus/IDU effect, no stack
write, and a fresh epoch/sequence-zero literal NOP record. The fault target
forces an actual reset-edge bus commit. Global reset is asserted between clock
edges, followed by an explicit direct-profile reset for fresh execution.


`cpu-irq-idu` checks fourteen literal bus/effect cycles and six complete records.
A JP to FDFD followed by a request captured before T3 causes a discarded FDFF
fetch, then the IRQ PC-repair effect at FE00. No ordinary access enters FE00–FEFF.
All four repair phases are paused without duplicate consumption. The negative
forces the actual effect address into FDFF while retaining the independent
expected FE00 page. This witnesses the additional effect separately from memory
transactions; it does not implement the OAM consumer or STOP wake mapping.


`cpu-wrap` checks original flat-memory programs against forty literal bus cycles
and twelve complete records. PUSH/POP and CALL/RET cross SP zero, a POP starting
at FFFF reads its second byte at0000, and a three-byte instruction at FFFE reads
operands at FFFF/0000 before executing the following HALT at0001. The independent
expected stream includes four stack writes. Its negative changes actual POP
read data and must fail the complete post-event record. The flat-memory responder
does not model the separate IF/IE owner or authorize product storage inference.


`cpu-if-observation` scripts resolved public IE/IF/button observations after A
and before B. Thirteen complete records distinguish retirement's updated fields
from held T3 recognition and the later dispatch snapshot. Clear, raise and
reprioritize cases have literal instruction/stack/vector schedules. The negative
forces the actual published IF field stale. This verifies the CPU sampling
contract, not the separate IF owner's collision-priority implementation.


`cpu-irq-reset` cancels each of five IRQ-entry M-cycles at all four phases with
both resets, plus two IRQ-capture-at-A/before-publication-at-B cases. It preserves
exactly the stack writes already committed, rejects pending access and stale
events, and checks a fresh epoch/sequence-zero profile record. Forty-two cases
produce 168 full records. The actual reset-edge commit fault must fail. Reset
does not roll back writes that crossed the public commit boundary.


The normal STOP-wake fixture uses a scripted qualified stable-clock pulse from
an external power owner. Four normal cases distinguish both IME states and
JOYP IE disabled/enabled with no pending request; a changed stored-PC opcode
must be fetched after the pulse and host pause. Sixteen reset cases cancel that
prepared fetch at each phase for both IME states and reset types. Literal bus,
full retirement and resumed IDU checks remain separate from actual stale-read
fault injection. This fixture does not establish analog settling duration,
JOYP event priority or the separately approved IME1 interrupt-during-restart model.


STOP-entry IDU checks extend the eight-row/IME entry matrix without changing its
architectural oracle. A separate eight-case program contrasts STOP at01FF/FDFF,
entry reads at0200/FE00, all four entry rows and independent additional effects.
It checks48 literal M-cycles,40 committed reads and16 full records. An actual FE00-to-FDFF
output mutation proves that ordinary read correctness cannot hide a wrong IDU
page. Analog partial-cycle shutdown timing is outside this digital projection.

`cpu-step` composes the real CPU and timebase. Seven single-instruction requests
stop on their completing A edge and publish eight B records, including one
interrupt entry which does not finish STEP. Literal cumulative dots are
8/16/24/28 and 8/12/36 after reset. The two fault targets suppress the actual
completion output or remove the finishing read response; the latter requires
both the missing-completion suppression marker and CPU bus assertion.


The `cpu-stop-irq` fixture checks the approved deterministic restart
approximation. Six literal schedules distinguish pending requests before wake,
pre-T3 arrival, on-T3 and post-T3 arrival, masked priority, and cancellation
before stack dispatch. Fresh INC A data distinguishes an immediately discarded
fetch from an instruction retired before the later interrupt. The oracle checks
both stack bytes, full IDU masks/addresses and every retirement field. Eight
additional cases cancel a qualified pending restart at each prepared-fetch phase
with core or global reset. The fourteen cases require 64 complete records.
Two actual DUT output faults target restart IDU qualification and the high stack
byte. This is a digital model check, not an analog oscillator measurement;
the accepted runs retain 32 explicit public waveform signals.
