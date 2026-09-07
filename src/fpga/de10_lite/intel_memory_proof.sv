`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Virtual request/observation ports retain all four RAM configurations for fit.
// This is a resource/timing proof, not a physical board acceptance image.
module intel_memory_proof (
    input var logic clk_reference,
    input var logic board_reset_n,
    input var logic a_read,
    input var logic a_write,
    input var logic [14:0] a_address,
    input var logic [31:0] a_wdata,
    input var logic [3:0] a_byte_enable,
    input var logic b_read,
    input var logic [7:0] b_address,
    output logic ready,
    output logic [7:0] byte_a,
    output logic [7:0] byte_b,
    output logic [15:0] pair_a,
    output logic [15:0] pair_b,
    output logic [31:0] lanes_a,
    output logic [31:0] lanes_b,
    output logic [1:0] frame_a,
    output logic [1:0] frame_b,
    output logic [3:0] a_valid,
    output logic [2:0] b_valid,
    output logic frame_valid
);
    logic clk_sys;
    logic clk_pix, reset_sys, reset_pix;
    logic frame_read;
    logic [14:0] frame_address, frame_next_address;
    n2m_clocking u_clocking (.clk_reference, .clk_sys, .board_reset_n, .clk_pix, .reset_sys, .reset_pix, .ready);
    // A real pixel-domain owner launches requests on the same clock tree as B.
    // This producer is outside the wrapper and adds no wrapper service stage.
    assign frame_next_address = frame_address == 15'd23039 ? 15'd0 : frame_address + 15'd1;
    `DFF_RST(frame_read, !frame_read, clk_pix, reset_pix)
    `DFF_RST_EN(frame_address, frame_next_address, clk_pix, frame_read, reset_pix, 15'd0)
    `N2M_ASSERT_KNOWN(INTEL_PROOF_REQUEST_KNOWN, clk_pix, reset_pix, {frame_read, frame_address})
    `N2M_ASSERT(INTEL_PROOF_ADDRESS_RANGE, clk_pix, reset_pix, frame_address < 15'd23040)
    n2m_intel_ram #(.DEPTH(160), .DATA_BITS(8), .ADDRESS_BITS(8)) byte_ram (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset_sys), .reset_b(reset_sys),
        .a_read, .a_write, .a_address(a_address[7:0]), .a_wdata(a_wdata[7:0]),
        .a_byte_enable(a_byte_enable[0]), .a_rdata(byte_a), .a_valid(a_valid[0]),
        .b_read, .b_address, .b_rdata(byte_b), .b_valid(b_valid[0])
    );
    n2m_intel_ram #(.DEPTH(80), .DATA_BITS(16), .ADDRESS_BITS(7)) pair_ram (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset_sys), .reset_b(reset_sys),
        .a_read, .a_write, .a_address(a_address[6:0]), .a_wdata(a_wdata[15:0]),
        .a_byte_enable(a_byte_enable[0]), .a_rdata(pair_a), .a_valid(a_valid[1]),
        .b_read, .b_address(b_address[6:0]), .b_rdata(pair_b), .b_valid(b_valid[1])
    );
    n2m_intel_ram #(.DEPTH(64), .DATA_BITS(32), .ADDRESS_BITS(6), .BYTE_LANES(4)) lanes_ram (
        .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset_sys), .reset_b(reset_sys),
        .a_read, .a_write, .a_address(a_address[5:0]), .a_wdata,
        .a_byte_enable, .a_rdata(lanes_a), .a_valid(a_valid[2]),
        .b_read, .b_address(b_address[5:0]), .b_rdata(lanes_b), .b_valid(b_valid[2])
    );
    n2m_intel_ram #(.DEPTH(23040), .DATA_BITS(2), .ADDRESS_BITS(15), .DUAL_CLOCK(1)) frame_ram (
        .clk_a(clk_sys), .clk_b(clk_pix), .reset_a(reset_sys), .reset_b(reset_pix),
        .a_read, .a_write, .a_address, .a_wdata(a_wdata[1:0]),
        .a_byte_enable(a_byte_enable[0]), .a_rdata(frame_a), .a_valid(a_valid[3]),
        .b_read(frame_read), .b_address(frame_address), .b_rdata(frame_b), .b_valid(frame_valid)
    );
endmodule
