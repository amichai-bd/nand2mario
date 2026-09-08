`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Component timing proof with virtual CPU/memory ports. No backing-store,
// complete CPU/system, programming or physical monitor acceptance is claimed.
module ppu_proof (
    input var logic clk_reference,
    input var logic board_reset_n,
    input var logic core_reset,
    input var logic pause_request,
    input var logic io_commit,
    input var logic io_write,
    input var logic [15:0] io_address,
    input var logic [7:0] io_wdata,
    input var logic [7:0] vram_data,
    input var logic vram_valid,
    input var logic [15:0] oam_data,
    input var logic oam_valid,
    input var logic dma_active,
    output logic ready, paused, io_selected,
    output logic [7:0] io_rdata,
    output logic vram_request, vram_cpu_allow, oam_cpu_allow,
    output logic [12:0] vram_address,
    output logic [6:0] oam_pair_address,
    output logic [1:0] oam_phase,
    output logic [5:0] oam_scan_index,
    output logic stat_condition, stat_rise, vblank_condition, vblank_rise, fault,
    output logic [3:0] red, green, blue,
    output logic hsync_n, vsync_n,
    output logic [63:0] discard_count, repeat_count, display_sequence,
    output logic [31:0] display_epoch,
    output logic [63:0] observed_sequence, observed_dot,
    output logic [31:0] observed_epoch,
    output logic [14:0] observed_index,
    output logic [1:0] observed_shade,
    output logic observed_valid, observed_complete, observed_abort
);
    logic clk_sys;
    logic clk_pix, reset_sys, reset_pix, gb_tick;
    logic [63:0] dot_before;
    logic [31:0] epoch;
    logic source_valid, source_start, source_abort, blank_assert, source_display_eligible;
    logic [1:0] source_shade;
    logic [31:0] source_epoch;
    logic [63:0] source_dot;
    n2m_clocking u_clocking (.clk_reference, .clk_sys, .board_reset_n, .clk_pix, .reset_sys, .reset_pix, .ready);
    n2m_timebase u_timebase (.clk_sys, .reset_sys, .core_reset, .pause_request, .gb_tick, .paused);
    `DFF_RST_EN(dot_before, dot_before + 64'd1, clk_sys, gb_tick, reset_sys || core_reset, 64'd0)
    `DFF_RST_EN(epoch, epoch + 32'd1, clk_sys, core_reset, reset_sys, 32'd0)
    n2m_ppu u_ppu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .epoch, .dot_before,
        .io_commit, .io_write, .io_address, .io_wdata, .io_selected, .io_rdata,
        .vram_request, .vram_address, .vram_data, .vram_valid,
        .oam_pair_address, .oam_phase, .oam_scan_index, .oam_data, .oam_valid, .dma_active,
        .vram_cpu_allow, .oam_cpu_allow, .vram_cpu_read_allow(), .oam_cpu_read_allow(), .oam_late_future(), .oam_cpu_late_write(), .stat_condition, .stat_rise,
        .vblank_condition, .vblank_rise, .fault,
        .source_valid, .source_start, .source_shade, .source_x(), .source_y(),
        .source_epoch, .source_dot, .source_abort, .blank_assert, .source_display_eligible
    );
    n2m_frame_bridge u_bridge (
        .clk_sys, .reset_sys, .core_reset, .clk_pix, .reset_pix,
        .source_valid, .source_start, .source_shade, .source_epoch, .source_dot,
        .source_abort, .blank_assert, .source_display_eligible,
        .observe_valid(observed_valid), .observe_complete(observed_complete),
        .observe_abort(observed_abort), .observe_index(observed_index),
        .observe_shade(observed_shade), .observe_epoch(observed_epoch),
        .observe_sequence(observed_sequence), .observe_dot(observed_dot),
        .discard_count, .repeat_count, .display_sequence, .display_epoch, .display_valid(),
        .video_x(), .video_y(), .video_valid(), .video_active(), .video_image(),
        .red, .green, .blue, .hsync_n, .vsync_n
    );
endmodule
