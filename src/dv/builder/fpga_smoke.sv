// Build-flow fixture only: no reset, board outputs, or Game Boy behavior.
module fpga_smoke(input logic clk, output logic [7:0] count);
    always_ff @(posedge clk) count <= count + 8'd1;
endmodule
