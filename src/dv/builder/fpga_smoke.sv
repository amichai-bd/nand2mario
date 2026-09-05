// Build-flow fixture only: no reset, board outputs, or Game Boy behavior.
`include "src/rtl/common/macros.svh"
module fpga_smoke(input logic clk, output logic [7:0] count);
    `DFF(count, count + 8'd1, clk)
endmodule
