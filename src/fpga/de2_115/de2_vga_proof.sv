`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// DE2-115 VGA DAC fit fixture: the qualified pixel path on this board's ADV7123.
// Nothing here generates pixels. u_clocking, u_timebase and u_bridge are the
// same instances the MAX 10 vga_proof fits, in the same hierarchy, so every
// clocking and frame-bridge check is that board's. What this top owns is the
// board side: four bits of shade onto eight DAC bits, and the DAC's own clock,
// blank and sync controls.
//
// ALTPLL serves this family, so u_clocking is the DE10-Lite's
// src/fpga/de10_lite/n2m_clocking.sv in place (src/fpga/de2_115/README.md).
//
// Bit alignment and DAC control values, with their vendor sources:
//   wiki/src/de2-115-board.md#driving-the-vga-dac
// Board pins: wiki/src/de2-115-board.md#vga
module de2_vga_proof (
    input logic clk_reference, board_reset_n, core_reset, pause_request,
    output logic [7:0] vga_r, vga_g, vga_b,
    output logic vga_hs, vga_vs,
    output logic vga_clk, vga_blank_n, vga_sync_n,
    output logic ready, paused,
    output logic [63:0] discard_count, repeat_count, display_sequence,
    output logic [31:0] display_epoch,
    output logic [63:0] observed_sequence,
    output logic [14:0] observed_index,
    output logic observed_complete
);
    logic clk_sys;
    logic clk_pix, reset_sys, reset_pix, gb_tick;
    n2m_clocking u_clocking (.clk_reference, .clk_sys, .board_reset_n, .clk_pix, .reset_sys, .reset_pix, .ready);
    n2m_timebase u_timebase (.clk_sys, .reset_sys, .core_reset, .pause_request, .gb_tick, .paused);
    logic [14:0] pixel_index;
    logic [63:0] source_dot;
    logic [31:0] source_epoch;
    `DFF_RST_EN(pixel_index, pixel_index == 15'd23039 ? 15'd0 : pixel_index + 15'd1,
                clk_sys, gb_tick, reset_sys || core_reset, 15'd0)
    `DFF_RST_EN(source_dot, source_dot + 64'd1, clk_sys, gb_tick, reset_sys || core_reset, 64'd0)
    `DFF_RST_EN(source_epoch, source_epoch + 32'd1, clk_sys, core_reset, reset_sys, 32'd0)
    logic [1:0] shade;
    assign shade = pixel_index[1:0] ^ pixel_index[9:8] ^ source_epoch[1:0];
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n;
    n2m_frame_bridge u_bridge (
        .clk_sys, .reset_sys, .core_reset, .clk_pix, .reset_pix,
        .source_valid(gb_tick), .source_start(pixel_index == 0), .source_shade(shade),
        .source_dot, .source_epoch,
        .source_abort(1'b0), .blank_assert(1'b0), .source_display_eligible(1'b1),
        .observe_abort(),
        .observe_valid(), .observe_complete(observed_complete), .observe_index(observed_index),
        .observe_shade(), .observe_epoch(), .observe_sequence(observed_sequence), .observe_dot(),
        .discard_count, .repeat_count, .display_valid(), .display_sequence, .display_epoch,
        .video_x(), .video_y(), .video_valid(), .video_active(), .video_image(),
        .red, .green, .blue, .hsync_n, .vsync_n
    );
    // Four bits of shade into eight bits of DAC. Repeating the nibble is the one
    // linear map that sends 4'h0 to 8'h00 and 4'hf to 8'hff: byte = nibble * 17,
    // exact for all sixteen codes, so full white stays full scale and the four
    // DMG shades land on 00/55/aa/ff. Zero-padding the low bits would cap white
    // at 8'hf0. Derivation: wiki/src/de2-115-board.md#four-bits-of-shade-on-eight-dac-bits
    assign vga_r = {red, red};
    assign vga_g = {green, green};
    assign vga_b = {blue, blue};
    assign vga_hs = hsync_n;
    assign vga_vs = vsync_n;
    // ADV7123 controls. The DAC latches data, BLANK and SYNC on the rising edge
    // of its CLOCK, so the pin carries the pixel clock inverted: the DAC samples
    // half a pixel period after the fabric drove the data. BLANK is held at Logic
    // 1 because a Logic 0 would make the DAC ignore the pixel data; the scan
    // already drives 8'h00 outside the active window, which the truth table shows
    // produces the same analog level. SYNC is tied to Logic 0, the datasheet's
    // value when sync is not encoded on green, which also matches green's
    // full-scale current to red's and blue's so grey stays grey.
    assign vga_clk = ~clk_pix;
    assign vga_blank_n = 1'b1;
    assign vga_sync_n = 1'b0;
endmodule
