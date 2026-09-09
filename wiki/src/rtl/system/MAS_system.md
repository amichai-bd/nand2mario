# v0.5 system composition

[`n2m_v05_system`](../../../../src/rtl/system/n2m_v05_system.sv) composes the owners used by the original
[v0.5 program](../../../../src/sw/v05/main.asm). It does not
add CPU, memory, interrupt or pixel semantics. The program and acceptance follow the [v0.5 fixture](../../dv/v05/SPEC.md) under the [charter](../../project-charter.md#release-acceptance) and
[software specification](../../../tools/sw/SPEC.md).

The module accepts 25 MHz `clk_sys`, 25.2 MHz `clk_pix` and their qualified,
asynchronously asserted domain resets. The enclosing clock/reset owner supplies
these signals. The composed fit uses the real parallel PLL wrapper driven by
the 50 MHz board reference and the actual bridge CDC constraints. Virtual UART
and observation ports make this a placement proof, not a programmable board image.
UART defaults to 115200 baud. Simulation may explicitly override `UART_BAUD`,
subject to the UART owner's minimum eight system clocks per bit. An accelerated
transport test does not establish physical UART acceptance.

The additive `v05-board` target uses the same composition with physical UART
D0/D1 and KEY0 reset, following the [board pin contract](../../fpga-controls.md).
Only diagnostic outputs remain virtual. `BUILD_ID` propagates the producing
128-bit build identity to the UART owner; the placement/simulation default stays
unchanged. Physical pin, wiring and voltage qualification remains an open
[board bring-up gap](https://github.com/amichai-bd/nand2mario/issues/28);
simulation and placement proofs do not satisfy it.

The UART owner supplies core reset, profile, epoch, pause and effective input.
Initialization completes only when CPU and backing-store initialization complete.
The CPU uses resolved IF/IE for observation, the DMA owner's memory CPU port for
prepared reads and committed writes, and the shared timebase. Host input reaches the real
JOYP owner atomically; its event feeds the interrupt event input. VBlank and STAT
levels and the timer request feed the interrupt level inputs. CPU completion controls STEP through the
existing UART boundary.

The public `physical_commit` and `physical_buttons` inputs use the same
`clk_sys`, coherent mask and off-tick acceptance contract as the
[shared input owner](../input/MAS_input.md). They connect directly to that
owner inside UART. `effective_buttons` and `input_source_observe` expose its
existing authoritative observations. UART remains the reset default. No input
queue, producer, synchronization or extra state is added here. The current
`v05_proof` board wrapper ties physical input inactive; board acquisition,
component wiring and calibration remain an open
[physical controls gap](https://github.com/amichai-bd/nand2mario/issues/156).

The [DMA owner](../dma/MAS_dma.md) arbitrates CPU and transfer traffic against
one Intel backing store. It owns FF46 and routes video accesses through the
PPU's read or write permission selected by the prepared CPU plan. Both PPU
read ports pass through the owner's collision suppression and registered OAM
forwarding. Timer, JOYP, interrupt and PPU registers have their actual
owners. Unused peripheral destinations reject service. The original program
must not access them or execute STOP; the named `V05_NO_STOP` assertion makes
that bounded program condition explicit. Serial transfer and audio
behavior are not implemented by this composition.

The CPU supplies its complete typed bus plan, address effect, resolved/sample
qualification, continuous M-cycle phase and HALT/STOP state to the DMA owner.
The PPU supplies its scan index, pair phase, late-write indication and future
late window. Host pause withholds the shared tick; CPU HALT suspends transfer
progress as specified by MAS_dma. The raw store write data comes from the DMA
arbiter, including its existing corruption and transfer projections.

A registered CPU fault suppresses subsequent DMA ticks, initialization/service
enable, requests, commits and address-effect qualification. It does not reset
memory or other peripheral owners, nor cancel the accepting edge which first
detects a missing CPU response. No response-valid feedback gates DMA work.
UART loading and backing-store initialization retain their existing ports.

The [timer owner](../timer/MAS_timer.md) provides side-effect-free pre-A reads
and receives accepted T4 writes for DIV/TIMA/TMA/TAC through `MEMORY_TIMER`.
It uses the shared system clock, global/core reset and `gb_tick`; host pause
holds elapsed timer time while CPU HALT does not. The typed request pulse feeds
interrupt level bit2 through the existing post-A/B capture, including a B edge
after host pause. CPU `divider_reset_request` reaches the timer, but this wiring
does not expand the composition's STOP/power contract. Timer reload, write
priority, reset values and request semantics remain owned by MAS_timer.

The PPU source feeds the actual frame bridge and immutable snapshot owner.
System and pixel resets remain distinct; core reset follows the existing
bridge/snapshot ownership rules. VGA outputs are exposed. All product stores
use the shared Intel wrapper, with the same parameters in simulation and fit.

The [revised acceptance matrix](../../dv/v05/SPEC.md#revised-milestone-matrix)
keeps its selected simulation window unpaused by the host until final completion.
CPU HALT preserves peripheral ticks. Independent
observation checks every source pixel and retirement, including activity while
UART input transactions run. Snapshots cannot substitute for that observation.

Qualified constrained fit and the complete revised milestone matrix are required before claiming
acceptance. Existing component results support their own unchanged scope only.
