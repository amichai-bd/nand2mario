`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
module n2m_controls_mask #(
    parameter int unsigned X_MIN = 0,
    parameter int unsigned X_CENTER = 1352,
    parameter int unsigned X_MAX = 2703,
    parameter int unsigned Y_MIN = 0,
    parameter int unsigned Y_CENTER = 1352,
    parameter int unsigned Y_MAX = 2703,
    parameter bit X_REVERSE = 1'b0,
    parameter bit Y_REVERSE = 1'b0
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic gb_tick,
    input var logic [3:0] buttons_pressed,
    input var logic pair_valid,
    input var logic [11:0] pair_x,
    input var logic [11:0] pair_y,
    input var logic fresh,
    output logic physical_commit,
    output logic [7:0] physical_buttons
);
    n2m_controls_pkg::axis_state_t x_q;
    n2m_controls_pkg::axis_state_t y_q;
    n2m_controls_pkg::axis_state_t x_next;
    n2m_controls_pkg::axis_state_t y_next;
    logic [7:0] published_q;
    logic [7:0] published_next;
    logic [7:0] desired;
    logic x_negative;
    logic x_positive;
    logic y_negative;
    logic y_positive;
    always_comb begin
        x_next = x_q;
        y_next = y_q;
        if (pair_valid) begin
            x_next = n2m_controls_pkg::classify_axis(pair_x, x_q, X_MIN, X_CENTER, X_MAX);
            y_next = n2m_controls_pkg::classify_axis(pair_y, y_q, Y_MIN, Y_CENTER, Y_MAX);
        end
        if (!fresh) begin
            x_next = n2m_controls_pkg::AXIS_CENTER;
            y_next = n2m_controls_pkg::AXIS_CENTER;
        end
    end
    assign x_negative = x_next == n2m_controls_pkg::AXIS_NEGATIVE;
    assign x_positive = x_next == n2m_controls_pkg::AXIS_POSITIVE;
    assign y_negative = y_next == n2m_controls_pkg::AXIS_NEGATIVE;
    assign y_positive = y_next == n2m_controls_pkg::AXIS_POSITIVE;
    // Physical D2..D5 are A, B, Start, Select; the shared mask is R,L,U,D,A,B,Select,Start.
    assign desired = {buttons_pressed[2], buttons_pressed[3], buttons_pressed[1:0],
        Y_REVERSE ? y_negative : y_positive, Y_REVERSE ? y_positive : y_negative,
        X_REVERSE ? x_positive : x_negative, X_REVERSE ? x_negative : x_positive};
    assign physical_buttons = reset_sys ? 8'd0 : desired;
    assign physical_commit = !reset_sys && !gb_tick && desired != published_q;
    `DFF_ARST_VAL(x_q, x_next, clk_sys, reset_sys, n2m_controls_pkg::AXIS_CENTER)
    `DFF_ARST_VAL(y_q, y_next, clk_sys, reset_sys, n2m_controls_pkg::AXIS_CENTER)
    assign published_next = physical_commit ? desired : published_q;
    `DFF_ARST_VAL(published_q, published_next, clk_sys, reset_sys, 8'd0)
    `N2M_ASSERT(controls_calibration, clk_sys, reset_sys,
        X_MIN < X_CENTER && X_CENTER < X_MAX && X_MAX <= 4095 &&
        Y_MIN < Y_CENTER && Y_CENTER < Y_MAX && Y_MAX <= 4095 &&
        X_CENTER - X_MIN >= 512 && X_MAX - X_CENTER >= 512 &&
        Y_CENTER - Y_MIN >= 512 && Y_MAX - Y_CENTER >= 512)
    `N2M_ASSERT_NEVER(controls_tick_commit, clk_sys, reset_sys, physical_commit && gb_tick)
    `N2M_ASSERT_NEVER(controls_opposing_axes, clk_sys, reset_sys,
        (&physical_buttons[1:0]) || (&physical_buttons[3:2]))
    `N2M_ASSERT_KNOWN(controls_mask_known, clk_sys, reset_sys, physical_buttons)
endmodule
