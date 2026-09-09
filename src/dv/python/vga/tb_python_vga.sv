`timescale 1ns/1ps
`default_nettype none
// Public frame-bridge boundary; real Intel memories are selected by the target.
module tb_python_vga;
    logic clk_sys, clk_pix, reset_sys, reset_pix, core_reset;
    logic source_valid, source_start, source_abort, blank_assert;
    logic source_display_eligible;
    logic [1:0] source_shade;
    logic [31:0] source_epoch;
    logic [63:0] source_dot;
    logic observe_valid, observe_complete, observe_abort;
    logic [14:0] observe_index;
    logic [1:0] observe_shade;
    logic [31:0] observe_epoch, display_epoch;
    logic [63:0] observe_sequence, observe_dot, discard_count, repeat_count, display_sequence;
    logic display_valid;
    logic [9:0] video_x, video_y;
    logic video_valid, video_active, video_image;
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n;
    logic [14:0] public_raster;
    integer raster_file;
    int unsigned capture_count;
    assign public_raster = {reset_pix, red, green, blue, hsync_n, vsync_n};
    n2m_frame_bridge dut (.*);
    always #20 clk_sys = !clk_sys;
    // Nominal 25.2 MHz rounded to the declared 1 ps fixture precision.
    always #19.84127 clk_pix = !clk_pix;
    initial begin
        capture_count = 0;
        raster_file = $fopen("public-raster.txt", "w");
        if (!raster_file) $fatal(1, "VGA_CRC_TRACE_OPEN");
    end
    // Passive public-pin capture, after NBA settling. Batch transfer avoids one
    // cross-language callback per pixel; no sample or expected value is omitted.
    always @(posedge clk_pix) begin
        #1;
        if (capture_count < 1260027) begin
            capture_count++;
            $fdisplay(raster_file, "%08h,%016h,%04h", capture_count,
                      longint'($realtime * 1000.0), public_raster);
            if (capture_count % 2048 == 0) $fflush(raster_file);
            if (capture_count == 1260027) begin
                $fdisplay(raster_file, "END");
                $fclose(raster_file);
            end
        end
    end
    initial begin
        clk_sys = 0; clk_pix = 0;
        reset_sys = 1; reset_pix = 1; core_reset = 0;
        source_valid = 0; source_start = 0; source_abort = 0;
        blank_assert = 0; source_display_eligible = 1;
        source_shade = 0; source_epoch = 0; source_dot = 0;
        #1000;
        fork
            begin @(negedge clk_sys); reset_sys = 0; end
            begin @(negedge clk_pix); reset_pix = 0; end
        join
    end
    initial begin
        if ($test$plusargs("rgb_corrupt")) begin
            // Fixed time before the first image: corrupt an actual public output.
            #17000000;
            force dut.red = 4'h0;
        end
    end
    initial begin
        #55000000;
        $fatal(1, "VGA_CRC_WATCHDOG");
    end
endmodule
`default_nettype wire
