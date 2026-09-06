`timescale 1ns/1ps
// Original build-harness fixture: no Game Boy behavior or reference HDL.
module builder_smoke;
    logic clk;
    logic reset;
    logic [3:0] count;
    integer seed;
    integer expected;
    integer cycle;
    integer ignored;
    always #5 clk = ~clk;
    always @(posedge clk) begin
        if (reset) count <= 0;
        else count <= count + 1'b1;
    end
    initial begin
        clk = 0;
        reset = 1;
        count = 0;
        ignored = $value$plusargs("seed=%d", seed);
        $dumpfile("waves/smoke.vcd");
        $dumpvars(0, builder_smoke);
        @(negedge clk);
        if (count !== 0) $fatal(1, "reset expected=0 actual=%0d seed=%0d", count, seed);
        reset = 0;
        for (cycle = 1; cycle <= 20; cycle = cycle + 1) begin
            @(negedge clk);
            expected = cycle % 16;
            if ($test$plusargs("inject_failure") && cycle == 3) expected = 7;
            if (count !== expected[3:0])
                $fatal(1, "count cycle=%0d expected=%0d actual=%0d seed=%0d", cycle, expected, count, seed);
        end
        reset = 1;
        @(negedge clk);
        if (count !== 0) $fatal(1, "second reset expected=0 actual=%0d seed=%0d", count, seed);
        $display("PASS builder-smoke seed=%0d checks=22", seed);
        $finish;
    end
    initial begin
        #1000;
        $fatal(1, "watchdog seed=%0d", seed);
    end
endmodule
