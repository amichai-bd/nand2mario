`timescale 1ns/1ps
`default_nettype none

// Composed placement proof with real board-reference PLLs and qualified resets,
// the DE10-Lite SDRAM behind the loader profile's storage arbiter and KEY1 as
// the return-to-menu button (wiki/src/rtl/cartridge/MAS_loader_profile.md).
module v05_proof #(
`ifdef N2M_V05_BUILD_ID
    parameter logic [127:0] BUILD_ID = `N2M_V05_BUILD_ID
`else
    parameter logic [127:0] BUILD_ID = 128'h88000000000000000000000000000001
`endif
) (
    input var logic clk_reference,
    input var logic board_reset_n,
    input var logic key1_n,
    input var logic uart_rx,
    output logic uart_tx,
    output logic [3:0] red, green, blue,
    output logic hsync_n, vsync_n,
    output logic [63:0] display_sequence,
    output logic [31:0] display_epoch,
    output logic paused, fault,
    output logic [12:0] DRAM_ADDR,
    output logic [1:0] DRAM_BA,
    output logic DRAM_CAS_N,
    output logic DRAM_CKE,
    output logic DRAM_CLK,
    output logic DRAM_CS_N,
    inout tri [15:0] DRAM_DQ,
    output logic DRAM_DQML,
    output logic DRAM_DQMH,
    output logic DRAM_RAS_N,
    output logic DRAM_WE_N
);
    logic clk_sys;
    logic clk_pix;
    logic reset_sys;
    logic reset_pix;
    logic sdram_initialized;
    logic sdram_request_valid;
    logic sdram_request_write;
    logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] sdram_request_address;
    logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] sdram_request_data;
    logic sdram_request_ready;
    logic sdram_response_valid;
    logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] sdram_response_data;
    n2m_clocking u_clocking (
        .clk_reference, .board_reset_n, .clk_sys, .clk_pix,
        .reset_sys, .reset_pix, .ready()
    );
    // The DE10-Lite image draws the handheld shell bezel; the RTL default is none.
    n2m_v05_system #(.BUILD_ID(BUILD_ID), .SHELL_BEZEL(1'b1)) u_system (
        .clk_sys, .clk_pix, .reset_sys, .reset_pix, .uart_rx, .uart_tx,
        .physical_commit(1'b0), .physical_buttons(8'd0),
        .effective_buttons(), .input_source_observe(),
        .red, .green, .blue, .hsync_n, .vsync_n, .paused, .fault,
        .display_sequence, .display_epoch,
        .gb_tick(), .core_reset(), .epoch(), .dot_count(),
        .retirement_valid(), .retirement(), .bus_commit(), .write_enable(),
        .address(), .write_data(), .read_data(), .irq_ack(),
        .source_valid(), .source_start(), .source_abort(),
        .source_display_eligible(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot(),
        .key1_n, .sdram_initialized, .sdram_request_valid, .sdram_request_write,
        .sdram_request_address, .sdram_request_data, .sdram_request_ready,
        .sdram_response_valid, .sdram_response_data
    );
    n2m_sdram_ctrl u_sdram (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .request_valid(sdram_request_valid), .request_write(sdram_request_write),
        .request_address(sdram_request_address), .request_data(sdram_request_data),
        .request_ready(sdram_request_ready), .response_valid(sdram_response_valid),
        .response_data(sdram_response_data), .idle(), .initialized(sdram_initialized),
        .DRAM_ADDR(DRAM_ADDR), .DRAM_BA(DRAM_BA), .DRAM_CAS_N(DRAM_CAS_N), .DRAM_CKE(DRAM_CKE),
        .DRAM_CLK(DRAM_CLK), .DRAM_CS_N(DRAM_CS_N), .DRAM_DQ(DRAM_DQ), .DRAM_DQML(DRAM_DQML),
        .DRAM_DQMH(DRAM_DQMH), .DRAM_RAS_N(DRAM_RAS_N), .DRAM_WE_N(DRAM_WE_N)
    );
endmodule
