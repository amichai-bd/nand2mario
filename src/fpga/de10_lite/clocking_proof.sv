`timescale 1ns/1ps
// Virtual control/observation ports make this a fit proof, not a board image.
module clocking_proof (
    input logic clk_sys, board_reset_n, core_reset, pause_request,
    output logic ready, paused,
    output logic [7:0] sys_count, pix_count
);
    wire clk_pix, reset_sys, reset_pix, gb_tick;
    n2m_clocking u_clocking (.clk_sys, .board_reset_n, .clk_pix, .reset_sys, .reset_pix, .ready);
    n2m_timebase u_tick (.clk_sys, .reset_sys, .core_reset, .pause_request, .gb_tick, .paused);
    // Specialized async consumers exercise recovery/removal after each reset bridge.
    always_ff @(posedge clk_sys or posedge reset_sys) begin
        if (reset_sys) sys_count <= 0;
        else if (gb_tick) sys_count <= sys_count + 8'd1;
    end
    always_ff @(posedge clk_pix or posedge reset_pix) begin
        if (reset_pix) pix_count <= 0;
        else pix_count <= pix_count + 8'd1;
    end
endmodule
