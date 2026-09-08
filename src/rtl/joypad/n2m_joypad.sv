`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// A registers each selected-line fall; the IF owner consumes that event at B.
module n2m_joypad (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic input_commit,
    input var logic [7:0] input_buttons,
    input var logic io_commit,
    input var logic io_write,
    input var logic [15:0] io_address,
    input var logic [7:0] io_wdata,
    output logic io_selected,
    output logic [7:0] io_rdata,
    output logic [7:0] buttons_observe,
    output logic selected_active,
    output logic request_event
);
    logic reset, write_select;
    logic [7:0] matrix_data;
    logic matrix_active;
    logic [7:0] next_matrix_data;
    logic next_matrix_active, event_q;
    n2m_joypad_pkg::joypad_state_t state_q, state_next, reset_value;
    assign reset = reset_sys || core_reset;
    assign reset_value.buttons = 8'd0;
    assign reset_value.select_bits = n2m_interfaces_pkg::PROFILE_JOYP_SELECT[5:4];
    assign io_selected = io_address == n2m_interfaces_pkg::GB_REG_JOYP;
    assign write_select = io_commit && io_write && io_selected;
    always_comb begin
        state_next = state_q;
        if (input_commit) state_next.buttons = input_buttons;
        if (write_select) state_next.select_bits = io_wdata[5:4];
    end
    `DFF_ARST_VAL(state_q, state_next, clk_sys, reset, reset_value)
    n2m_joypad_matrix u_matrix (
        .buttons(state_q.buttons), .select_bits(state_q.select_bits),
        .read_data(matrix_data), .selected_active(matrix_active)
    );
    n2m_joypad_matrix u_next_matrix (
        .buttons(state_next.buttons), .select_bits(state_next.select_bits),
        .read_data(next_matrix_data), .selected_active(next_matrix_active)
    );
    `DFF_ARST_VAL(event_q, |(matrix_data[3:0] & ~next_matrix_data[3:0]), clk_sys, reset, 1'b0)
    assign request_event = !reset && event_q;
    assign io_rdata = io_selected ? (reset ? {2'b11, n2m_interfaces_pkg::PROFILE_JOYP_SELECT[5:4], 4'hf} : matrix_data) : 8'd0;
    assign buttons_observe = reset ? 8'd0 : state_q.buttons;
    assign selected_active = !reset && matrix_active;
    `N2M_ASSERT(JOYP_COMMIT_BOUNDARY, clk_sys, reset,
        !io_commit || (gb_tick && io_selected))
    `N2M_ASSERT_KNOWN(JOYP_CONTROLS, clk_sys, reset,
        {gb_tick, input_commit, io_commit, io_write})
    `N2M_ASSERT(JOYP_INPUT_KNOWN, clk_sys, reset,
        !input_commit || !$isunknown(input_buttons))
    `N2M_ASSERT(JOYP_WRITE_KNOWN, clk_sys, reset,
        !write_select || !$isunknown(io_wdata))
    `N2M_ASSERT_STABLE_WHEN(JOYP_STATE_STABLE, clk_sys, reset,
        !input_commit && !write_select, state_q)
endmodule
