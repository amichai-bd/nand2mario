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
    n2m_clocking u_clocking (
        .clk_reference, .board_reset_n, .clk_sys, .clk_pix,
        .reset_sys, .reset_pix, .ready()
    );
    n2m_controls_system #(.BUILD_ID(BUILD_ID), .UART_BAUD(UART_BAUD)) u_controls (
        .clk_reference, .board_reset_n, .clk_adc_reference,
        .clk_sys, .clk_pix, .reset_sys, .reset_pix, .buttons_n, .leds,
        .uart_rx, .uart_tx, .red, .green, .blue, .hsync_n, .vsync_n,
        .display_sequence, .display_epoch, .paused, .fault
    );
endmodule
