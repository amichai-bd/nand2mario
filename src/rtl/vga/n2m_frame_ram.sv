`timescale 1ns/1ps
`default_nettype none
// Contract: wiki/src/rtl/vga/MAS_vga.md. Ownership excludes port collisions.
module n2m_frame_ram (
    input var logic clk_sys, write_enable,
    input var logic [14:0] write_address,
    input var logic [1:0] write_shade,
    input var logic clk_pix, read_enable,
    input var logic [14:0] read_address,
    output logic [1:0] read_shade
);
    logic [1:0] unused_a_data;
    logic unused_a_valid, unused_b_valid;
    // Owner gating masks startup contents and excludes cross-bank collisions.
    // The Intel input/address stage preserves the single enabled read edge.
    n2m_intel_ram #(
        .DEPTH(23040), .DATA_BITS(2), .ADDRESS_BITS(15),
        .BYTE_LANES(1), .DUAL_CLOCK(1)
    ) u_storage (
        .clk_a(clk_sys), .clk_b(clk_pix), .reset_a(1'b0), .reset_b(1'b0),
        .a_read(1'b0), .a_write(write_enable),
        .a_address(write_enable ? write_address : 15'd0),
        .a_wdata(write_shade), .a_byte_enable(1'b1),
        .a_rdata(unused_a_data), .a_valid(unused_a_valid),
        .b_read(read_enable), .b_address(read_enable ? read_address : 15'd0),
        .b_rdata(read_shade), .b_valid(unused_b_valid)
    );
endmodule
