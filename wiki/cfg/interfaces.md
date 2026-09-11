# Interface tables

Generated from cfg/interfaces.json by tools/n2m/interfaces.py; DO NOT EDIT.

Source SHA-256: `80618216aec777c06eace757549d9bab43315603dc0655f78ee9b833f72a429a`.

See [interface contracts](../src/rtl/interfaces/MAS_interfaces.md) for behavior, reset, framing and tests.

## Gb

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `GB_ADDRESS_BITS` | 8 | `0x10` | CPU byte address width |
| `GB_DATA_BITS` | 8 | `0x8` | CPU byte data width |
| `GB_ROM0_START` | 16 | `0x0` | Fixed cartridge bank; file offset equals address in dmg-direct-v1 |
| `GB_ROM0_END` | 16 | `0x3FFF` | Inclusive end |
| `GB_ROM1_START` | 16 | `0x4000` | Second fixed bank in dmg-direct-v1; file offset equals address |
| `GB_ROM1_END` | 16 | `0x7FFF` | Inclusive end |
| `GB_VRAM_START` | 16 | `0x8000` | Video RAM |
| `GB_VRAM_END` | 16 | `0x9FFF` | Inclusive end |
| `GB_CART_RAM_START` | 16 | `0xA000` | Cartridge RAM space; absent in direct profile |
| `GB_CART_RAM_END` | 16 | `0xBFFF` | Inclusive end |
| `GB_WRAM_START` | 16 | `0xC000` | Internal work RAM |
| `GB_WRAM_END` | 16 | `0xDFFF` | Inclusive end |
| `GB_ECHO_START` | 16 | `0xE000` | Alias of C000-DDFF |
| `GB_ECHO_END` | 16 | `0xFDFF` | Inclusive end |
| `GB_OAM_START` | 16 | `0xFE00` | Object attributes |
| `GB_OAM_END` | 16 | `0xFE9F` | Inclusive end |
| `GB_UNUSABLE_START` | 16 | `0xFEA0` | Reserved; not general RAM |
| `GB_UNUSABLE_END` | 16 | `0xFEFF` | Inclusive end |
| `GB_IO_START` | 16 | `0xFF00` | DMG I/O |
| `GB_IO_END` | 16 | `0xFF7F` | Inclusive end |
| `GB_HRAM_START` | 16 | `0xFF80` | High RAM |
| `GB_HRAM_END` | 16 | `0xFFFE` | Inclusive end |
| `GB_IE_START` | 16 | `0xFFFF` | Interrupt enable |
| `GB_IE_END` | 16 | `0xFFFF` | Inclusive end |

