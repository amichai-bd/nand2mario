`timescale 1ns/1ps
`default_nettype none

// Address ownership only. Service, masks and commit effects belong downstream.
module n2m_memory_decode (
    input var logic [15:0] address,
    output n2m_memory_pkg::memory_destination_t destination,
    output n2m_memory_pkg::memory_store_t store,
    output logic [14:0] offset
);

    always_comb begin
        destination = n2m_memory_pkg::MEMORY_UNUSED_IO;
        store = n2m_memory_pkg::STORE_ROM;
        offset = 0;
        if (address <= n2m_interfaces_pkg::GB_ROM1_END) begin
            destination = n2m_memory_pkg::MEMORY_DIRECT;
            store = n2m_memory_pkg::STORE_ROM;
            offset = address[14:0];
        end else if (address <= n2m_interfaces_pkg::GB_VRAM_END) begin
            destination = n2m_memory_pkg::MEMORY_VRAM;
            store = n2m_memory_pkg::STORE_VRAM;
            offset = {2'b0, address[12:0]};
        end else if (address <= n2m_interfaces_pkg::GB_CART_RAM_END) begin
            destination = n2m_memory_pkg::MEMORY_ABSENT_CART;
        end else if (address <= n2m_interfaces_pkg::GB_ECHO_END) begin
            // E000-FDFF selects the same C000-DDFF bytes in both directions.
            destination = n2m_memory_pkg::MEMORY_DIRECT;
            store = n2m_memory_pkg::STORE_WRAM;
            offset = {2'b0, address[12:0]};
        end else if (address <= n2m_interfaces_pkg::GB_OAM_END) begin
            destination = n2m_memory_pkg::MEMORY_OAM;
            store = n2m_memory_pkg::STORE_OAM;
            offset = {7'b0, address[7:0]};
        end else if (address <= n2m_interfaces_pkg::GB_UNUSABLE_END) begin
            destination = n2m_memory_pkg::MEMORY_UNUSABLE;
        end else if (address >= n2m_interfaces_pkg::GB_HRAM_START && address <= n2m_interfaces_pkg::GB_HRAM_END) begin
            destination = n2m_memory_pkg::MEMORY_DIRECT;
            store = n2m_memory_pkg::STORE_HRAM;
            offset = {8'b0, address[6:0]};
        end else if (address >= n2m_interfaces_pkg::GB_VIEW_WAVE_START && address <= n2m_interfaces_pkg::GB_VIEW_WAVE_END) begin
            destination = n2m_memory_pkg::MEMORY_WAVE;
            store = n2m_memory_pkg::STORE_WAVE;
            offset = {11'b0, address[3:0]};
        end else begin
            case (address)
                n2m_interfaces_pkg::GB_REG_JOYP: destination = n2m_memory_pkg::MEMORY_JOYP;
                n2m_interfaces_pkg::GB_REG_SB, n2m_interfaces_pkg::GB_REG_SC: destination = n2m_memory_pkg::MEMORY_SERIAL;
                n2m_interfaces_pkg::GB_REG_DIV, n2m_interfaces_pkg::GB_REG_TIMA, n2m_interfaces_pkg::GB_REG_TMA, n2m_interfaces_pkg::GB_REG_TAC: destination = n2m_memory_pkg::MEMORY_TIMER;
                n2m_interfaces_pkg::GB_REG_IF, n2m_interfaces_pkg::GB_REG_IE: destination = n2m_memory_pkg::MEMORY_IRQ;
                n2m_interfaces_pkg::GB_REG_NR10, n2m_interfaces_pkg::GB_REG_NR11, n2m_interfaces_pkg::GB_REG_NR12, n2m_interfaces_pkg::GB_REG_NR13, n2m_interfaces_pkg::GB_REG_NR14,
                n2m_interfaces_pkg::GB_REG_NR21, n2m_interfaces_pkg::GB_REG_NR22, n2m_interfaces_pkg::GB_REG_NR23, n2m_interfaces_pkg::GB_REG_NR24,
                n2m_interfaces_pkg::GB_REG_NR30, n2m_interfaces_pkg::GB_REG_NR31, n2m_interfaces_pkg::GB_REG_NR32, n2m_interfaces_pkg::GB_REG_NR33, n2m_interfaces_pkg::GB_REG_NR34,
                n2m_interfaces_pkg::GB_REG_NR41, n2m_interfaces_pkg::GB_REG_NR42, n2m_interfaces_pkg::GB_REG_NR43, n2m_interfaces_pkg::GB_REG_NR44,
                n2m_interfaces_pkg::GB_REG_NR50, n2m_interfaces_pkg::GB_REG_NR51, n2m_interfaces_pkg::GB_REG_NR52: destination = n2m_memory_pkg::MEMORY_APU;
                n2m_interfaces_pkg::GB_REG_LCDC, n2m_interfaces_pkg::GB_REG_STAT, n2m_interfaces_pkg::GB_REG_SCY, n2m_interfaces_pkg::GB_REG_SCX, n2m_interfaces_pkg::GB_REG_LY, n2m_interfaces_pkg::GB_REG_LYC,
                n2m_interfaces_pkg::GB_REG_BGP, n2m_interfaces_pkg::GB_REG_OBP0, n2m_interfaces_pkg::GB_REG_OBP1, n2m_interfaces_pkg::GB_REG_WY, n2m_interfaces_pkg::GB_REG_WX: destination = n2m_memory_pkg::MEMORY_PPU;
                n2m_interfaces_pkg::GB_REG_DMA: destination = n2m_memory_pkg::MEMORY_DMA;
                n2m_interfaces_pkg::GB_REG_BOOT_DISABLE: destination = n2m_memory_pkg::MEMORY_BOOT;
                default: begin end
            endcase
        end
    end
endmodule
