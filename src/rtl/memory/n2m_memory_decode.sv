`timescale 1ns/1ps
`default_nettype none

// Address ownership only. Service, masks and commit effects belong downstream.
module n2m_memory_decode (
    input var logic [15:0] address,
    output n2m_memory_pkg::memory_destination_t destination,
    output n2m_memory_pkg::memory_store_t store,
    output logic [14:0] offset
);
    import n2m_interfaces_pkg::*;
    import n2m_memory_pkg::*;

    always_comb begin
        destination = MEMORY_UNUSED_IO;
        store = STORE_ROM;
        offset = 0;
        if (address <= GB_ROM1_END) begin
            destination = MEMORY_DIRECT;
            store = STORE_ROM;
            offset = address[14:0];
        end else if (address <= GB_VRAM_END) begin
            destination = MEMORY_VRAM;
            store = STORE_VRAM;
            offset = {2'b0, address[12:0]};
        end else if (address <= GB_CART_RAM_END) begin
            destination = MEMORY_ABSENT_CART;
        end else if (address <= GB_ECHO_END) begin
            // E000-FDFF selects the same C000-DDFF bytes in both directions.
            destination = MEMORY_DIRECT;
            store = STORE_WRAM;
            offset = {2'b0, address[12:0]};
        end else if (address <= GB_OAM_END) begin
            destination = MEMORY_OAM;
            store = STORE_OAM;
            offset = {7'b0, address[7:0]};
        end else if (address <= GB_UNUSABLE_END) begin
            destination = MEMORY_UNUSABLE;
        end else if (address >= GB_HRAM_START && address <= GB_HRAM_END) begin
            destination = MEMORY_DIRECT;
            store = STORE_HRAM;
            offset = {8'b0, address[6:0]};
        end else if (address >= GB_VIEW_WAVE_START && address <= GB_VIEW_WAVE_END) begin
            destination = MEMORY_WAVE;
            store = STORE_WAVE;
            offset = {11'b0, address[3:0]};
        end else begin
            case (address)
                GB_REG_JOYP: destination = MEMORY_JOYP;
                GB_REG_SB, GB_REG_SC: destination = MEMORY_SERIAL;
                GB_REG_DIV, GB_REG_TIMA, GB_REG_TMA, GB_REG_TAC: destination = MEMORY_TIMER;
                GB_REG_IF, GB_REG_IE: destination = MEMORY_IRQ;
                GB_REG_NR10, GB_REG_NR11, GB_REG_NR12, GB_REG_NR13, GB_REG_NR14,
                GB_REG_NR21, GB_REG_NR22, GB_REG_NR23, GB_REG_NR24,
                GB_REG_NR30, GB_REG_NR31, GB_REG_NR32, GB_REG_NR33, GB_REG_NR34,
                GB_REG_NR41, GB_REG_NR42, GB_REG_NR43, GB_REG_NR44,
                GB_REG_NR50, GB_REG_NR51, GB_REG_NR52: destination = MEMORY_APU;
                GB_REG_LCDC, GB_REG_STAT, GB_REG_SCY, GB_REG_SCX, GB_REG_LY, GB_REG_LYC,
                GB_REG_BGP, GB_REG_OBP0, GB_REG_OBP1, GB_REG_WY, GB_REG_WX: destination = MEMORY_PPU;
                GB_REG_DMA: destination = MEMORY_DMA;
                GB_REG_BOOT_DISABLE: destination = MEMORY_BOOT;
                default: begin end
            endcase
        end
    end
endmodule