## Gb Reg

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `GB_REG_JOYP` | 16 | `0xFF00` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_SB` | 16 | `0xFF01` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_SC` | 16 | `0xFF02` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_DIV` | 16 | `0xFF04` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_TIMA` | 16 | `0xFF05` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_TMA` | 16 | `0xFF06` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_TAC` | 16 | `0xFF07` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_IF` | 16 | `0xFF0F` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR10` | 16 | `0xFF10` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR11` | 16 | `0xFF11` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR12` | 16 | `0xFF12` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR13` | 16 | `0xFF13` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR14` | 16 | `0xFF14` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR21` | 16 | `0xFF16` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR22` | 16 | `0xFF17` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR23` | 16 | `0xFF18` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR24` | 16 | `0xFF19` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR30` | 16 | `0xFF1A` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR31` | 16 | `0xFF1B` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR32` | 16 | `0xFF1C` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR33` | 16 | `0xFF1D` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR34` | 16 | `0xFF1E` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR41` | 16 | `0xFF20` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR42` | 16 | `0xFF21` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR43` | 16 | `0xFF22` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR44` | 16 | `0xFF23` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR50` | 16 | `0xFF24` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR51` | 16 | `0xFF25` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_NR52` | 16 | `0xFF26` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_LCDC` | 16 | `0xFF40` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_STAT` | 16 | `0xFF41` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_SCY` | 16 | `0xFF42` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_SCX` | 16 | `0xFF43` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_LY` | 16 | `0xFF44` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_LYC` | 16 | `0xFF45` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_DMA` | 16 | `0xFF46` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_BGP` | 16 | `0xFF47` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_OBP0` | 16 | `0xFF48` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_OBP1` | 16 | `0xFF49` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_WY` | 16 | `0xFF4A` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_WX` | 16 | `0xFF4B` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_BOOT_DISABLE` | 16 | `0xFF50` | 8-bit DMG register address; access behavior belongs to subsystem contract |
| `GB_REG_IE` | 16 | `0xFFFF` | 8-bit DMG register address; access behavior belongs to subsystem contract |

## Gb View

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `GB_VIEW_WAVE_START` | 16 | `0xFF30` | 16 wave bytes |
| `GB_VIEW_WAVE_END` | 16 | `0xFF3F` | Inclusive end |
| `GB_VIEW_LDH_START` | 16 | `0xFF00` | LDH full-address range |
| `GB_VIEW_LDH_END` | 16 | `0xFFFF` | Inclusive end |
| `GB_VIEW_TILES_START` | 16 | `0x8000` | Tile storage |
| `GB_VIEW_TILES_END` | 16 | `0x97FF` | Inclusive end |
| `GB_VIEW_MAP0_START` | 16 | `0x9800` | 32 by 32 tile map |
| `GB_VIEW_MAP1_START` | 16 | `0x9C00` | 32 by 32 tile map |

## Vector

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `VECTOR_RST_00` | 16 | `0x0` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_RST_08` | 16 | `0x8` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_RST_10` | 16 | `0x10` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_RST_18` | 16 | `0x18` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_RST_20` | 16 | `0x20` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_RST_28` | 16 | `0x28` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_RST_30` | 16 | `0x30` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_RST_38` | 16 | `0x38` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_VBLANK` | 16 | `0x40` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_STAT` | 16 | `0x48` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_TIMER` | 16 | `0x50` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_SERIAL` | 16 | `0x58` | Eight-byte reserved vector slot in direct profile |
| `VECTOR_JOYPAD` | 16 | `0x60` | Eight-byte reserved vector slot in direct profile |

## Profile

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `PROFILE_DIRECT_ID` | 8 | `0x1` | dmg-direct-v1; original v0.5 programs only |
| `PROFILE_ROM_BYTES` | 32 | `0x8000` | Exact load image length |
| `PROFILE_BANK_BYTES` | 16 | `0x4000` | Section boundary |
| `PROFILE_HEADER_START` | 16 | `0x100` | Packager reservation inclusive |
| `PROFILE_HEADER_END` | 16 | `0x14F` | Packager reservation inclusive |
| `PROFILE_VECTOR_SLOT_BYTES` | 8 | `0x8` | Each vector reservation length |
| `PROFILE_PC` | 16 | `0x100` | First opcode after reset/resume |
| `PROFILE_SP` | 16 | `0xFFFE` | Stack pointer |
| `PROFILE_A` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_F` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_B` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_C` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_D` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_E` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_H` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_L` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_IME` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_IME_DELAY` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_CPU_HALT` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_CPU_STOP` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_HALT_BUG` | 8 | `0x0` | Direct reset CPU state |
| `PROFILE_RAM_FILL` | 8 | `0x0` | Reset fills WRAM, HRAM, VRAM, OAM, wave RAM |
| `PROFILE_JOYP_SELECT` | 8 | `0x30` | Neither group selected |
| `PROFILE_BOOT_MAPPED` | 8 | `0x0` | No boot ROM; unmapping is permanent |
| `PROFILE_PERIPHERAL_FILL` | 8 | `0x0` | Writable peripheral storage and internal counters; read masks still apply |

## Host

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `HOST_ADDRESS_BITS` | 8 | `0x20` | Host-only byte address width |
| `HOST_DATA_BITS` | 8 | `0x20` | Host register width |
| `HOST_BASE` | 32 | `0x10000` | Outside the CPU address range |

