`timescale 1ns/1ps
`default_nettype none

// Composed placement proof with real board-reference PLLs and qualified resets.
module v05_proof #(
`ifdef N2M_V05_BUILD_ID
    parameter logic [127:0] BUILD_ID = `N2M_V05_BUILD_ID
`else
    parameter logic [127:0] BUILD_ID = 128'h88000000000000000000000000000001
`endif
) (
    input var logic clk_reference,
    input var logic board_reset_n,
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
    n2m_v05_system #(.BUILD_ID(BUILD_ID)) u_system (
        .clk_sys, .clk_pix, .reset_sys, .reset_pix, .uart_rx, .uart_tx,
        .red, .green, .blue, .hsync_n, .vsync_n, .paused, .fault,
        .display_sequence, .display_epoch,
        .gb_tick(), .core_reset(), .epoch(), .dot_count(),
        .retirement_valid(), .retirement(), .bus_commit(), .write_enable(),
        .address(), .write_data(), .read_data(), .irq_ack(),
        .source_valid(), .source_start(), .source_abort(),
        .source_display_eligible(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot()
    );
endmodule
