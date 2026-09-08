`timescale 1ns/1ps
`default_nettype none

// Actual Game Boy composition with the delivered physical-control producer.
module v05_controls_proof #(
`ifdef N2M_V05_BUILD_ID
    parameter logic [127:0] BUILD_ID = `N2M_V05_BUILD_ID
`else
    parameter logic [127:0] BUILD_ID = 128'h88000000000000000000000000000001
`endif
,
    parameter integer UART_BAUD = 115200
) (
    input var logic clk_reference,
    input var logic board_reset_n,
    input var logic clk_adc_reference,
    input var logic [3:0] buttons_n,
    output logic [9:0] leds,
    input var logic uart_rx,
    output logic uart_tx,
    output logic [3:0] red, green, blue,
    output logic hsync_n, vsync_n,
    output logic [63:0] display_sequence,
    output logic [31:0] display_epoch,
    output logic paused, fault
);
    logic clk_sys;
    logic clk_pix;
    logic reset_sys;
    logic reset_pix;
    logic gb_tick;
    logic physical_commit;
    logic [7:0] physical_buttons, effective_buttons, input_source;
    logic command_valid, command_ready, response_valid;
    logic [4:0] command_channel, response_channel;
    logic [11:0] response_data;
    logic clk_adc, adc_pll_reset, adc_pll_locked, adc_reset, fresh, adc_fault;
    // Acquisition uses global reset; a Game Boy core reset retains physical state.
    n2m_reset_control u_adc_reset (
        .clk_reference, .clk_sys, .clk_pix(clk_adc),
        .board_reset_n(board_reset_n && !reset_sys), .pll_locked(adc_pll_locked),
        .pll_areset(adc_pll_reset), .ready(), .reset_sys(adc_reset), .reset_pix()
    );
    n2m_adc_backend u_adc (
        .clk_sys, .clk_adc_reference, .pll_areset(adc_pll_reset), .reset_sys(adc_reset),
        .command_valid, .command_channel, .command_ready, .response_valid,
        .response_channel, .response_data, .clk_adc, .pll_locked(adc_pll_locked)
    );
    n2m_physical_controls u_physical (
        .clk_sys, .reset_sys, .gb_tick, .buttons_n, .adc_available(!adc_reset),
        .command_valid, .command_channel, .command_ready, .response_valid,
        .response_channel, .response_data, .physical_commit, .physical_buttons,
        .adc_fresh(fresh), .adc_fault
    );
    assign leds[7:0] = effective_buttons;
    assign leds[8] = input_source == n2m_interfaces_pkg::INPUT_SOURCE_PHYSICAL;
    assign leds[9] = fresh;
    n2m_clocking u_clocking (
        .clk_reference, .board_reset_n, .clk_sys, .clk_pix,
        .reset_sys, .reset_pix, .ready()
    );
    n2m_v05_system #(.BUILD_ID(BUILD_ID), .UART_BAUD(UART_BAUD)) u_system (
        .clk_sys, .clk_pix, .reset_sys, .reset_pix, .uart_rx, .uart_tx,
        .physical_commit, .physical_buttons,
        .effective_buttons, .input_source_observe(input_source),
        .red, .green, .blue, .hsync_n, .vsync_n, .paused, .fault,
        .display_sequence, .display_epoch,
        .gb_tick, .core_reset(), .epoch(), .dot_count(),
        .retirement_valid(), .retirement(), .bus_commit(), .write_enable(),
        .address(), .write_data(), .read_data(), .irq_ack(),
        .source_valid(), .source_start(), .source_abort(),
        .source_display_eligible(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot()
    );
endmodule
