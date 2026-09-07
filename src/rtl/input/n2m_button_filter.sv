`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
module n2m_button_filter #(
    parameter int unsigned STABLE_CYCLES = 250000
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic [3:0] buttons_n,
    output logic [3:0] pressed,
    output logic [3:0] accepted_pressed
);
    localparam int unsigned COUNT_BITS = $clog2(STABLE_CYCLES + 1);
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [3:0] button_meta;
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [3:0] button_sync;
    `DFF_ARST_VAL(button_meta, buttons_n, clk_sys, reset_sys, 4'hF)
    `DFF_ARST_VAL(button_sync, button_meta, clk_sys, reset_sys, 4'hF)
    genvar i;
    for (i = 0; i < 4; i++) begin : g_button
        logic [COUNT_BITS-1:0] count_q;
        logic [COUNT_BITS-1:0] count_next;
        logic pressed_next;
        always_comb begin
            count_next = count_q;
            pressed_next = pressed[i];
            if ((!button_sync[i]) == pressed[i]) count_next = '0;
            else if (count_q == COUNT_BITS'(STABLE_CYCLES - 1)) begin
                pressed_next = !button_sync[i];
                count_next = '0;
            end else count_next = count_q + COUNT_BITS'(1);
        end
        // Proposal for this edge lets axes and debounce acceptance commit together.
        assign accepted_pressed[i] = reset_sys ? 1'b0 : pressed_next;
        `DFF_ARST_VAL(count_q, count_next, clk_sys, reset_sys, '0)
        `DFF_ARST_VAL(pressed[i], pressed_next, clk_sys, reset_sys, 1'b0)
        `N2M_ASSERT(button_count_range, clk_sys, reset_sys,
            count_q < COUNT_BITS'(STABLE_CYCLES))
    end
    `N2M_ASSERT(button_filter_parameter, clk_sys, reset_sys, STABLE_CYCLES >= 1)
    `N2M_ASSERT_KNOWN(button_filter_known, clk_sys, reset_sys, pressed)
endmodule
