`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Compose the actual renderer stimulus with the actual VGA bridge. Independent
// observer counters do not read the renderer's decoded position or bank state.
module tb_ppu_video;
    tb_ppu_render scene();
    logic clk_pix, reset_pix;
    logic [1:0] pix_release;
    logic observe_valid, observe_complete, observe_abort;
    logic [14:0] observe_index;
    logic [1:0] observe_shade;
    logic [31:0] observe_epoch;
    logic [63:0] observe_sequence, observe_dot;
    integer index, frame, completed;
    logic [1:0] expected;
    initial begin
        clk_pix = 0;
        index = 0; frame = 0; completed = 0;
        #3;
        forever #(1250.0 / 63.0) clk_pix = !clk_pix;
    end
    `DFF_ARST_VAL(pix_release, {pix_release[0], 1'b1}, clk_pix, scene.reset_sys, 2'b00)
    assign reset_pix = !pix_release[1];
    n2m_frame_bridge bridge (
        .clk_sys(scene.clk_sys), .reset_sys(scene.reset_sys), .core_reset(scene.core_reset),
        .clk_pix, .reset_pix,
        .source_valid(scene.source_valid), .source_start(scene.source_start),
        .source_shade(scene.source_shade), .source_epoch(scene.source_epoch),
        .source_dot(scene.source_dot), .source_abort(scene.source_abort),
        .blank_assert(scene.blank_assert), .source_display_eligible(scene.source_display_eligible),
        .observe_valid, .observe_complete, .observe_abort, .observe_index, .observe_shade,
        .observe_epoch, .observe_sequence, .observe_dot,
        .discard_count(), .repeat_count(), .display_valid(), .display_sequence(), .display_epoch(),
        .video_x(), .video_y(), .video_valid(), .video_active(), .video_image(),
        .red(), .green(), .blue(), .hsync_n(), .vsync_n()
    );
    always @(posedge scene.clk_sys) begin
        if (!scene.reset_sys) begin
            if (observe_abort || observe_valid !== scene.source_valid)
                $fatal(1, "PPU_VIDEO_OBSERVER_VALID");
            if (observe_valid) begin
                expected = frame == 0 ? 2'd0 : scene.scene(index % 160, index / 160);
                if (observe_index !== 15'(index) || observe_sequence !== 64'(frame)
                    || observe_epoch !== 32'd5 || observe_dot !== scene.dot_before
                    || observe_shade !== expected || observe_complete !== (index == 23039))
                    $fatal(1, "PPU_VIDEO_OBSERVER_PIXEL frame=%0d index=%0d", frame, index);
                if (index == 23039) begin
                    completed = completed + 1;
                    frame = frame + 1; index = 0;
                    $display("PPU_VIDEO_OBSERVER_COMPLETE count=%0d pixels=%0d", completed, completed * 23040);
                end else index = index + 1;
            end
        end
    end
    initial begin
        wait (scene.simulation_done);
        @(negedge scene.clk_sys);
        if (completed != 3) $fatal(1, "PPU_VIDEO_COMPLETION_COUNT actual=%0d", completed);
        $display("PASS PPU video observer frames=3 pixels=69120");
        $finish;
    end
    initial begin
        if ($test$plusargs("observer_corrupt")) begin
            wait (frame == 1);
            @(negedge scene.clk_sys);
            force bridge.observe_shade = 2'd3;
        end
    end
endmodule