## Host Reg

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `HOST_REG_ABI` | 32 | `0x10000` | Interface ABI version; read-only |
| `HOST_REG_STATE` | 32 | `0x10004` | Host state enum; read-only |
| `HOST_REG_IMAGE_VALID` | 32 | `0x10008` | 0 or 1; read-only |
| `HOST_REG_PROFILE` | 32 | `0x1000C` | Loaded profile ID or 0; read-only |
| `HOST_REG_DOT_LO` | 32 | `0x10010` | Low half of paused emulated dot count; read-only |
| `HOST_REG_DOT_HI` | 32 | `0x10014` | High half; pause for coherent multi-read; read-only |
| `HOST_REG_RETIRE_LO` | 32 | `0x10018` | Low half of retirement count; read-only |
| `HOST_REG_RETIRE_HI` | 32 | `0x1001C` | High half; pause for coherent multi-read; read-only |
| `HOST_REG_INPUT` | 32 | `0x10020` | Active-high host button mask; writable by INPUT or WRITE_HOST |
| `HOST_REG_SNAPSHOT_VALID` | 32 | `0x10024` | 0 or 1; read-only |
| `HOST_REG_SNAPSHOT_SEQ_LO` | 32 | `0x10028` | Latched source frame sequence low; read-only |
| `HOST_REG_SNAPSHOT_SEQ_HI` | 32 | `0x1002C` | Latched source frame sequence high; read-only |
| `HOST_REG_BUILD_ID_0` | 32 | `0x10030` | Least-significant 32 bits of 128-bit build identifier; read-only |
| `HOST_REG_BUILD_ID_1` | 32 | `0x10034` | Build identifier bits 63:32; read-only |
| `HOST_REG_BUILD_ID_2` | 32 | `0x10038` | Build identifier bits 95:64; read-only |
| `HOST_REG_BUILD_ID_3` | 32 | `0x1003C` | Build identifier bits 127:96; read-only |
| `HOST_REG_SNAPSHOT_EPOCH` | 32 | `0x10040` | Latched source core-reset epoch; read-only |
| `HOST_REG_INPUT_SOURCE` | 32 | `0x10044` | Selected input source: UART or physical. |
| `HOST_REG_INPUT_PHYSICAL` | 32 | `0x10048` | Latest coherent physical button mask; read only. |
| `HOST_REG_INPUT_EFFECTIVE` | 32 | `0x1004C` | Effective Game Boy button mask; read only. |
| `HOST_REG_IO_LCDC` | 32 | `0x10050` | DMG LCDC committed byte; read-only live view |
| `HOST_REG_IO_STAT` | 32 | `0x10054` | DMG STAT enables, coincidence and live mode; bit 7 zero; read-only live view |
| `HOST_REG_IO_SCY` | 32 | `0x10058` | DMG SCY committed byte; read-only live view |
| `HOST_REG_IO_SCX` | 32 | `0x1005C` | DMG SCX committed byte; read-only live view |
| `HOST_REG_IO_LY` | 32 | `0x10060` | DMG readable LY; read-only live view |
| `HOST_REG_IO_LYC` | 32 | `0x10064` | DMG LYC committed byte; read-only live view |
| `HOST_REG_IO_BGP` | 32 | `0x10068` | DMG BGP committed byte; read-only live view |
| `HOST_REG_IO_OBP0` | 32 | `0x1006C` | DMG OBP0 committed byte; read-only live view |
| `HOST_REG_IO_OBP1` | 32 | `0x10070` | DMG OBP1 committed byte; read-only live view |
| `HOST_REG_IO_WY` | 32 | `0x10074` | DMG WY committed byte; read-only live view |
| `HOST_REG_IO_WX` | 32 | `0x10078` | DMG WX committed byte; read-only live view |
| `HOST_REG_IO_DIV` | 32 | `0x1007C` | DMG DIV, the upper byte of the internal divider; read-only live view |
| `HOST_REG_IO_TIMA` | 32 | `0x10080` | DMG TIMA committed byte; read-only live view |
| `HOST_REG_IO_TMA` | 32 | `0x10084` | DMG TMA committed byte; read-only live view |
| `HOST_REG_IO_TAC` | 32 | `0x10088` | DMG TAC committed control in bits 2:0; read-only live view |
| `HOST_REG_IO_IF` | 32 | `0x1008C` | DMG IF committed request flags in bits 4:0; read-only live view |
| `HOST_REG_IO_IE` | 32 | `0x10090` | DMG IE committed byte; read-only live view |
| `HOST_REG_IO_LCD_STATUS` | 32 | `0x10094` | LCDC, STAT and LY sampled on one edge; LY in bits 7:0; read-only live view |

