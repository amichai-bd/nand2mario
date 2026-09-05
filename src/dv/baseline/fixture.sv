`timescale 1ns/1ps
// Test-only accumulator. This is not Game Boy RTL.
module baseline_fixture(input logic clk, reset, enable,
                        input logic [7:0] operand, output logic [7:0] value);
  logic broken;
  initial broken = $test$plusargs("broken");
  always @(posedge clk) begin
    if (reset) value <= 8'b0;
    else if (enable) value <= value + (broken ? {1'b0, operand[6:0]} : operand);
  end
endmodule
