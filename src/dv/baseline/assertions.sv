`timescale 1ns/1ps
module baseline_assertions(input logic strobe, reset, enable,
                           input logic [7:0] actual, input integer cycle, seed);
  logic [7:0] previous;
  always @(strobe) if (cycle > 0) begin
    if ((^actual) === 1'bx)
      $fatal(1, "BASELINE_UNKNOWN cycle=%0d expected=known actual=%h seed=%0d", cycle, actual, seed);
    if (reset && actual !== 8'b0)
      $fatal(1, "BASELINE_RESET cycle=%0d expected=0 actual=%0d seed=%0d", cycle, actual, seed);
    if (cycle > 1 && !reset && !enable && actual !== previous)
      $fatal(1, "BASELINE_HOLD cycle=%0d expected=%0d actual=%0d seed=%0d", cycle, previous, actual, seed);
    previous = actual;
  end
endmodule
