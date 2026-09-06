# CPU verification plan

Status: component verification in progress for [#118](https://github.com/amichai-bd/nand2mario/issues/118).
[MAS_cpu](../../../wiki/src/rtl/cpu/MAS_cpu.md) owns behavior and its open design
gates. The component results below do not establish full CPU acceptance.

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
on the planned public CPU module.

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

This slice does not establish IRQ/HALT corner timing, STOP policy, every opcode's
architectural behavior, or internal IDU observations. These remain required before
#118 can close. In particular, the current pending-interrupt HALT path still needs
a directed distinction between an already enabled IME and delayed EI maturation.
