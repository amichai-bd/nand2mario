/* Original direct-entry glue for the pinned SameBoy Core. */
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "Core/gb.h"
#include "Core/memory.h"
#include "Core/display.h"
#include "n2m_profile.h"

/* Fresh GB_init only: Core zeros saved and unsaved state before installing
 * model bookkeeping. The caller first verifies exact original file length/hash;
 * GB_load_rom rounds and pads files and cannot enforce that precondition.
 * Do not reuse this initializer as a warm reset. */
bool n2m_direct_profile(GB_gameboy_t *gb, const char *rom)
{
    GB_init(gb, GB_MODEL_DMG_B);
    if (GB_load_rom(gb, rom)) return false;
    if (gb->rom_size != 32768 || gb->mbc_ram_size || gb->rom[0x147] != 0)
        return false;
    gb->boot_rom_finished = !PROFILE_BOOT_MAPPED;
    gb->pc = PROFILE_PC; gb->sp = PROFILE_SP;
    gb->af = (PROFILE_A << 8) | PROFILE_F;
    gb->bc = (PROFILE_B << 8) | PROFILE_C;
    gb->de = (PROFILE_D << 8) | PROFILE_E;
    gb->hl = (PROFILE_H << 8) | PROFILE_L;
    gb->ime = PROFILE_IME; gb->ime_toggle = PROFILE_IME_DELAY;
    gb->halted = PROFILE_CPU_HALT; gb->stopped = PROFILE_CPU_STOP;
    gb->halt_bug = PROFILE_HALT_BUG;
    gb->pending_cycles = 0;
    memset(gb->ram, PROFILE_RAM_FILL, gb->ram_size);
    memset(gb->vram, PROFILE_RAM_FILL, gb->vram_size);
    memset(gb->hram, PROFILE_RAM_FILL, sizeof(gb->hram));
    memset(gb->oam, PROFILE_RAM_FILL, sizeof(gb->oam));
    memset(gb->io_registers, PROFILE_PERIPHERAL_FILL, sizeof(gb->io_registers));
    /* Core stores JOYP's released lines and SC's read-only bits in the byte.
     * Other I/O read masks are supplied by Core/memory.c. */
    gb->io_registers[GB_IO_JOYP] = 0xCF | PROFILE_JOYP_SELECT;
    gb->io_registers[GB_IO_SC] = 0x7E;
    GB_set_internal_div_counter(gb, 0);
    /* Keep Core's semantic idle encodings: DMA dest A1, no OAM row FF,
     * serial first-bit mask80 and APU 2MHz-unit flag. They are not activity. */
    gb->interrupt_enable = PROFILE_PERIPHERAL_FILL;
    GB_lcd_off(gb);
    /* Reset coincidence/IRQ history stays zero while LCD is off (MAS_ppu).
     * Calling GB_STAT_update cannot force a comparison while disabled. */
    gb->io_registers[GB_IO_STAT] = PROFILE_PERIPHERAL_FILL;
    gb->stat_interrupt_line = false;
    gb->lyc_interrupt_line = false;
    return true;
}
