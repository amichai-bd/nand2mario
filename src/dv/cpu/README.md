# CPU verification plan

Status: planned for [#118](https://github.com/amichai-bd/nand2mario/issues/118).
[MAS_cpu](../../../wiki/src/rtl/cpu/MAS_cpu.md) owns behavior and its open design
gates. No CPU simulation result is claimed by this plan.

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
