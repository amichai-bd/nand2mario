`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Both producers resolve one whole mask before JOYP captures the same edge.
module n2m_input (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var n2m_input_pkg::input_write_t host_write,
    input var logic physical_commit,
    input var logic [7:0] physical_buttons,
    output logic [7:0] host_buttons,
    output logic [7:0] physical_observe,
    output logic [7:0] source_observe,
    output logic [7:0] effective_buttons,
    output n2m_input_pkg::input_update_t effective_update
);
    n2m_input_pkg::input_host_state_t host_q, host_next;
    logic [7:0] physical_q, physical_next, effective_next;
    logic reset;
    assign reset = reset_sys || core_reset;
    always_comb begin
        host_next = host_q;
        physical_next = physical_q;
        if (physical_commit && !gb_tick) physical_next = physical_buttons;
        if (host_write.valid && !gb_tick) begin
            if (host_write.source_write) host_next.physical_source = host_write.value[0];
            else host_next.host_buttons = host_write.value;
        end
        effective_next = host_next.physical_source ? physical_next : host_next.host_buttons;
    end
    // Core reset restores UART ownership but does not release external buttons.
    `DFF_ARST_VAL(host_q, host_next, clk_sys, reset, '0)
    `DFF_ARST_VAL(physical_q, physical_next, clk_sys, reset_sys, 8'd0)
    assign host_buttons = reset ? 8'd0 : host_q.host_buttons;
    assign physical_observe = reset_sys ? 8'd0 : physical_q;
    assign source_observe = reset ? 8'd0 : {7'd0, host_q.physical_source};
    assign effective_buttons = reset ? 8'd0 :
        (host_q.physical_source ? physical_q : host_q.host_buttons);
    assign effective_update.valid = !reset && effective_next != effective_buttons;
    assign effective_update.buttons = reset ? 8'd0 : effective_next;
    `N2M_ASSERT_KNOWN(INPUT_CONTROLS_KNOWN, clk_sys, reset_sys,
        {core_reset, gb_tick, physical_commit, host_write.valid})
    `N2M_ASSERT(INPUT_PHYSICAL_BOUNDARY, clk_sys, reset_sys,
        !physical_commit || (!gb_tick && !$isunknown(physical_buttons)))
    `N2M_ASSERT(INPUT_HOST_BOUNDARY, clk_sys, reset,
        !host_write.valid || (!gb_tick && !$isunknown(host_write)))
    `N2M_ASSERT(INPUT_SOURCE_VALUE, clk_sys, reset,
        !(host_write.valid && host_write.source_write) || host_write.value <= 8'd1)
endmodule
