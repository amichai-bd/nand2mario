`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Original generated-shade fit fixture. Not a PPU or physical monitor result.
module vga_proof (
    input logic clk_sys, board_reset_n, core_reset, pause_request,
    output logic [3:0] red, green, blue,
    output logic hsync_n, vsync_n,
    output logic ready, paused,
    output logic [63:0] discard_count, repeat_count, display_sequence,
    output logic [31:0] display_epoch,
    output logic [63:0] observed_sequence,
    output logic [14:0] observed_index,
    output logic observed_complete
);
    logic clk_pix, reset_sys, reset_pix, gb_tick;
    n2m_clocking u_clocking (.clk_sys, .board_reset_n, .clk_pix, .reset_sys, .reset_pix, .ready);
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
endmodule
