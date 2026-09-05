`timescale 1ns/1ps
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
    // Specialized memory inference blocks; no reset or initialization of RAM.
    always_ff @(posedge clk_sys)
        if (write_enable) pixels[write_address] <= write_shade;
    always_ff @(posedge clk_pix)
        if (read_enable) read_shade <= pixels[read_address];
endmodule
