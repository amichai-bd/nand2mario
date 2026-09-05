`timescale 1ns/1ps
`default_nettype none
`define SYNTHESIS
`include "src/rtl/common/macros.svh"
module tb_assert_synthesis;
    // Undefined arguments and temporal expressions must disappear completely.
    `N2M_ASSERT(removed, absent_clk, absent_reset, absent_value |=> absent_value)
    `N2M_ASSERT_NO_RST(removed_no_reset, absent_clk, absent_value)
    `N2M_ASSERT_NEVER(removed_never, absent_clk, absent_reset, absent_value)
    `N2M_ASSERT_KNOWN(removed_known, absent_clk, absent_reset, absent_value)
    `N2M_ASSERT_STABLE_WHEN(removed_hold, absent_clk, absent_reset, absent_hold, absent_value)
    initial begin
        #1 $display("PASS assertion synthesis exclusion");
        $finish;
    end
endmodule
`undef SYNTHESIS
`default_nettype wire
