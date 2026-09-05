`timescale 1ns/1ps
// Contract: wiki/src/clocks-resets-cdc.md (exact emulated time and run control).
module n2m_timebase (
    input  logic clk_sys,
    input  logic reset_sys,
    input  logic core_reset,
    input  logic pause_request,
    output logic gb_tick,
    output logic paused
);
    logic [18:0] phase;
    logic [18:0] sum;
    assign sum = phase + 19'd32768;
    // Consumers sample this edge's carry, before the phase register advances.
    assign gb_tick = !reset_sys && !core_reset && !paused && (sum >= 19'd390625);

    always_ff @(posedge clk_sys or posedge reset_sys) begin
        if (reset_sys) begin
            phase <= 19'd0;
            paused <= 1'b1;
        end else if (core_reset) begin
            phase <= 19'd0;
            paused <= 1'b1;
        end else if (paused) begin
            if (!pause_request) paused <= 1'b0;
        end else if (sum >= 19'd390625) begin
            phase <= sum - 19'd390625;
            if (pause_request) paused <= 1'b1;
        end else begin
            phase <= sum;
        end
    end
endmodule
