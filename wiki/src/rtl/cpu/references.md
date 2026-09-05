# CPU behavior sources

These immutable sources support [MAS_cpu](MAS_cpu.md). They are research inputs;
no CPU implementation or upstream test suite is imported by this source record.
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
