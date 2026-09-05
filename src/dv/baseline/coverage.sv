`timescale 1ns/1ps
module baseline_coverage(input logic strobe, reset, enable,
                         input logic [7:0] operand, actual,
                         input integer cycle, output logic [7:0] coverage_bits);
  logic [7:0] previous;
  logic active_seen;
  initial begin
    coverage_bits = 0;
    active_seen = 0;
  end
  always @(strobe) if (cycle > 0) begin
    if (reset) coverage_bits[0] = 1;
    if (reset && enable) coverage_bits[1] = 1;
    if (!reset && enable) begin
      coverage_bits[2] = 1; active_seen = 1;
      if (operand == 0) coverage_bits[3] = 1;
      if (operand == 255) coverage_bits[4] = 1;
      if (cycle > 1 && actual < previous) coverage_bits[5] = 1;
    end
    if (!reset && !enable) coverage_bits[6] = 1;
    if (reset && active_seen) coverage_bits[7] = 1;
    previous = actual;
  end
endmodule
