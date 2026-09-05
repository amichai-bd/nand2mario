`timescale 1ns/1ps
module baseline_monitor(input logic clk, reset, enable,
                        input logic [7:0] operand, value,
                        output logic sampled_reset, sampled_enable,
                        output logic [7:0] sampled_operand, actual,
                        output logic strobe, output integer cycle);
  initial begin strobe = 0; cycle = 0; end
  always @(posedge clk) begin
    sampled_reset = reset; sampled_enable = enable; sampled_operand = operand;
    cycle = cycle + 1;
    // Sample after the DUT's nonblocking update, never drive the DUT here.
    #1;
    actual = value;
    strobe = ~strobe;
  end
endmodule
