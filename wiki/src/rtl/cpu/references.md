# CPU behavior sources

These immutable sources support [MAS_cpu](MAS_cpu.md). No upstream CPU
implementation is imported. The selected MIT instruction-vector data is recorded
separately in the [fixture manifest](../../../../src/dv/cpu/singlestep/README.md).
The original prose below summarizes the role and limits of each source.

| Source | Immutable revision | Purpose and reuse boundary |
|---|---|---|
| [Pan Docs](https://github.com/gbdev/pandocs/tree/fe246067b695b5404a4a6a47efb4fd6d921ececb) | `fe246067b695b5404a4a6a47efb4fd6d921ececb` | CC0-1.0. CPU instruction groups, interrupts, HALT and STOP decision diagram. Existing shared interface pin is unchanged. |
| [RGBDS instruction manual](https://github.com/gbdev/rgbds/blob/307846b03ea89ee57bf75f179d5f8051175ac60d/man/gbz80.7) | `307846b03ea89ee57bf75f179d5f8051175ac60d` | MIT manual. Instruction effects, flags and programmer M-cycle counts. Existing RGBDS dependency pin is unchanged; the assembler is an encoding oracle, not a CPU timing oracle. |
| [Gekkio Game Boy Complete Technical Reference](https://github.com/Gekkio/gb-ctr/tree/5ce83a107013e9bec4a19fcfdd440fb5dd75c616) | `5ce83a107013e9bec4a19fcfdd440fb5dd75c616` | CC-BY-SA-4.0 documentation, by Joonas Javanainen and contributors. Factual timing research only; no prose, diagrams or modified document assets copied. |
| [Gekkio SM83 die-derived research](https://github.com/Gekkio/gb-research/tree/59088f486f579a69fd86bd86a55181b937e769e0/sm83-cpu-core) | `59088f486f579a69fd86bd86a55181b937e769e0` | CPU VHDL header offers MIT OR Apache-2.0. Non-synthesizable SGB-CPU01/DMG-B research, with incomplete SoC interrupt validation. Read as corroboration, not executed or imported. |
| [SonoSooS CPU notes](https://gist.github.com/SonoSooS/c0055300670d678b5ae8433e20bea595/8efa6645473411e78dd917169141c16c0d306ce1) | `8efa6645473411e78dd917169141c16c0d306ce1` | License not established: reference only. Explains fetch overlap and IRQ microsequences, but explicitly notes uncertainty around power-saving and interrupts. No copied implementation or text. |

## Evidence boundaries

CTR's `chapter/cpu/timing.typ` supplies the worked INC/LDH/RST fetch-overlap
sequence. Its `chapter/console/clocks.typ` names half-cycle phases, while
`appendix/external-bus.typ` marks external read sampling. Comparing those two
figures implies T4 rising for that read sample. External WR is asserted over
part of T3/T4. This is not proof of every internal MMIO write edge, DMA conflict
or oscillator wake transition. The original Sharp SM831x overlap diagram is not
used as the authority: CTR identifies misleading cases in it.

Pan Docs `src/Interrupts.md`, `src/halt.md`,
`src/Reducing_Power_Consumption.md` and `src/imgs/stop_diagram.svg` define the
specific instruction questions. The STOP diagram's nondeterministic branch is
preserved as a modeling decision, rather than converted into an unsupported
promise about repeatable analog behavior.

The [baseline adapter plans](../../dv/baseline/SPEC.md#future-adapter-plans) own
existing SingleStepTests, SameBoy and Mooneye pins and their later adapters.
Those are not re-pinned here. Single-step M-cycle vectors do not prove T-cycle
bus edges, and their IME/EI limitations cannot establish interrupt behavior.
Independent original fixtures must cover those gaps without reading product
control signals. Source byte hashes belong in retained build evidence; imported
source, if later approved, additionally needs its exact license and notices.

## Interrupt snapshot evidence

The pinned Mooneye `acceptance/interrupts/ie_push.s` reports results verified on
DMG and other listed hardware. It establishes that an upper stack-byte write
to IE can cancel dispatch or change its selected request, while the lower-byte
write is too late to cancel it. Cancellation targets zero, leaves IF unchanged
and leaves IME clear. This establishes ordering, not a measured exact T-edge.
`acceptance/ei_sequence.s`, `ei_timing.s` and `halt_ime0_ei.s` separately constrain
consecutive EI, delayed enable and EI/HALT behavior. These files were read as
research with their MIT notices; no external suite was executed or imported.

The existing pinned SameBoy `Core/sm83_cpu.c` captures IE after the high write,
then selects against IF during the low write. Its `cycle_write_if` uses the
old IF value when that write itself targets IF, and comments explicitly flag
remaining same-M-cycle timing uncertainty. The CPU therefore keeps its dispatch snapshot separate from post-commit IF
storage. The phase inference below refines that snapshot to T3 rather than
claiming that SameBoy proves every simultaneous timer/request/register-write
priority in hardware.

The same Pan Docs pin's `src/OAM_Corruption_Bug.md` distinguishes ordinary
read/write activity from IDU address exposure and identifies the POP/RET and
stack-push exceptions. It supplies an additional required CPU observation
boundary for the future OAM/arbitration owner, not permission to infer all
bus-side effects from retirement or T4 transaction commits.


## Request-latch phase inference

At the existing Gekkio research pin, `hdl/cells/dlatch.vhd` is transparent while
its clock is high. `hdl/interrupts.vhd` uses PHI to latch the enabled request
vector. `hdl/simulation/test_soc.vhd` supplies PHI high in half-phases 0–3 and writeback in
6–7; the control unit consumes the held request at the instruction boundary.
CTR's clock-phase figure places PHI falling at T3 rising. Combining these sources
supports capturing the resolved enabled vector before T3 and using it at T4 in
our digital bus contract. This is a stated inference from an unexecuted die
model with known SoC-validation limits. It naturally separates preceding high
stack writes from the current low write, consistent with Mooneye's IE tests.

The pinned SameBoy `halt()` performs its dummy read before checking pending
requests and rolls PC back when IME is set. That predicate is not restricted to
delayed EI. Therefore the general Pan Docs distinction between normal wake and
EI/HALT is insufficient by itself to prove a late-arrival rollback defect. Our
checks must contrast request sampling during execution with wake after sleep;
source interpretation and tested digital behavior remain separately identified.


The existing Mooneye pin's `acceptance/halt_ime1_timing2-GS.s` explicitly compares
HALT waiting with NOP waiting and reports equal latency on DMG/MGB/SGB/SGB2,
while other listed models fail. `halt_ime1_timing.s` checks that the instruction
after HALT does not execute before service. `halt_ime0_nointr_timing.s` compares
six NOPs with interrupt entry plus JP HL; its whole setup and fetch pipeline must
be accounted for before fixing the IME0 wake schedule. These primary fixtures
were read with retained MIT notices; no Mooneye ROM was run here.
