`timescale 1ns/1ps
module baseline_reference(input integer prior,
                          input logic reset, enable, input logic [7:0] operand,
                          output integer expected);
  // The oracle retains an integer history and uses modulo arithmetic, not DUT state.
  always @* begin
    if (reset) expected = 0;
    else if (enable) expected = (prior + int'(operand)) % 256;
    else expected = prior;
  end
endmodule
