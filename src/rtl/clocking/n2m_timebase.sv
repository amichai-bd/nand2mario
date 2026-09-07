`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Contract: wiki/src/clocks-resets-cdc.md (exact emulated time and run control).
module n2m_timebase (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic pause_request,
    output logic gb_tick,
    output logic paused
);
    logic [18:0] phase;
    logic [18:0] sum;
    assign sum = phase + 19'd65536;
    // Consumers sample this edge's carry, before the phase register advances.
    assign gb_tick = !reset_sys && !core_reset && !paused && (sum >= 19'd390625);

    logic [18:0] phase_next;
    logic paused_next;
    always_comb begin
        phase_next = phase;
        paused_next = paused;
        if (core_reset) begin
            phase_next = 19'd0;
            paused_next = 1'b1;
        end else if (paused) begin
            if (!pause_request) paused_next = 1'b0;
        end else if (sum >= 19'd390625) begin
            phase_next = sum - 19'd390625;
            if (pause_request) paused_next = 1'b1;
        end else begin
            phase_next = sum;
        end
    end
    `DFF_ARST_VAL(phase, phase_next, clk_sys, reset_sys, 19'd0)
    `DFF_ARST_VAL(paused, paused_next, clk_sys, reset_sys, 1'b1)

    `N2M_ASSERT(phase_in_range, clk_sys, reset_sys, phase < 19'd390625)
    `N2M_ASSERT_KNOWN(timebase_known, clk_sys, reset_sys, {phase, paused, gb_tick})
    `N2M_ASSERT_NEVER(no_tick_while_stopped, clk_sys, reset_sys, (core_reset || paused) && gb_tick)
    `N2M_ASSERT_STABLE_WHEN(paused_phase_holds, clk_sys, reset_sys, paused && !core_reset, phase)
endmodule
