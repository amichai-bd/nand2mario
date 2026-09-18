`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// DE10-Nano flow proof: a free-running counter on the board LEDs. It proves the
// Cyclone V build path, not Game Boy behaviour, and it is not a board image.
// Board pins: wiki/src/de10-nano-board.md
module nano_smoke (
    input logic clk_reference,
    input logic key0_n,
    output logic [7:0] leds
);
    // KEY0 is an asynchronous button, so it is synchronized before it resets
    // anything. Pressed is low, so the synchronized reset is active high.
    logic [1:0] reset_sync;
    logic reset;
    `DFF(reset_sync, {reset_sync[0], ~key0_n}, clk_reference)
    assign reset = reset_sync[1];
    logic [31:0] count;
    logic [31:0] count_next;
    assign count_next = reset ? 32'd0 : count + 32'd1;
    `DFF(count, count_next, clk_reference)
    // The top eight bits divide the 50 MHz reference to a visible LED walk.
    assign leds = count[31:24];
endmodule
