# Audio gateway

Owner and related contracts: [ownership map](../../../ownership.md).

Status: present-but-unimplemented DMG APU. The gateway serves `FF10`-`FF26`
register access and `FF30`-`FF3F` wave-RAM access so the CPU never faults on
them. There is no channel, frame sequencer, length or envelope timer, DAC,
mixer or audio output; the charter defers audio synthesis.

## Contract

`n2m_apu` owns the `MEMORY_APU` and `MEMORY_WAVE` destinations produced by the
[memory decoder](../memory/MAS_memory.md#address-ownership-decoder). It uses
`clk_sys`, global and core reset, and the shared `gb_tick`. Wave bytes stay in
the [memory owner's](../memory/MAS_memory.md) generated store; this gateway
holds no sample array.

| Port | Direction, width | Meaning |
|---|---|---|
| `clk_sys`, `reset_sys`, `core_reset` | input, 1 each | Shared system clock and resets |
| `gb_tick` | input, 1 | Emulated enable; a commit may occur only on one |
| `io_prepare` | input, 1 | Prepared CPU access already qualified to this owner |
| `io_commit` | input, 1 | Accepted T4 access already qualified to this owner |
| `io_write`, `io_address`, `io_wdata` | input, 1/16/8 | Direction, CPU address and byte |
| `io_selected` | output, 1 | Address is an audio register or a wave byte |
| `io_rdata`, `io_valid` | output, 8/1 | Read byte and its validity for the prepared address |
| `wave_read`, `wave_write` | output, 1 each | Wave-store read and write enables for the CPU access |
| `wave_address`, `wave_wdata` | output, 4/8 | Wave byte offset and write byte |
| `wave_rdata`, `wave_valid` | input, 8/1 | Registered wave byte and its validity |

- **POWERED OFF:** The APU is always off. `NR52` bit 7 reads zero, no channel
  is ever active, and every audio-register write is ignored, including a write
  that would power the APU on. Stored register state is the generated
  `PERIPHERAL_FILL`, so each register read equals its read-back mask below.
- **READ MASKS:** Unimplemented and unused audio-register bits read back as
  one. `FF10`-`FF25` return the fixed per-register mask in the table below.
- **NR52:** `FF26` reports power in bit 7 and channel status in bits 3:0, with
  bits 6:4 set. With the APU off and no channel active the read is `70`.
- **WAVE RAM:** `FF30`-`FF3F` is plain readable and writable storage. A read
  presents the registered store byte with its own validity, one system edge
  after the prepared request; a committed write replaces one byte. No channel
  restricts access because none exists. Reset fill and clearing belong to the
  [memory owner](../memory/MAS_memory.md), which suppresses the gateway write
  while clearing.
- **COMMIT BOUNDARY:** A commit outside `gb_tick`, or for an unselected
  address, violates the contract and fires the named `APU_COMMIT_BOUNDARY`
  assertion. A prepared access must select this owner. A read and a write of
  the wave store never coincide.

### Read-back masks

| Register | Address | Mask | Register | Address | Mask |
|---|---|---|---|---|---|
| NR10 | `FF10` | `80` | NR32 | `FF1C` | `9F` |
| NR11 | `FF11` | `3F` | NR33 | `FF1D` | `FF` |
| NR12 | `FF12` | `00` | NR34 | `FF1E` | `BF` |
| NR13 | `FF13` | `FF` | NR41 | `FF20` | `FF` |
| NR14 | `FF14` | `BF` | NR42 | `FF21` | `00` |
| NR21 | `FF16` | `3F` | NR43 | `FF22` | `00` |
| NR22 | `FF17` | `00` | NR44 | `FF23` | `BF` |
| NR23 | `FF18` | `FF` | NR50 | `FF24` | `00` |
| NR24 | `FF19` | `BF` | NR51 | `FF25` | `00` |
| NR30 | `FF1A` | `7F` | NR52 | `FF26` | `70` |
| NR31 | `FF1B` | `FF` | | | |

`FF15`, `FF1F` and `FF27`-`FF2F` are unassigned I/O. They never reach this
owner; the CPU port returns its fixed `FF` for them.

## Sources

| Source | Pin | Use |
|---|---|---|
| [SameBoy Core](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/apu.c) | `213a12ce93d66b105a113debd9396306066a7cfc` | The `read_mask` table in `GB_apu_read` supplies every per-register mask above, and its `NR52` branch supplies the `70` set bits. `GB_apu_write` returns early for a register write while `global_enable` is clear, and masks the `NRx1` duty bits off on monochrome models, so a never-powered APU reads exactly the mask. Research only, no imported code. |
| [Pan Docs](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Audio_Registers.md) | `fe246067b695b5404a4a6a47efb4fd6d921ececb` | `NR52` bit 7 is audio power and bits 3:0 are read-only channel status; powering the APU off clears the registers and makes them read-only. It does not tabulate the per-register read-back masks; those come from the pinned SameBoy model. Research only, no imported code. |

## Known divergence

A DMG game that powers the APU on then reads `NR52` sees `F0`; this gateway
returns `70`. Channel status, length, envelope and sweep behavior likewise do
not exist. Restoring them belongs to a future audio implementation, not to this
gateway, which exists only so those accesses do not fault the system.

## Alignment and verification

[RTL](../../../../src/rtl/audio/n2m_apu.sv) implements the named rules.
The [audio test plan](../../../../src/dv/audio/README.md) maps each to
independent checks in the builder's
[targets](../../../../src/dv/builder/targets.json).
