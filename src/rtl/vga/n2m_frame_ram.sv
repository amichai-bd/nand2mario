`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Contract: wiki/src/rtl/vga/MAS_vga.md. Ownership excludes port collisions.
module n2m_frame_ram (
    input logic clk_sys, write_enable,
    input logic [14:0] write_address,
    input logic [1:0] write_shade,
    input logic clk_pix, read_enable,
    input logic [14:0] read_address,
    output logic [1:0] read_shade
);
    (* ramstyle = "M9K, no_rw_check" *) logic [1:0] pixels [0:23039];
    // No reset or initialization: these enabled ports infer dual-clock M9K RAM.
    `DFF_EN(pixels[write_address], write_shade, clk_sys, write_enable)
    `DFF_EN(read_shade, pixels[read_address], clk_pix, read_enable)
endmodule
