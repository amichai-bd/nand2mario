`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Raw storage, after behavior-owner arbitration. No DMG I/O masks live here.
module n2m_memory_stores (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    output logic init_done,
    input var logic access_read,
    input var logic access_write,
    input var n2m_memory_pkg::memory_store_t access_store,
    input var logic [14:0] access_address,
    input var logic [7:0] access_wdata,
    output logic [7:0] access_rdata,
    output logic access_valid,
    input var n2m_memory_pkg::memory_oam_request_t oam_request,
    output n2m_memory_pkg::memory_oam_response_t oam_response,
    input var logic host_read,
    input var logic host_write,
    input var logic [31:0] host_offset,
    input var logic [7:0] host_wdata,
    output logic [7:0] host_rdata,
    output logic host_valid,
    input var logic ppu_vram_read,
    input var logic [12:0] ppu_vram_address,
    output logic [7:0] ppu_vram_rdata,
    output logic ppu_vram_valid,
    input var logic ppu_oam_read,
    input var logic [6:0] ppu_oam_pair,
    output logic [15:0] ppu_oam_rdata,
    output logic ppu_oam_valid,
    input var logic wave_read,
    input var logic wave_write,
    input var logic [3:0] wave_address,
    input var logic [7:0] wave_wdata,
    output logic [7:0] wave_rdata,
    output logic wave_valid
);
    // Quartus 25.1 misresolves package constants in instance connections and assignment indices.
    localparam n2m_memory_pkg::memory_store_t ROM_STORE = n2m_memory_pkg::STORE_ROM;
    localparam n2m_memory_pkg::memory_store_t WRAM_STORE = n2m_memory_pkg::STORE_WRAM;
    localparam n2m_memory_pkg::memory_store_t HRAM_STORE = n2m_memory_pkg::STORE_HRAM;
    localparam n2m_memory_pkg::memory_store_t VRAM_STORE = n2m_memory_pkg::STORE_VRAM;
    localparam n2m_memory_pkg::memory_store_t OAM_STORE = n2m_memory_pkg::STORE_OAM;
    localparam n2m_memory_pkg::memory_store_t WAVE_STORE = n2m_memory_pkg::STORE_WAVE;
    localparam integer WRAM_BYTES = int'(n2m_interfaces_pkg::GB_WRAM_END) - int'(n2m_interfaces_pkg::GB_WRAM_START) + 1;
    localparam integer VRAM_BYTES = int'(n2m_interfaces_pkg::GB_VRAM_END) - int'(n2m_interfaces_pkg::GB_VRAM_START) + 1;
    localparam integer HRAM_BYTES = int'(n2m_interfaces_pkg::GB_HRAM_END) - int'(n2m_interfaces_pkg::GB_HRAM_START) + 1;
    localparam integer OAM_BYTES = int'(n2m_interfaces_pkg::GB_OAM_END) - int'(n2m_interfaces_pkg::GB_OAM_START) + 1;
    localparam integer WAVE_BYTES = int'(n2m_interfaces_pkg::GB_VIEW_WAVE_END) - int'(n2m_interfaces_pkg::GB_VIEW_WAVE_START) + 1;
    logic reset, clearing, clearing_next;
    logic [12:0] clear_address, clear_next;
    logic [14:0] ram_address;
    logic [7:0] ram_wdata;
    logic access_range, access_read_enable, access_write_enable, host_range;
    n2m_memory_pkg::memory_store_t response_store;
    logic [5:0][7:0] data_a;
    logic [5:0] valid_a;
    logic [7:0] oam_even, oam_odd, oam_a_even, oam_a_odd;
    logic oam_even_valid, oam_odd_valid, oam_a_valid;
    logic response_odd;
    logic response_valid;
    logic pair_active, pair_read, pair_valid;
    logic [6:0] oam_address;
    logic [15:0] oam_wdata;
    logic [1:0] oam_write;
    logic [7:0] rom_a_data;
    logic rom_a_valid;
    logic [7:0] unused_b_wram, unused_b_hram;
    logic unused_b_wram_valid, unused_b_hram_valid;
    logic wave_gateway_write;

    assign reset = reset_sys || core_reset;
    assign init_done = !reset && !clearing;
    // The APU gateway owns CPU wave access; clearing still dominates its write.
    assign wave_gateway_write = wave_write && init_done;
    always_comb begin
        clearing_next = clearing;
        clear_next = clear_address;
        if (clearing) begin
            if (int'(clear_address) == WRAM_BYTES - 1) clearing_next = 0;
            else clear_next = clear_address + 13'd1;
        end
        if (core_reset) begin
            clearing_next = 1;
            clear_next = 0;
        end
    end
    `DFF_ARST_VAL(clearing, clearing_next, clk_sys, reset_sys, 1'b1)
    `DFF_ARST_VAL(clear_address, clear_next, clk_sys, reset_sys, 13'd0)
    assign ram_address = clearing ? {2'b0, clear_address} : access_address;
    assign ram_wdata = clearing ? n2m_interfaces_pkg::PROFILE_RAM_FILL : access_wdata;
    always_comb begin
        access_range = 0;
        case (access_store)
            n2m_memory_pkg::STORE_ROM: access_range = int'(access_address) < int'(n2m_interfaces_pkg::PROFILE_ROM_BYTES);
            n2m_memory_pkg::STORE_WRAM: access_range = int'(access_address) < WRAM_BYTES;
            n2m_memory_pkg::STORE_HRAM: access_range = int'(access_address) < HRAM_BYTES;
            n2m_memory_pkg::STORE_VRAM: access_range = int'(access_address) < VRAM_BYTES;
            n2m_memory_pkg::STORE_OAM: access_range = int'(access_address) < OAM_BYTES;
            n2m_memory_pkg::STORE_WAVE: access_range = int'(access_address) < WAVE_BYTES;
            default: begin end
        endcase
    end
    assign access_read_enable = access_read && init_done && access_range;
    assign access_write_enable = access_write && init_done && access_range;
    assign host_range = host_offset < 32'(n2m_interfaces_pkg::PROFILE_ROM_BYTES);
    `DFF_EN(response_store, access_store, clk_sys, access_read_enable)
    `DFF_EN(response_odd, access_address[0], clk_sys, access_read_enable)
    `DFF_ARST_VAL(response_valid, access_read_enable, clk_sys, reset, 1'b0)
    assign access_rdata = data_a[response_store];
    assign access_valid = init_done && response_valid;
    assign pair_active = oam_request.read || |oam_request.write_enable;
    assign pair_read = init_done && oam_request.read && oam_request.pair < 7'd80;
    assign oam_address = pair_active && init_done ? oam_request.pair : ram_address[7:1];
    assign oam_wdata = pair_active && init_done ? oam_request.data : {2{ram_wdata}};
    assign oam_write[0] = (clearing && int'(clear_address) < OAM_BYTES && !clear_address[0]) ||
        (init_done && pair_active && oam_request.pair < 7'd80 && oam_request.write_enable[0]) ||
        (access_write_enable && access_store == n2m_memory_pkg::STORE_OAM && !access_address[0]);
    assign oam_write[1] = (clearing && int'(clear_address) < OAM_BYTES && clear_address[0]) ||
        (init_done && pair_active && oam_request.pair < 7'd80 && oam_request.write_enable[1]) ||
        (access_write_enable && access_store == n2m_memory_pkg::STORE_OAM && access_address[0]);
    `DFF_ARST_VAL(pair_valid, pair_read, clk_sys, reset, 1'b0)
    assign oam_response.valid = init_done && pair_valid;
    assign oam_response.data = {oam_a_odd, oam_a_even};

    // ROM writes exist only on the explicit host offset port. CPU/arbitrator
    // write attempts selecting ROM are ignored and cannot reach that port.
    n2m_intel_ram #(.DEPTH(n2m_interfaces_pkg::PROFILE_ROM_BYTES), .ADDRESS_BITS(15)) rom (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset), .reset_b(reset), .a_byte_enable(1'b1), .a_read(host_read && host_range), .a_write(host_write && host_range),
        .a_address(host_offset[14:0]), .a_wdata(host_wdata), .a_rdata(rom_a_data), .a_valid(rom_a_valid),
        .b_read(access_read_enable && access_store == ROM_STORE), .b_address(access_address),
        .b_rdata(data_a[ROM_STORE]), .b_valid(valid_a[ROM_STORE])
    );
    assign host_rdata = rom_a_data;
    assign host_valid = rom_a_valid && !reset;
    n2m_intel_ram #(.DEPTH(WRAM_BYTES), .ADDRESS_BITS(13)) wram (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset), .reset_b(reset), .a_byte_enable(1'b1), .a_read(access_read_enable && access_store == WRAM_STORE),
        .a_write(clearing || (access_write_enable && access_store == WRAM_STORE)),
        .a_address(ram_address[12:0]), .a_wdata(ram_wdata), .a_rdata(data_a[WRAM_STORE]), .a_valid(valid_a[WRAM_STORE]),
        .b_read(1'b0), .b_address(13'd0), .b_rdata(unused_b_wram), .b_valid(unused_b_wram_valid)
    );
    n2m_intel_ram #(.DEPTH(HRAM_BYTES), .ADDRESS_BITS(7)) hram (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset), .reset_b(reset), .a_byte_enable(1'b1), .a_read(access_read_enable && access_store == HRAM_STORE),
        .a_write((clearing && int'(clear_address) < HRAM_BYTES) || (access_write_enable && access_store == HRAM_STORE)),
        .a_address(ram_address[6:0]), .a_wdata(ram_wdata), .a_rdata(data_a[HRAM_STORE]), .a_valid(valid_a[HRAM_STORE]),
        .b_read(1'b0), .b_address(7'd0), .b_rdata(unused_b_hram), .b_valid(unused_b_hram_valid)
    );
    n2m_intel_ram #(.DEPTH(VRAM_BYTES), .ADDRESS_BITS(13)) vram (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset), .reset_b(reset), .a_byte_enable(1'b1), .a_read(access_read_enable && access_store == VRAM_STORE),
        .a_write(clearing || (access_write_enable && access_store == VRAM_STORE)),
        .a_address(ram_address[12:0]), .a_wdata(ram_wdata), .a_rdata(data_a[VRAM_STORE]), .a_valid(valid_a[VRAM_STORE]),
        .b_read(ppu_vram_read && init_done), .b_address(ppu_vram_address),
        .b_rdata(ppu_vram_rdata), .b_valid(ppu_vram_valid)
    );
    n2m_intel_ram #(.DEPTH(OAM_BYTES/2), .ADDRESS_BITS(7)) oam_low (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset), .reset_b(reset), .a_byte_enable(1'b1), .a_read(pair_read || (access_read_enable && access_store == OAM_STORE)),
        .a_write(oam_write[0]),
        .a_address(oam_address), .a_wdata(oam_wdata[7:0]), .a_rdata(oam_a_even), .a_valid(oam_a_valid),
        .b_read(ppu_oam_read && init_done), .b_address(ppu_oam_pair), .b_rdata(oam_even), .b_valid(oam_even_valid)
    );
    n2m_intel_ram #(.DEPTH(OAM_BYTES/2), .ADDRESS_BITS(7)) oam_high (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset), .reset_b(reset), .a_byte_enable(1'b1), .a_read(pair_read || (access_read_enable && access_store == OAM_STORE)),
        .a_write(oam_write[1]),
        .a_address(oam_address), .a_wdata(oam_wdata[15:8]), .a_rdata(oam_a_odd), .a_valid(valid_a[OAM_STORE]),
        .b_read(ppu_oam_read && init_done), .b_address(ppu_oam_pair), .b_rdata(oam_odd), .b_valid(oam_odd_valid)
    );
    assign data_a[OAM_STORE] = response_odd ? oam_a_odd : oam_a_even;
    assign ppu_oam_rdata = {oam_odd, oam_even};
    assign ppu_oam_valid = oam_even_valid && oam_odd_valid;
    n2m_intel_ram #(.DEPTH(WAVE_BYTES), .ADDRESS_BITS(4)) wave_ram (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset), .reset_b(reset), .a_byte_enable(1'b1), .a_read(access_read_enable && access_store == WAVE_STORE),
        .a_write((clearing && int'(clear_address) < WAVE_BYTES) || (access_write_enable && access_store == WAVE_STORE) || wave_gateway_write),
        .a_address(wave_gateway_write ? wave_address : ram_address[3:0]),
        .a_wdata(wave_gateway_write ? wave_wdata : ram_wdata), .a_rdata(data_a[WAVE_STORE]), .a_valid(valid_a[WAVE_STORE]),
        .b_read(wave_read && init_done), .b_address(wave_address), .b_rdata(wave_rdata), .b_valid(wave_valid)
    );
    `N2M_ASSERT(MEMORY_ACCESS_RANGE, clk_sys, reset,
        !(access_read || access_write) || access_range)
    `N2M_ASSERT(MEMORY_OAM_SINGLE_OWNER, clk_sys, reset,
        !pair_active || !((access_read || access_write) && access_store == n2m_memory_pkg::STORE_OAM))
    `N2M_ASSERT(MEMORY_OAM_PAIR_REQUEST, clk_sys, reset,
        !pair_active || (init_done && oam_request.pair < 7'd80 &&
        !(oam_request.read && |oam_request.write_enable)))
    `N2M_ASSERT(MEMORY_HOST_RANGE, clk_sys, reset,
        !(host_read || host_write) || host_range)
    `N2M_ASSERT(MEMORY_NO_ACCESS_DURING_CLEAR, clk_sys, reset,
        !clearing || !(access_read || access_write || ppu_vram_read || ppu_oam_read || wave_read || wave_write))
    `N2M_ASSERT(MEMORY_WAVE_SINGLE_WRITER, clk_sys, reset,
        !wave_gateway_write || !(access_write_enable && access_store == n2m_memory_pkg::STORE_WAVE))
    `N2M_ASSERT(MEMORY_OAM_PAIR_VALID, clk_sys, reset,
        oam_even_valid == oam_odd_valid && oam_a_valid == valid_a[n2m_memory_pkg::STORE_OAM])
    `N2M_ASSERT(MEMORY_RESPONSE_OWNER_VALID, clk_sys, reset,
        response_valid |-> valid_a[response_store])
endmodule