## State

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `STATE_PAUSED` | 8 | `0x0` | Frozen emulated state |
| `STATE_RUNNING` | 8 | `0x1` | Emulated time advances |
| `STATE_LOADING` | 8 | `0x2` | Paused; incomplete image cannot run |

## Button

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `BUTTON_RIGHT` | 8 | `0x1` | Active-high pressed bit in host mask; no opposite-direction filtering |
| `BUTTON_LEFT` | 8 | `0x2` | Active-high pressed bit in host mask; no opposite-direction filtering |
| `BUTTON_UP` | 8 | `0x4` | Active-high pressed bit in host mask; no opposite-direction filtering |
| `BUTTON_DOWN` | 8 | `0x8` | Active-high pressed bit in host mask; no opposite-direction filtering |
| `BUTTON_A` | 8 | `0x10` | Active-high pressed bit in host mask; no opposite-direction filtering |
| `BUTTON_B` | 8 | `0x20` | Active-high pressed bit in host mask; no opposite-direction filtering |
| `BUTTON_SELECT` | 8 | `0x40` | Active-high pressed bit in host mask; no opposite-direction filtering |
| `BUTTON_START` | 8 | `0x80` | Active-high pressed bit in host mask; no opposite-direction filtering |

## Wire

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `WIRE_VERSION` | 8 | `0x1` | Packet ABI |
| `WIRE_REQUEST` | 8 | `0x0` | Host to FPGA |
| `WIRE_RESPONSE` | 8 | `0x1` | FPGA to host |
| `WIRE_MAX_PAYLOAD` | 16 | `0x100` | Decoded payload byte limit |
| `WIRE_CRC_POLY` | 16 | `0x1021` | CRC-16 polynomial; non-reflected |
| `WIRE_CRC_INIT` | 16 | `0xFFFF` | CRC-16 initial value; xorout zero |
| `WIRE_BAUD` | 32 | `0x1C200` | Initial UART baud, 8N1 LSB-first data bits, no flow control |
| `WIRE_FRAME_TIMEOUT_MS` | 16 | `0x1F4` | Incomplete frame discarded after idle interval |
| `WIRE_RESPONSE_TIMEOUT_MS` | 16 | `0x7D0` | Host timeout; fail uncertain without automatic retry |
| `WIRE_STEP_MAX_DOTS` | 32 | `0x11250` | Maximum step budget |
| `WIRE_ABI` | 32 | `0x1` | Host register ABI |
| `WIRE_CRC32_POLY` | 32 | `0xEDB88320` | Reflected CRC-32/ISO-HDLC polynomial |
| `WIRE_CRC32_INIT` | 32 | `0xFFFFFFFF` | Initial CRC32 register and final XOR value |
| `WIRE_RUN_DOTS_MAX` | 32 | `0x11250` | Maximum exact-dot request |
| `WIRE_RUN_DOTS_COUNT` | 8 | `0x0` | Requested tick count completed |
| `WIRE_RUN_DOTS_STOPPED` | 8 | `0x1` | CPU STOP ended bounded execution |

## Status

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `STATUS_OK` | 8 | `0x0` | Completed |
| `STATUS_BAD_VERSION` | 8 | `0x1` | Unsupported packet version |
| `STATUS_BAD_COMMAND` | 8 | `0x2` | Unknown command |
| `STATUS_BAD_LENGTH` | 8 | `0x3` | Wrong payload length |
| `STATUS_BAD_VALUE` | 8 | `0x4` | Range, alignment, profile, or reserved value invalid |
| `STATUS_BAD_STATE` | 8 | `0x5` | Command not permitted in current state |
| `STATUS_BAD_IMAGE` | 8 | `0x6` | Incomplete image or whole-image CRC mismatch |
| `STATUS_NO_FRAME` | 8 | `0x7` | No complete source frame since reset |
| `STATUS_STEP_LIMIT` | 8 | `0x8` | Budget exhausted; paused without next retirement |
| `STATUS_SEQUENCE` | 8 | `0x9` | Sequence reused with different request |

