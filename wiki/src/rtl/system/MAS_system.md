# v0.5 system composition

`n2m_v05_system` composes the delivered owners used by the original
[issue88](https://github.com/amichai-bd/nand2mario/issues/88) program. It does not
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

The UART owner supplies core reset, profile, epoch, pause and effective input.
Initialization completes only when CPU and backing-store initialization complete.
The CPU uses resolved IF/IE for observation, the memory CPU port for prepared
reads and committed writes, and the shared timebase. Host input reaches the real
JOYP owner atomically; its event feeds the interrupt event input. VBlank and STAT
levels feed the interrupt level inputs. CPU completion controls STEP through the
existing UART boundary.

The memory CPU port routes ROM/RAM to the explicit Intel backing stores and
video accesses through PPU permissions. The PPU independently uses the stores'
VRAM and OAM read ports. JOYP, interrupt and PPU registers have their actual
owners. Unused peripheral destinations reject service. The original program
must not access them or execute STOP; the named `V05_NO_STOP` assertion makes
that bounded program condition explicit. Timer, DMA, serial transfer and audio
behavior are not implemented by this composition.

The PPU source feeds the actual frame bridge and immutable snapshot owner.
System and pixel resets remain distinct; core reset follows the existing
bridge/snapshot ownership rules. VGA outputs are exposed. All product stores
use the shared Intel wrapper, with the same parameters in simulation and fit.

The acceptance run must remain unpaused by the host throughout the first-image
and 600-interval bounds. CPU HALT preserves peripheral ticks. Independent
observation checks every source pixel and retirement, including activity while
UART input transactions run. Snapshots cannot substitute for that observation.

Combined constrained fit and full issue88 execution are required before claiming
acceptance. Existing component results support their own unchanged scope only.
