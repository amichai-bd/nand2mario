`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module tb_register_macros;
    logic clk = 0;
    logic reset = 0;
    logic enable = 1;
    logic [31:0] data = 0;
    logic [7:0] plain;
    logic cleared;
    logic [16:0] valued;
    logic [3:0] enabled;
    logic [31:0] combined;
    logic [61:0] expected;
    logic [61:0] actual;
    integer cycle;
    integer seed;
    integer combinations = 0;
    bit corrupt;

    `DFF(plain, data[7:0], clk)
    `DFF_RST(cleared, data[0], clk, reset)
    `DFF_RST_VAL(valued, data[16:0], clk, reset, 17'h1abcd)
    `DFF_EN(enabled, data[3:0], clk, enable)
    `DFF_RST_EN(combined, data, clk, enable, reset, 32'h89abcdef)

    task automatic check(input bit inject);
        actual = {plain, cleared, valued, enabled, combined};
        if (inject) actual[0] = ~actual[0];
        if (actual !== expected)
            $fatal(1, "REGISTER_MISMATCH cycle=%0d seed=%0d expected=%h actual=%h", cycle, seed, expected, actual);
    endtask

    initial begin
        seed = 1;
        if ($value$plusargs("seed=%d", seed)) begin end
        corrupt = $test$plusargs("corrupt");
        $dumpfile("waves/registers.vcd");
        $dumpvars(0, tb_register_macros);
        // Initialize all forms through a real enabled edge, without assuming
        // power-up state for registers that deliberately have no reset.
        #5 clk = 1;
        #1 expected = 0;
        cycle = 0;
        check(0);
        for (cycle = 1; cycle <= 64; cycle = cycle + 1) begin
            #4 clk = 0;
            data = 32'hfedcba98 ^ (cycle * 32'h01020409);
            reset = (cycle % 4) >= 2;
            enable = (cycle % 2) == 1;
            combinations = combinations | (1 << {reset, enable});
            // Reset, enable and input transitions alone must not update state.
            #2 check(0);
            expected[61:54] = data[7:0];
            expected[53] = reset ? 1'b0 : data[0];
            expected[52:36] = reset ? 17'h1abcd : data[16:0];
            if (enable) expected[35:32] = data[3:0];
            if (reset) expected[31:0] = 32'h89abcdef;
            else if (enable) expected[31:0] = data;
            #3 clk = 1;
            #1 check(corrupt && cycle == 5);
        end
        if (combinations != 15) $fatal(1, "REGISTER_COVERAGE expected=15 actual=%0d", combinations);
        $display("PASS register macros cycles=64 combinations=15");
        $finish;
    end
endmodule
`default_nettype wire
