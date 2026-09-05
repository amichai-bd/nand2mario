`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module tb_async_assert_macros;
    logic clk = 0;
    logic reset = 0;
    logic reset_n = 1;
    logic [7:0] data = 0;
    logic [7:0] high_q, low_q;
    logic [7:0] expected_high, expected_low;
    logic [7:0] observed = 0;
    logic hold = 0;
    logic direct_ok = 1;
    logic no_reset_ok = 1;
    logic forbidden = 0;
    logic known_value = 0;
    integer edges = 0;

    `DFF_ARST_VAL(high_q, data, clk, reset, 8'ha5)
    `DFF_ARST_N_VAL(low_q, data, clk, reset_n, 8'h3c)
    `N2M_ASSERT(direct_check, clk, reset, direct_ok)
    `N2M_ASSERT_NO_RST(no_reset_check, clk, no_reset_ok)
    `N2M_ASSERT_NEVER(never_check, clk, reset, forbidden)
    `N2M_ASSERT_KNOWN(known_check, clk, reset, known_value)
    `N2M_ASSERT_STABLE_WHEN(hold_check, clk, reset, hold, observed)

    task automatic compare_registers;
        if (high_q !== expected_high || low_q !== expected_low)
            $fatal(1, "ASYNC_REGISTER_MISMATCH edge=%0d expected=%h/%h actual=%h/%h",
                   edges, expected_high, expected_low, high_q, low_q);
    endtask

    task automatic edge_check;
        #2;
        expected_high = reset ? 8'ha5 : data;
        expected_low = reset_n ? data : 8'h3c;
        clk = 1;
        edges++;
        #1 compare_registers();
        #2 clk = 0;
    endtask

    initial begin
        $dumpfile("waves/async-assert.vcd");
        $dumpvars(0, tb_async_assert_macros);
        // Both reset polarities act between edges and dominate changing data.
        #1 reset = 1; reset_n = 0; data = 8'hff;
        expected_high = 8'ha5; expected_low = 8'h3c;
        #1 compare_registers();
        edge_check();
        reset = 0; reset_n = 1; data = 8'h12; observed = 8'h10;
        #1 compare_registers();
        edge_check();
        // HOLD becomes true on an edge after an allowed change. Testing current
        // HOLD instead of prior HOLD would reject this legitimate transition.
        data = 8'h34; observed = 8'h20; hold = 1;
        edge_check();
        edge_check();
        // A pulse entirely between sampled edges invalidates assertion history.
        #1 reset = 1; reset_n = 0; observed = 8'h30;
        expected_high = 8'ha5; expected_low = 8'h3c;
        #1 compare_registers();
        reset = 0; reset_n = 1; data = 8'h56;
        #1 compare_registers();
        edge_check();
        edge_check();
        // Release hold, then change on the following edge, and hold again.
        hold = 0;
        edge_check();
        observed = 8'h40; hold = 1;
        edge_check();
        edge_check();
        if ($test$plusargs("fail_hold")) observed = 8'h41;
        if ($test$plusargs("fail_direct")) direct_ok = 0;
        if ($test$plusargs("fail_no_reset")) no_reset_ok = 0;
        if ($test$plusargs("fail_never")) forbidden = 1;
        if ($test$plusargs("fail_known")) known_value = 1'bx;
        edge_check();
        $display("PASS async and assertion macros edges=10 reset-pulses=2");
        $finish;
    end
    initial begin
        #1000 $fatal(1, "ASYNC_ASSERT_TIMEOUT");
    end
endmodule
`default_nettype wire
