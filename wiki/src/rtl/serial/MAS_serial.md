# Serial registers

Owner and related contracts: [ownership map](../../../ownership.md).

Status: present-but-unimplemented DMG serial port. SB and SC are served so the
CPU never faults on `FF01`-`FF02`. There is no shift clock, no transfer
completion and no serial interrupt.

## Contract

`n2m_serial` owns the `MEMORY_SERIAL` destination produced by the
[memory decoder](../memory/MAS_memory.md#address-ownership-decoder). It uses
`clk_sys`, global and core reset, and the shared `gb_tick`.

| Port | Direction, width | Meaning |
|---|---|---|
| `clk_sys`, `reset_sys`, `core_reset` | input, 1 each | Shared system clock and resets |
| `gb_tick` | input, 1 | Emulated enable; a commit may occur only on one |
| `io_commit` | input, 1 | Accepted T4 access already qualified to this owner |
| `io_write`, `io_address`, `io_wdata` | input, 1/16/8 | Direction, CPU address and byte |
| `io_selected` | output, 1 | Address is `FF01` or `FF02` |
| `io_rdata` | output, 8 | Side-effect-free read byte for the prepared address |

- **SB:** `FF01` is a plain readable and writable byte. A committed write
  replaces it; a read returns it unchanged.
- **SC:** `FF02` retains only transfer enable (bit 7) and clock select (bit 0).
  Bits 6:1 are unused on DMG and read back as one, so a read is the retained
  bits OR `7E`.
- **NO TRANSFER:** An enabled transfer is retained and never completes. No byte
  is shifted, `SB` is not modified by `SC`, and this owner raises no interrupt.
  The [system composition](../system/MAS_system.md) holds the serial interrupt
  level inactive.
- **RESET:** Both resets restore the generated `PERIPHERAL_FILL` state, so `SB`
  reads `00` and `SC` reads `7E`. Reset dominates a competing write.
- **COMMIT BOUNDARY:** A commit outside `gb_tick`, or for an unselected
  address, violates the contract and fires the named `SERIAL_COMMIT_BOUNDARY`
  assertion. Prepared but uncommitted accesses change nothing.

## Sources

| Source | Pin | Use |
|---|---|---|
| [SameBoy Core](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/Core/memory.c) | `213a12ce93d66b105a113debd9396306066a7cfc` | `GB_write_memory` stores `SC` as `value \| (~0x83)` and forces bit 1 on non-CGB models; `GB_read_memory` returns the stored byte. A DMG `SC` read is therefore the written value OR `7E`. Research only, no imported code. |
| [Pan Docs](https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/Serial_Data_Transfer_(Link_Cable).md) | `fe246067b695b5404a4a6a47efb4fd6d921ececb` | `SC` bit 7 is transfer enable, bit 0 is clock select, and bit 1 is CGB only. It does not state the DMG read-back of the unused bits; the mask above comes from the pinned SameBoy model. |

## Alignment and verification

[RTL](../../../../src/rtl/serial/n2m_serial.sv) implements the named rules.
The [serial test plan](../../../../src/dv/serial/README.md) maps each to
independent checks in the builder's
[targets](../../../../src/dv/builder/targets.json).
