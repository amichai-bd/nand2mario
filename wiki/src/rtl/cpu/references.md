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


## Internal-address evidence

At the same Gekkio research pin, `hdl/cpu_core.vhd` drives the external address
from `idu_in`, not `idu_out`. The decoder stages use shared taken-JR adjustment
and completion paths for conditional and unconditional forms. In
`hdl/regfile.vhd`, the adjustment phase drives PC's high byte onto the IDU input;
PC's low byte and the signed offset participate in the separate ALU result.
The following phase drives WZ for the target fetch. The simplified model does
not establish a fully driven low address byte throughout the adjustment phase.
Our high-byte-only observation is an explicit inference from these connections,
not a measured full 16-bit bus value. None of this VHDL was executed or imported.

The pinned SameBoy JR implementations pass differently timed PC values to their
OAM helper. That difference is not adopted as proof of distinct conditional and
unconditional hardware paths. Pan Docs' `src/OAM_Corruption_Bug.md` states that
once an address is in FE00–FEFF, its precise value does not affect the corruption
pattern. This supports a known-high-byte interface for the later OAM consumer,
while preserving uncertainty about physical low bits and waveform intervals.

For LD SP,HL, decoder stage 1 identifies the transfer state; stage 2 selects
`addr_hl`, and stage 3 enables HL onto the IDU input and the IDU result into SP.
The register file connects all 16 HL bits to that input. Together with SameBoy's
explicit HL OAM-effect call, this supports the full-HL internal-transfer
observation. The additional effect is not inferred merely from an architectural
SP value change; other arithmetic transfers need their own source mapping.

For LD [a16],SP, stage 2 selects WZ onto the IDU input for both data-write
states, and asserts `idu_inc` specifically for low-write state `s010`.
This establishes the extra increment effect at the old temporary address in
that M-cycle. The high write has no corresponding increment. Combining the
extra effect with the ordinary write follows Pan Docs' same-cycle rule, rather
than requesting a second architectural write.

For ADD HL's internal `sx00`, ADD SP,e's internal `001`/`010`, and LD HL,SP+e's
internal `x01`, the decoder's complete IDU input-driver selection has no active
PC, HL, BC, DE, SP or WZ source, and the IDU increment/decrement controls do not
select those states. The signed-SP result uses ALU paths and direct WZ-to-SP
writeback; it is not an SP-to-IDU address exposure. SameBoy separately uses
`cycle_no_access` for these internal cycles. We therefore map them to no
additional write-like effect within this digital observation model, without
claiming a measured value on floating or precharged pins. Final-fetch states
ADD HL `x01`, ADD SP,e `011`, and LD HL,SP+e `x10` still select PC increments.


## STOP chart scope

The retained Pan Docs SVG connects selected-line inactive to the KEY1 question.
Its no-speed-switch branch leads directly to the pending-request question and
the one-byte/two-byte STOP entry results. The IME/glitch diamond is downstream
of the speed-switch-yes branch. It must not be relabeled as a DMG entry test.
The same source's selected-line-active branch chooses one-byte continuation
or two-byte HALT. SameBoy corroborates these entry cases, while explicitly
marking the STOP dummy-read timing unverified. Separately, the pinned SonoSooS
notes describe unstable DMG clocks when an IME-enabled interrupt occurs during
wake. We preserve that separate evidence and model limit without conflating
it with the chart's CGB speed-switch branch.


## HALT wake projection

At the existing Gekkio pin, `control_unit.vhd` forces decoder state `111` during
clock shutdown (`reset_op_int`, lines 164 and 217–239). Decoder stage 1's
`op_s111` and stage 2's `addr_pc`/`idu_inc` select the next-PC fetch. Normal
interrupt state `int_s000` instead selects PC with `idu_dec`; the register file
and `cpu_core` expose the IDU input, hence the pre-decrement cursor. These are
digital source-to-phase inferences, not measurements of stopped-clock pins.

The two Mooneye timing fixtures place their DIV resets at matching 24/23
M-cycle setup offsets: the extra IME0 NOP replaces EI. Their six-NOP versus
interrupt-entry-plus-JP-HL comparison constrains the subsequent latency. A fresh
read at wake T4 followed by execution satisfies that comparison; an additional
IME0 refetch M-cycle does not. The original fixture contrasts both IME states,
three arrival edges, and an opcode changed during sleep. No external test ROM
was executed to establish this projection.


## Normal STOP stable-clock boundary

At the existing Pan Docs pin, `Reducing_Power_Consumption.md` identifies selected
P10-P13 low as the STOP release source. SameBoy at the existing pin checks JOYP's
low nibble independently of IE in `GB_cpu_run`, then advances eight cycles after
leaving STOP. This corroborates selected-line release, not a hardware-exact
settling duration: its STOP entry read timing is explicitly unverified.
The pinned SonoSooS example resumes with a fresh fetch after the discarded
padding byte. We project that stable fetch onto the normal PC increment
observation, without claiming an analog waveform.

Gekkio's `control_unit.vhd` separates system-clock release (`wake`, lines148-155)
from CPU-clock release (`intr_wake_sync` or `startup_begin`, line121).
`interrupts.vhd` line55 combines enabled requests and NMI for `intr_wake`.
The retained `test_soc.vhd` initializes `wake` to zero without a JOYP driver, so
it does not independently resolve button-only/no-IE restart. The CPU boundary
therefore delegates oscillator qualification to the enclosing power owner and
assigns no invented fixed delay. The approved [CPU model](MAS_cpu.md#qualified-stop-wake)
uses deterministic ordinary interrupt behavior after stable qualification when
IME-enabled requests occur during restart. This is an explicit digital analog
approximation, not a new claim from these physical-source references.


## STOP execution IDU projection

At the existing Gekkio pin, stage1 line482 selects `op_nop_stop_s0xx` for the
actual NOP/STOP execution row. Stage2 includes it in `addr_pc` (335), `m1` (363)
and `idu_inc` (449). The register file drives all16 PC bits onto `idu_in`
(163-167), which is also the address output in `cpu_core` (164). Stage3 routes
the IDU result to PC (549-560). Thus a completed STOP execution has the pre-fetch
PC write-like observation; architectural one-byte retirement does not establish
absence of IDU activity. The interrupt row separately selects PC decrement,
which remains write-like under the typed convention. This is the same digital
M-cycle projection as ordinary fetch/IRQ effects, not a promise about partial-M
analog shutdown transitions or increment/decrement direction on physical pins.
