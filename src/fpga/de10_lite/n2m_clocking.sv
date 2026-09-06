`timescale 1ns/1ps
// Vendor wrapper. n2m_pixel_pll is generated beneath the build tag by Quartus.
module n2m_clocking (
    input  logic clk_sys,
    input  logic board_reset_n,
    output logic  clk_pix,
    output logic  reset_sys,
    output logic  reset_pix,
    output logic  ready
);
    logic pll_areset;
    logic pll_locked;
    n2m_pixel_pll u_pll (.inclk0(clk_sys), .areset(pll_areset),
                        .c0(clk_pix), .locked(pll_locked));
    n2m_reset_control u_reset (.clk_sys, .clk_pix, .board_reset_n, .pll_locked,
                              .pll_areset, .ready, .reset_sys, .reset_pix);
endmodule
