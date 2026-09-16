`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// MBC1 profile owner. Contract: wiki/src/rtl/cartridge/MAS_mbc1_profile.md.
// Holds the BANK1, BANK2 and MODE registers from the resolved CPU ROM write
// commits and translates every store access offset: in MBC1_ID a switched
// window read lands in the effective bank of the 64 KiB store; in every other
// profile the translation is the identity, so the 32 KiB profiles are
// unchanged byte for byte. RAMG writes are accepted and ignored: there is no
// cartridge RAM. No CPU write ever reaches the store through this owner.
module n2m_mbc1 (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic [7:0] profile,
    // CPU commits resolved to the ROM store by the memory owner.
    input var logic rom_commit,
    input var logic [14:0] commit_offset,
    input var logic [7:0] commit_data,
    // Store access before translation, and the translated store offset.
    input var n2m_memory_pkg::memory_store_t access_store,
    input var logic [14:0] access_offset,
    output logic [15:0] store_offset
);
    localparam logic [7:0] MBC1_ID = n2m_interfaces_pkg::PROFILE_MBC1_ID;
    localparam integer BANK1_BITS = int'(n2m_interfaces_pkg::MBC1_BANK1_BITS);
    localparam integer BANK2_BITS = int'(n2m_interfaces_pkg::MBC1_BANK2_BITS);
    localparam logic [1:0] BANK_MASK = 2'(n2m_interfaces_pkg::MBC1_BANK_MASK);
    localparam logic [1:0] RESET_BANK = 2'(n2m_interfaces_pkg::MBC1_RESET_BANK);
    // Alias ranges tile $0000-$7FFF in 8 KiB steps; offset bits 14:13 select
    // the register (checked against the generated ranges below).
    localparam logic [1:0] RAMG_SELECT = 2'b00;
    localparam logic [1:0] BANK1_SELECT = 2'b01;
    localparam logic [1:0] BANK2_SELECT = 2'b10;
    localparam logic [1:0] MODE_SELECT = 2'b11;

    logic mbc1_active, reset;
    logic bank1_commit, bank2_commit, mode_commit;
    logic [BANK1_BITS-1:0] bank1, bank1_next;
    logic [BANK2_BITS-1:0] bank2, bank2_next;
    logic mode, mode_next;
    logic [1:0] effective_bank;
    logic switched_read;

    assign mbc1_active = profile == MBC1_ID;
    assign reset = reset_sys || core_reset;
    assign bank1_commit = rom_commit && mbc1_active && commit_offset[14:13] == BANK1_SELECT;
    assign bank2_commit = rom_commit && mbc1_active && commit_offset[14:13] == BANK2_SELECT;
    assign mode_commit = rom_commit && mbc1_active && commit_offset[14:13] == MODE_SELECT;
    assign bank1_next = bank1_commit ? commit_data[BANK1_BITS-1:0] : bank1;
    assign bank2_next = bank2_commit ? commit_data[BANK2_BITS-1:0] : bank2;
    assign mode_next = mode_commit ? commit_data[0] : mode;
    `DFF_ARST_VAL(bank1, bank1_next, clk_sys, reset, '0)
    `DFF_ARST_VAL(bank2, bank2_next, clk_sys, reset, '0)
    `DFF_ARST_VAL(mode, mode_next, clk_sys, reset, 1'b0)

    // Zero translation on the whole register, then the mask to four banks.
    // BANK2 and MODE hold state but reach no address bit of a 64 KiB image.
    assign effective_bank = (bank1 == '0 ? 2'(RESET_BANK) : bank1[1:0]) & BANK_MASK;
    // Offset bit 14 is set only for ROM store offsets: every other store is at
    // most 8 KiB, so the store selector is not needed here and stays out of
    // the address path (it is checked by MBC1_SWITCHED_IS_ROM below).
    assign switched_read = mbc1_active && access_offset[14];
    assign store_offset = switched_read ? {effective_bank, access_offset[13:0]} : {1'b0, access_offset};

    `N2M_ASSERT(MBC1_REGISTERS_ONLY_IN_PROFILE, clk_sys, reset_sys,
        (bank1_commit || bank2_commit || mode_commit) |-> profile == MBC1_ID)
    `N2M_ASSERT(MBC1_FIXED_WINDOW_BANK0, clk_sys, reset_sys,
        mbc1_active && access_store == n2m_memory_pkg::STORE_ROM && !access_offset[14] |-> store_offset[15:14] == 2'b00)
    `N2M_ASSERT(MBC1_EFFECTIVE_BANK_NONZERO_ALIAS, clk_sys, reset_sys,
        bank1 == '0 |-> effective_bank == RESET_BANK)
    `N2M_ASSERT(MBC1_SWITCHED_IS_ROM, clk_sys, reset_sys,
        access_offset[14] |-> access_store == n2m_memory_pkg::STORE_ROM)
    `N2M_ASSERT(MBC1_IDENTITY_OUTSIDE_PROFILE, clk_sys, reset_sys,
        !mbc1_active |-> store_offset == {1'b0, access_offset})
    // The generated alias ranges must match the 8 KiB select decode above
    // (constant property, checked on every edge in simulation, excluded from synthesis).
    `N2M_ASSERT_NO_RST(MBC1_ALIAS_DECODE, clk_sys,
        n2m_interfaces_pkg::MBC1_RAMG_START == 16'h0000 && n2m_interfaces_pkg::MBC1_BANK1_START == 16'h2000 &&
        n2m_interfaces_pkg::MBC1_BANK2_START == 16'h4000 && n2m_interfaces_pkg::MBC1_MODE_START == 16'h6000 &&
        n2m_interfaces_pkg::MBC1_MODE_END == 16'h7FFF)
endmodule
`default_nettype wire
