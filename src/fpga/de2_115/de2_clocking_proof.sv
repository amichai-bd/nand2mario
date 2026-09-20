`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Cyclone IV E clocking fit proof. Virtual control/observation ports make this a
// fit proof, not a board image; it mirrors the MAX 10 clocking_proof so both
// ALTPLL families prove the same clock contract from the same wrapper.
// ALTPLL serves this family, so u_clocking is the DE10-Lite's
// src/fpga/de10_lite/n2m_clocking.sv in place. Not a copy: the Questa gate
// compiles every registered source into one library and fails on the
// module-overwrite warning a same-named copy raises, and a renamed copy forks the
// fitted hierarchy every clocking check names (src/fpga/de2_115/README.md).
// Board pins: wiki/src/de2-115-board.md
module de2_clocking_proof (
    input logic clk_reference, board_reset_n, core_reset, pause_request,
    output logic ready, paused,
    output logic [7:0] sys_count, pix_count
);
    logic clk_sys;
    logic clk_pix, reset_sys, reset_pix, gb_tick;
    n2m_clocking u_clocking (.clk_reference, .clk_sys, .board_reset_n, .clk_pix, .reset_sys, .reset_pix, .ready);
    n2m_timebase u_tick (.clk_sys, .reset_sys, .core_reset, .pause_request, .gb_tick, .paused);
    logic [7:0] sys_count_next;
    always_comb begin
        sys_count_next = sys_count;
        if (gb_tick) sys_count_next = sys_count + 8'd1;
    end
    logic [7:0] pix_count_next;
    assign pix_count_next = pix_count + 8'd1;
    `DFF_ARST_VAL(sys_count, sys_count_next, clk_sys, reset_sys, 8'd0)
    `DFF_ARST_VAL(pix_count, pix_count_next, clk_pix, reset_pix, 8'd0)
endmodule
