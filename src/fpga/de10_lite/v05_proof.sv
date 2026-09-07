`timescale 1ns/1ps
`default_nettype none

// Placement proof with externally qualified clocks/resets, not a board image.
module v05_proof (
    input var logic clk_sys,
    input var logic clk_pix,
    input var logic reset_sys,
    input var logic reset_pix,
    input var logic uart_rx,
    output logic uart_tx,
    output logic [3:0] red, green, blue,
    output logic hsync_n, vsync_n,
    output logic [63:0] display_sequence,
    output logic [31:0] display_epoch,
    output logic paused, fault
);
    n2m_v05_system u_system (
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
