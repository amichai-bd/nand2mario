`timescale 1ns/1ps
// System-domain acquisition/filtering. The FPGA owner supplies the actual Intel
// ADC command interface and a reset-qualified availability signal.
module n2m_physical_controls #(
    parameter int unsigned BUTTON_CYCLES = 250000,
    parameter int unsigned INTERVAL_CYCLES = 50000,
    parameter int unsigned LIMIT_CYCLES = 1000000,
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
    input var logic [3:0] buttons_n,
    input var logic adc_available,
    output logic command_valid,
    output logic [4:0] command_channel,
    input var logic command_ready,
    input var logic response_valid,
    input var logic [4:0] response_channel,
    input var logic [11:0] response_data,
    output logic physical_commit,
    output logic [7:0] physical_buttons,
    output logic adc_fresh,
    output logic adc_fault
);
    logic [3:0] buttons_pressed;
    logic [3:0] buttons_accepted;
    logic pair_valid;
    logic [11:0] pair_x;
    logic [11:0] pair_y;
    n2m_button_filter #(.STABLE_CYCLES(BUTTON_CYCLES)) u_buttons (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .buttons_n(buttons_n), .pressed(buttons_pressed), .accepted_pressed(buttons_accepted)
    );
    n2m_adc_pairs #(.INTERVAL_CYCLES(INTERVAL_CYCLES), .LIMIT_CYCLES(LIMIT_CYCLES)) u_pairs (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .adc_available(adc_available),
        .command_valid(command_valid), .command_channel(command_channel), .command_ready(command_ready),
        .response_valid(response_valid), .response_channel(response_channel), .response_data(response_data),
        .pair_valid(pair_valid), .pair_x(pair_x), .pair_y(pair_y), .fresh(adc_fresh), .protocol_fault(adc_fault)
    );
    n2m_controls_mask #(.X_MIN(X_MIN), .X_CENTER(X_CENTER), .X_MAX(X_MAX),
        .Y_MIN(Y_MIN), .Y_CENTER(Y_CENTER), .Y_MAX(Y_MAX), .X_REVERSE(X_REVERSE), .Y_REVERSE(Y_REVERSE)) u_mask (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .gb_tick(gb_tick), .buttons_pressed(buttons_accepted),
        .pair_valid(pair_valid), .pair_x(pair_x), .pair_y(pair_y), .fresh(adc_fresh),
        .physical_commit(physical_commit), .physical_buttons(physical_buttons)
    );
endmodule
