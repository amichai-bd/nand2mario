`timescale 1ns/1ps
// Cyclone V clocking wrapper. The two Altera PLL instances are generated beneath
// the build tag; this file presents the same interface to n2m_reset_control as
// the MAX 10 wrapper (src/fpga/de10_lite/n2m_clocking.sv) does.
// Board pins: wiki/src/de10-nano-board.md
module n2m_clocking_cyclonev (
    input  logic clk_reference,
    input  logic board_reset_n,
    output logic  clk_sys,
    output logic  clk_pix,
    output logic  reset_sys,
    output logic  reset_pix,
    output logic  ready
);
    logic pll_areset;
    logic pll_locked;
    logic system_locked;
    logic pixel_locked;
    // The Altera PLL IP names the reference refclk and the active-high reset
    // rst, where ALTPLL names them inclk0 and areset. Polarity is the same.
    n2m_system_pll_cyclonev u_system_pll (.refclk(clk_reference), .rst(pll_areset),
                                          .outclk_0(clk_sys), .locked(system_locked));
    assign pll_locked = system_locked && pixel_locked;
    n2m_pixel_pll_cyclonev u_pll (.refclk(clk_reference), .rst(pll_areset),
                                  .outclk_0(clk_pix), .locked(pixel_locked));
    n2m_reset_control u_reset (.clk_reference, .clk_sys, .clk_pix, .board_reset_n, .pll_locked,
                              .pll_areset, .ready, .reset_sys, .reset_pix);
endmodule