## Trace

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `TRACE_VERSION` | 8 | `0x1` | Retirement record ABI |
| `TRACE_INSTRUCTION` | 8 | `0x0` | Completed instruction |
| `TRACE_INTERRUPT` | 8 | `0x1` | Completed interrupt entry; separate event, not instruction retirement |

## Frame

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `FRAME_WIDTH` | 16 | `0xA0` | Visible pixels per row |
| `FRAME_HEIGHT` | 16 | `0x90` | Visible rows |
| `FRAME_PIXEL_BITS` | 8 | `0x2` | Final shade index |
| `FRAME_BYTES` | 16 | `0x1680` | Four shades per byte; first pixel in bits 1:0 |

## Command

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `COMMAND_PING` | 8 | `0x1` | Return ABI. |
| `COMMAND_READ_HOST` | 8 | `0x2` | Read exactly one aligned host register; unknown addresses fail. |
| `COMMAND_RESET` | 8 | `0x3` | Pause at a dot boundary and initialize direct state; retain valid ROM and profile. |
| `COMMAND_RUN` | 8 | `0x4` | Resume from retained phase; acknowledgement after transition. |
| `COMMAND_HALT` | 8 | `0x5` | Host pause at next dot boundary; already paused is idempotent. |
| `COMMAND_STEP` | 8 | `0x6` | Advance until next completed instruction or the requested dot budget; interrupt entry does not satisfy retirement. |
| `COMMAND_LOAD_BEGIN` | 8 | `0x7` | Validate metadata, pause/reset, invalidate old image and start a fresh load. |
| `COMMAND_LOAD_WRITE` | 8 | `0x8` | Write 1..252 image bytes, marking each byte present; ranges cannot cross image end. |
| `COMMAND_LOAD_END` | 8 | `0x9` | Require every byte written and expected CRC32; reset and mark image valid, paused. |
| `COMMAND_READ_ROM` | 8 | `0xA` | Read exact image storage bytes; host offsets never denote CPU or host registers. |
| `COMMAND_INPUT` | 8 | `0xB` | Apply full button mask at next dot boundary, or immediately while paused; return completed dot count. |
| `COMMAND_SNAPSHOT` | 8 | `0xC` | Copy last completed source frame to dedicated immutable host snapshot; fail if none since core reset. |
| `COMMAND_READ_FRAME` | 8 | `0xD` | Read dedicated snapshot, unchanged until next successful SNAPSHOT or global reset. |
| `COMMAND_WRITE_HOST` | 8 | `0xE` | Write a whitelisted host control register. |
| `COMMAND_RUN_DOTS` | 8 | `0xF` | Run a bounded number of real dots and pause |

## Input Source

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `INPUT_SOURCE_UART` | 8 | `0x0` | Use the host button mask; reset default. |
| `INPUT_SOURCE_PHYSICAL` | 8 | `0x1` | Use the coherent physical button mask. |

## Host Write Mask

| Constant | Bits | Value | Meaning |
|---|---|---|---|
| `HOST_WRITE_MASK_INPUT` | 32 | `0xFF` | Writable host button mask bits. |
| `HOST_WRITE_MASK_INPUT_SOURCE` | 32 | `0x1` | Writable source selection bit. |

## Packet Header record

10 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `version` | 0 | 8 | Wire ABI |
| `kind` | 1 | 8 | Request or response |
| `seq` | 2 | 32 | Client correlation token |
| `command` | 6 | 8 | Command ID |
| `status` | 7 | 8 | Zero in requests |
| `length` | 8 | 16 | Payload byte length |

## Read Host record

4 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `address` | 0 | 32 | Aligned host register address |

## Word record

4 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `value` | 0 | 32 | Unsigned value |

## Load Begin record

9 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `profile` | 0 | 8 | Direct profile ID |
| `size` | 1 | 32 | Exact image byte length |
| `crc32` | 5 | 32 | Whole image CRC-32/ISO-HDLC |

## Offset record

4 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `offset` | 0 | 32 | ROM file offset or snapshot byte offset |

## Read Range record

6 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `offset` | 0 | 32 | Byte offset |
| `count` | 4 | 16 | 1 through maximum payload bytes |

## Input record

1 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `buttons` | 0 | 8 | All eight active-high button states |

