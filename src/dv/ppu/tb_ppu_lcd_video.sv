`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Original scene and coordinate oracle. No expected value uses DUT fetch,
// position, mode, line counters or window state.
module tb_ppu_lcd_video;
    logic clk_sys, reset_sys, core_reset, gb_tick, pause_request, paused;
    logic [31:0] epoch;
    logic [63:0] dot_before;
    logic [1:0] cpu_phase;
    logic write_pending, io_commit, io_write;
    logic [15:0] io_address;
    logic [7:0] io_wdata, io_rdata;
    logic io_selected, vram_request, vram_valid;
    logic [12:0] vram_address;
    logic [7:0] vram_data;
    logic [6:0] oam_pair_address;
    logic [1:0] oam_phase;
    logic [5:0] oam_scan_index;
    logic [15:0] oam_data;
    logic oam_valid, dma_active, vram_cpu_allow, oam_cpu_allow;
    logic stat_condition, vblank_condition, stat_rise, vblank_rise, fault;
    logic source_valid, source_start, source_abort, blank_assert, source_display_eligible;
    logic [1:0] source_shade;
    logic [7:0] source_x, source_y;
    logic [31:0] source_epoch;
    logic [63:0] source_dot, previous_dot, enable_dot, normal_first_dot;
    logic clk_pix, reset_pix, pause_after_frame, white_required, release_seen;
    logic [1:0] pix_release;
    logic [7:0] ref_lcdc;
    logic abort_due, enable_commit;
    logic observe_valid, observe_complete, observe_abort, display_valid;
    logic [14:0] observe_index;
    logic [1:0] observe_shade;
    logic [31:0] observe_epoch, display_epoch;
    logic [63:0] observe_sequence, observe_dot, display_sequence;
    logic [9:0] video_x, video_y;
    logic video_valid, video_active, video_image;
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n;
    integer completed, aborted, stream_frame, checked_image, run_number;
    logic [7:0] vram [0:8191];
    logic [7:0] oam [0:159];
    integer frame_count, pixel_count, trace_file;
    integer t, x, y, p, n;
    logic [7:0] lo, hi;
    logic [1:0] color, expected;
    n2m_timebase timebase (.*);
    n2m_ppu dut (.vram_cpu_read_allow(), .oam_cpu_read_allow(), .*);
    assign io_commit = write_pending && cpu_phase == 3 && gb_tick;
    `DFF_RST_EN(cpu_phase, cpu_phase + 2'd1, clk_sys, gb_tick, reset_sys || core_reset, 2'd0)
    `DFF_RST_EN(dot_before, dot_before + 64'd1, clk_sys, gb_tick, reset_sys || core_reset, 64'd0)
    // Response-valid refers to the prior request, never the fault-masked current
    // request. Returned bytes remain available before the later consuming dot.
    `DFF_RST(vram_valid, vram_request, clk_sys, reset_sys)
    `DFF_RST_EN(vram_data, vram[vram_address], clk_sys, vram_request, reset_sys, 8'd0)
    `DFF_RST(oam_valid, oam_phase != 0, clk_sys, reset_sys)
    `DFF_RST_EN(oam_data, {oam[{oam_pair_address, 1'b1}], oam[{oam_pair_address, 1'b0}]},
        clk_sys, oam_phase != 0, reset_sys, 16'd0)



    `DFF_ARST_VAL(pix_release, {pix_release[0], 1'b1}, clk_pix, reset_sys, 2'b00)
    assign reset_pix = !pix_release[1];
    assign enable_commit = gb_tick && io_commit && io_write && io_address == 16'hff40
        && !ref_lcdc[7] && io_wdata[7];
    `DFF_RST_EN(ref_lcdc, io_wdata, clk_sys,
        gb_tick && io_commit && io_write && io_address == 16'hff40, reset_sys, 8'd0)
    `DFF_RST(abort_due, gb_tick && io_commit && io_write && io_address == 16'hff40
        && ref_lcdc[7] && !io_wdata[7], clk_sys, reset_sys)
    n2m_frame_bridge bridge (
        .clk_sys, .reset_sys, .core_reset, .clk_pix, .reset_pix,
        .source_valid, .source_start, .source_shade, .source_epoch, .source_dot,
        .source_abort, .blank_assert, .source_display_eligible,
        .observe_valid, .observe_complete, .observe_abort, .observe_index,
        .observe_shade, .observe_epoch, .observe_sequence, .observe_dot,
        .discard_count(), .repeat_count(), .display_valid, .display_sequence, .display_epoch,
        .video_x, .video_y, .video_valid, .video_active, .video_image,
        .red, .green, .blue, .hsync_n, .vsync_n
    );
    task automatic write_register(input logic [15:0] address, input logic [7:0] value);
        @(negedge clk_sys);
        io_address = address; io_wdata = value; write_pending = 1;
        do @(posedge clk_sys); while (!(gb_tick && cpu_phase == 3));
        @(negedge clk_sys);
        write_pending = 0;
    endtask
    task automatic disable_at(input integer elapsed);
        @(negedge clk_sys);
        io_address = 16'hff40; io_wdata = 0;
        do @(negedge clk_sys); while (!(gb_tick && dot_before == enable_dot + 64'(elapsed)));
        if (cpu_phase != 3) $fatal(1, "PPU_LCD_ILLEGAL_WRITE");
        write_pending = 1;
        @(posedge clk_sys);
        @(negedge clk_sys);
        write_pending = 0;
        @(negedge clk_sys);
    endtask
    always #10 clk_sys = !clk_sys;
    initial begin
        clk_pix = 0;
        #3;
        forever #(1250.0 / 63.0) clk_pix = !clk_pix;
    end
    always @(posedge clk_sys) begin
        if (!reset_sys) begin
            if (enable_commit) begin enable_dot = dot_before; stream_frame = 0; pixel_count = 0; end
            if (source_abort !== abort_due || observe_abort !== abort_due)
                $fatal(1, "PPU_LCD_ABORT_BOUNDARY run=%0d expected=%0d source=%0d observer=%0d",
                    run_number, abort_due, source_abort, observe_abort);
            if (abort_due) begin
                if (source_valid || observe_valid || observe_complete || !blank_assert)
                    $fatal(1, "PPU_LCD_ABORT_SUPPRESS");
                if ((aborted == 0 && (pixel_count != 0 || completed != 0))
                    || (aborted == 1 && (pixel_count != 23039 || completed != 1)))
                    $fatal(1, "PPU_LCD_ABORT_PROGRESS abort=%0d partial=%0d complete=%0d", aborted, pixel_count, completed);
                aborted = aborted + 1; pixel_count = 0;
            end
            if (source_valid) begin
                if (gb_tick || fault || observe_valid !== 1'b1) $fatal(1, "PPU_LCD_FORWARD");
                expected = stream_frame == 0 ? 2'd0 : 2'd1;
                if (source_x !== 8'(pixel_count % 160) || source_y !== 8'(pixel_count / 160)
                    || source_start !== (pixel_count == 0) || source_shade !== expected
                    || source_display_eligible !== (stream_frame != 0)
                    || source_dot !== dot_before || source_epoch !== 32'd5)
                    $fatal(1, "PPU_LCD_SOURCE run=%0d frame=%0d index=%0d", run_number, stream_frame, pixel_count);
                if (observe_index !== 15'(pixel_count) || observe_shade !== expected
                    || observe_sequence !== 64'(completed) || observe_epoch !== 32'd5
                    || observe_dot !== dot_before || observe_complete !== (pixel_count == 23039))
                    $fatal(1, "PPU_LCD_OBSERVER run=%0d index=%0d expected_sequence=%0d actual=%0d",
                        run_number, pixel_count, completed, observe_sequence);
                $fdisplay(trace_file, "%0d,%0d,%0d,%0d,%0d", run_number, stream_frame, pixel_count, source_dot, expected);
                if (pixel_count == 23039) begin
                    completed = completed + 1; stream_frame = stream_frame + 1; pixel_count = 0;
                end else pixel_count = pixel_count + 1;
            end else if (observe_valid) $fatal(1, "PPU_LCD_PHANTOM_OBSERVER");
        end
    end
    always @(negedge clk_pix) begin
        if (!reset_pix && video_valid && video_image && white_required) begin
            if (red !== 4'hf || green !== 4'hf || blue !== 4'hf) begin
                if (completed < 3 || !display_valid || display_sequence !== 64'd2 || display_epoch !== 32'd5)
                    $fatal(1, "PPU_LCD_EARLY_UNBLANK complete=%0d display=%0d", completed, display_sequence);
                release_seen = 1;
            end
            if (release_seen) begin
                if (red !== 4'ha || green !== 4'ha || blue !== 4'ha)
                    $fatal(1, "PPU_LCD_RELEASE_IMAGE x=%0d y=%0d", video_x, video_y);
                checked_image = checked_image + 1;
            end
        end
    end
    initial begin
        $dumpfile("waves/lcd-video.vcd");
        $dumpvars(0, clk_sys, clk_pix, reset_sys, reset_pix, core_reset,
            gb_tick, dot_before, io_commit, io_address, io_wdata,
            source_valid, source_abort, blank_assert, source_x, source_y,
            source_shade, source_dot, source_display_eligible, observe_valid,
            observe_abort, observe_complete, observe_index, observe_shade,
            observe_sequence, display_valid, display_sequence, red, green,
            blue, video_valid, video_image, video_x, video_y, completed, aborted);
        clk_sys = 0; reset_sys = 1; core_reset = 0; pause_request = 0;
        epoch = 5; write_pending = 0; io_write = 1; io_address = 0; io_wdata = 0;
        dma_active = 0; pixel_count = 0; stream_frame = 0; completed = 0; aborted = 0;
        run_number = 0; enable_dot = 0; white_required = 0; release_seen = 0; checked_image = 0;
        trace_file = $fopen("lcd-source.csv", "w");
        if (!trace_file) $fatal(1, "PPU_LCD_TRACE");
        $fdisplay(trace_file, "run,frame,index,completed_dot,shade");
        for (n = 0; n < 8192; n = n + 1) vram[n] = 0;
        for (n = 0; n < 160; n = n + 1) oam[n] = 0;
        for (y = 0; y < 8; y = y + 1) vram[2*y] = 8'hff;
        repeat (4) @(negedge clk_sys); reset_sys = 0;
        write_register(16'hff43, 3); write_register(16'hff47, 8'he4);
        run_number = 1; write_register(16'hff40, 8'h91);
        disable_at(96);
        repeat (200) @(negedge clk_pix);
        white_required = 1;
        write_register(16'hff43, 1);
        run_number = 2; write_register(16'hff40, 8'h91);
        if ($test$plusargs("lcd_observer_corrupt")) fork
            begin
                wait (completed == 1);
                @(negedge clk_sys);
                force bridge.observe_sequence = 64'd3;
            end
        join_none
        disable_at(135684);
        run_number = 3; write_register(16'hff40, 8'h91);
        wait (completed == 3);
        @(negedge clk_sys); pause_request = 1;
        wait (paused);
        wait (release_seen && video_x == 559 && video_y == 455);
        @(negedge clk_pix);
        #1;
        if (aborted != 2 || completed != 3 || checked_image != 207360)
            $fatal(1, "PPU_LCD_FINAL aborts=%0d complete=%0d image=%0d", aborted, completed, checked_image);
        // A local core reset while host-paused does not erase the last image.
        core_reset = 1;
        repeat (4) @(negedge clk_sys);
        io_address = 16'hff40;
        #1;
        if (io_rdata !== 0 || !display_valid || display_sequence !== 64'd2
            || source_valid || observe_valid || observe_abort)
            $fatal(1, "PPU_LCD_PAUSED_CORE_RESET");
        wait (video_valid && video_image);
        @(negedge clk_pix);
        #1;
        if (red !== 4'ha || green !== 4'ha || blue !== 4'ha)
            $fatal(1, "PPU_LCD_CORE_LAST_IMAGE");
        // Shared reset clears both mailbox endpoints; no one-ended reset case.
        reset_sys = 1;
        #1;
        if (red !== 0 || green !== 0 || blue !== 0 || !hsync_n || !vsync_n)
            $fatal(1, "PPU_LCD_GLOBAL_BLACK");
        repeat (3) @(negedge clk_pix);
        if (display_valid || source_valid || observe_valid)
            $fatal(1, "PPU_LCD_GLOBAL_CLEAR");
        $fclose(trace_file);
        $display("PASS PPU LCD composed first last cancellation aborts=2 frames=3 VGA pixels=207360 resets=2");
        $finish;
    end
    initial begin
        #150000000;
        $fatal(1, "PPU_LCD_TIMEOUT");
    end
endmodule