## Dot record

8 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `dot` | 0 | 64 | Number of completed emulated dots at transition |

## Snapshot record

24 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `epoch` | 0 | 32 | Core-reset epoch of source frame |
| `seq` | 4 | 64 | Source frame sequence |
| `dot` | 12 | 64 | Source frame completion dot |
| `size` | 20 | 32 | Packed frame bytes |

## Retirement record

48 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `version` | 0 | 8 | Trace ABI |
| `kind` | 1 | 8 | Instruction or interrupt entry |
| `epoch` | 2 | 32 | Core-reset epoch since global reset |
| `seq` | 6 | 64 | Event index from zero within epoch |
| `dot` | 14 | 64 | Completed dots at event end |
| `pc_before` | 22 | 16 | PC before instruction or interrupt entry |
| `pc_after` | 24 | 16 | PC after completion |
| `opcode` | 26 | 24 | Fetched bytes in bits 7:0 then 15:8 then 23:16; unused bytes zero |
| `opcode_length` | 29 | 8 | 1..3 for instruction; zero for interrupt entry |
| `a` | 30 | 8 | Post-event CPU register |
| `f` | 31 | 8 | Post-event flags; low nibble zero |
| `b` | 32 | 8 | Post-event CPU register |
| `c` | 33 | 8 | Post-event CPU register |
| `d` | 34 | 8 | Post-event CPU register |
| `e` | 35 | 8 | Post-event CPU register |
| `h` | 36 | 8 | Post-event CPU register |
| `l` | 37 | 8 | Post-event CPU register |
| `sp` | 38 | 16 | Post-event stack pointer |
| `ime` | 40 | 8 | Post-event interrupt master enable: 0 or 1 |
| `ime_delay` | 41 | 8 | Deferred EI state: 0 or 1 |
| `halted` | 42 | 8 | CPU HALT: 0 or 1 |
| `stopped` | 43 | 8 | CPU STOP: 0 or 1 |
| `halt_bug` | 44 | 8 | Pending suppressed PC increment: 0 or 1 |
| `ie` | 45 | 8 | Interrupt-enable storage byte |
| `iflags` | 46 | 8 | Interrupt-request low five storage bits |
| `buttons` | 47 | 8 | Effective Game Boy button mask at event end |

## Write Host record

8 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `address` | 0 | 32 | Whitelisted host register address. |
| `value` | 4 | 32 | Value with all reserved bits zero. |

## Run Dots record

13 bytes, in listed order; each field is unsigned little-endian.

| Field | Byte offset | Bits | Meaning |
|---|---|---|---|
| `dot` | 0 | 64 | Completed emulated dot at pause |
| `executed` | 8 | 32 | Actual ticks executed by this operation |
| `reason` | 12 | 8 | COUNT or STOPPED completion |

## Commands

| Name | Request payload | Successful response | Allowed state |
|---|---|---|---|
| `PING` | `empty` | `word` | any |
| `READ_HOST` | `read_host` | `word` | any |
| `RESET` | `empty` | `empty` | not loading; valid image |
| `RUN` | `empty` | `empty` | paused valid image |
| `HALT` | `empty` | `dot` | not loading |
| `STEP` | `word` | `dot` | paused valid image |
| `LOAD_BEGIN` | `load_begin` | `empty` | any |
| `LOAD_WRITE` | `offset+bytes` | `empty` | loading |
| `LOAD_END` | `empty` | `empty` | loading |
| `READ_ROM` | `read_range` | `bytes` | paused or loading |
| `INPUT` | `input` | `dot` | not loading |
| `SNAPSHOT` | `empty` | `snapshot` | not loading |
| `READ_FRAME` | `read_range` | `bytes` | snapshot valid |
| `WRITE_HOST` | `write_host` | `dot` | Not LOADING. |
| `RUN_DOTS` | `word` | `run_dots` | paused valid image |

## Provenance

- [Pan Docs](https://github.com/gbdev/pandocs/tree/fe246067b695b5404a4a6a47efb4fd6d921ececb), `fe246067b695b5404a4a6a47efb4fd6d921ececb`, CC0-1.0: Memory map, vectors, DMG register addresses, joypad matrix; research only, no imported code.
