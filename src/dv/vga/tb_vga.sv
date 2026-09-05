`timescale 1ns/1ps
module tb_vga;
    logic clk_sys = 0, clk_pix = 0, pixel_running = 1;
    logic board_reset_n = 0, pll_locked = 0, core_reset = 0;
    wire pll_areset, ready, reset_sys, reset_pix;
    always #10 clk_sys = !clk_sys;
    always #19 if (pixel_running) clk_pix = !clk_pix; else clk_pix = 0;
    n2m_reset_control u_reset (.clk_sys, .clk_pix, .board_reset_n, .pll_locked,
                              .pll_areset, .ready, .reset_sys, .reset_pix);
    logic source_valid = 0, source_start = 0;
    logic [1:0] source_shade = 0;
    logic [31:0] source_epoch = 0;
    logic [63:0] source_dot = 0;
    wire observe_valid, observe_complete, display_valid;
    wire [14:0] observe_index;
    wire [1:0] observe_shade;
    wire [31:0] observe_epoch, display_epoch;
    wire [63:0] observe_sequence, observe_dot, discard_count, repeat_count, display_sequence;
    wire [9:0] video_x, video_y;
    wire video_valid, video_active, video_image, hsync_n, vsync_n;
    wire [3:0] red, green, blue;
    n2m_frame_bridge dut (.*);

    function automatic logic [1:0] pattern(input int ep, seq, index);
        int sx, sy;
        sx = index % 160; sy = index / 160;
        return 2'((ep * 3 + seq + sx / 7 + sy / 5 + (sx * sy) % 3) % 4);
    endfunction
    function automatic logic [3:0] gray(input logic [1:0] shade);
        return 4'(15 - 5 * int'(shade));
    endfunction
    int observed_pixel = 0, observed_seq = 0, completed_total = 0;
    bit complete_frames [int][int];
    int raster_frames = 0, displayed_frames = 0, source_edges = 0;
    int pix_edges = 0;
    int seen_banks = 0;
    bit mutation_reuse, mutation_swap;
    bit have_previous_display = 0;
    logic [1:0] previous_display_bank;
    logic [63:0] previous_display_seq;
    logic [31:0] previous_display_epoch;
    bit previous_boundary;
    bit pending_previous = 0, release_previous = 0;
    logic [97:0] previous_offer;

    always @(posedge clk_sys) begin
        source_edges++;
        if (reset_sys) begin
            observed_pixel = 0; observed_seq = 0; pending_previous = 0;
            complete_frames.delete();
        end else begin
            if (core_reset) begin observed_pixel = 0; observed_seq = 0; end
            if (observe_valid !== (source_valid && !core_reset))
                $fatal(1, "OBSERVER_VALID: lost or invented source edge");
            if (observe_valid) begin
                if (observe_index !== 15'(observed_pixel) ||
                    observe_sequence !== 64'(observed_seq) ||
                    observe_epoch !== source_epoch || observe_dot !== source_dot ||
                    observe_shade !== pattern(int'(source_epoch), observed_seq, observed_pixel) ||
                    observe_complete !== (observed_pixel == 23039))
                    $fatal(1, "OBSERVER_PIXEL: epoch=%0d sequence=%0d index=%0d", source_epoch, observed_seq, observed_pixel);
                if (observed_pixel == 23039) begin
                    complete_frames[int'(source_epoch)][observed_seq] = 1;
                    completed_total++; observed_seq++; observed_pixel = 0;
                end else observed_pixel++;
            end
            if (source_valid && !core_reset &&
                ((dut.pending && dut.writer_bank == dut.offer_bank) ||
                 dut.writer_bank == dut.system_display_bank ||
                 (display_valid && dut.writer_bank == dut.display_bank)))
                $fatal(1, "FRAME_BANK_REUSE: writer targets immutable bank");
            if (pending_previous && !release_previous &&
                {dut.offer_bank, dut.offer_epoch, dut.offer_sequence} !== previous_offer)
                $fatal(1, "FRAME_OFFER_CHANGED: pending bundle changed");
            pending_previous = dut.pending;
            release_previous = dut.pending && dut.ack_sys[1] == dut.request && dut.pix_ready_sys[1];
            previous_offer = {dut.offer_bank, dut.offer_epoch, dut.offer_sequence};
        end
    end

    always @(posedge clk_pix) begin : raster_check
        int point, ex, ey, index;
        bit ea, ei;
        logic [3:0] expected_gray;
        if (reset_pix) begin pix_edges = 0; have_previous_display = 0; end
        else begin
            pix_edges++;
            previous_boundary = dut.swap_boundary;
        end
        #1;
        if (!reset_pix) begin
            if (have_previous_display && dut.display_bank != previous_display_bank && !previous_boundary)
                $fatal(1, "FRAME_ACTIVE_SWAP: bank changed outside blanking boundary");
            if (display_valid && (!have_previous_display || dut.display_bank != previous_display_bank)) begin
                if (!complete_frames.exists(int'(display_epoch)) ||
                    !complete_frames[int'(display_epoch)].exists(int'(display_sequence)))
                    $fatal(1, "FRAME_INCOMPLETE: displayed epoch=%0d sequence=%0d", display_epoch, display_sequence);
                displayed_frames++;
                seen_banks |= 1 << dut.display_bank;
            end
            previous_display_bank = dut.display_bank;
            previous_display_seq = display_sequence;
            previous_display_epoch = display_epoch;
            have_previous_display = display_valid;
            if (video_valid !== (pix_edges >= 2))
                $fatal(1, "VGA_PIPELINE: valid edge=%0d", pix_edges);
            if (video_valid) begin
                point = (pix_edges - 2) % 420000;
                ex = point % 800; ey = point / 800;
                ea = ex < 640 && ey < 480;
                ei = ex >= 80 && ex < 560 && ey >= 24 && ey < 456 && display_valid;
                expected_gray = 0;
                if (ei) begin
                    index = ((ey - 24) / 3) * 160 + (ex - 80) / 3;
                    expected_gray = gray(pattern(int'(display_epoch), int'(display_sequence), index));
                end
                if (video_x !== 10'(ex) || video_y !== 10'(ey) || video_active !== ea || video_image !== ei ||
                    hsync_n !== !(ex >= 656 && ex <= 751) || vsync_n !== !(ey >= 490 && ey <= 491) ||
                    {red, green, blue} !== {expected_gray, expected_gray, expected_gray})
                    $fatal(1, "VGA_PIXEL: coordinate=%0d,%0d actual=%0d,%0d expected=%h actual=%h epoch=%0d sequence=%0d",
                           ex, ey, video_x, video_y, expected_gray, red, display_epoch, display_sequence);
                if (point == 419999) raster_frames++;
            end
        end
    end

    task automatic send_pixels(input int count, gap, seq);
        for (int index = 0; index < count; index++) begin
            @(negedge clk_sys);
            source_valid = 1; source_start = index == 0;
            source_shade = pattern(int'(source_epoch), seq, index);
            source_dot++;
            @(negedge clk_sys); source_valid = 0; source_start = 0;
            repeat (gap - 1) @(negedge clk_sys);
        end
    endtask
    task automatic startup;
        #7; board_reset_n = 1;
        wait (!pll_areset); #13; pll_locked = 1;
        wait (!reset_sys && !reset_pix);
        repeat (8) @(negedge clk_sys);
    endtask
    initial begin
        mutation_reuse = $test$plusargs("bank_reuse");
        mutation_swap = $test$plusargs("active_swap");
        $dumpfile("vga.vcd"); $dumpvars(1, tb_vga);
        startup();
        for (int seq = 0; seq < 8; seq++) send_pixels(23040, 1, seq);
        wait (display_valid);
        if (mutation_reuse) begin
            @(negedge clk_sys);
            force dut.writer_bank = dut.display_bank;
            send_pixels(10, 1, 8);
            $fatal(1, "MUTATION_MISSED: bank reuse");
        end
        if (mutation_swap) begin
            wait (video_y == 10 && video_x == 100);
            force dut.display_bank = 2'd2;
            repeat (5) @(negedge clk_pix);
            $fatal(1, "MUTATION_MISSED: active swap");
        end
        $dumpoff;
        repeat (840000) @(negedge clk_pix);
        // Slow producer and paused intervals leave scanout and ownership alive.
        send_pixels(23040, 50, 8);
        send_pixels(23040, 50, 9);
        repeat (420000) @(negedge clk_pix);
        // Core reset abandons partial data but preserves the last complete image.
        send_pixels(311, 1, 10);
        @(negedge clk_sys); core_reset = 1; source_epoch = 1;
        @(negedge clk_sys); core_reset = 0;
        send_pixels(23040, 1, 0);
        @(negedge clk_pix); pixel_running = 0;
        for (int seq = 1; seq < 4; seq++) send_pixels(23040, 1, seq);
        @(negedge clk_sys); pixel_running = 1;
        repeat (840000) @(negedge clk_pix);
        if (discard_count == 0 || repeat_count == 0 || displayed_frames < 3 || raster_frames < 6)
            $fatal(1, "VGA_COVERAGE: discard=%0d repeat=%0d display=%0d rasters=%0d", discard_count, repeat_count, displayed_frames, raster_frames);
        // Raw lock loss asserts both resets even with no pixel edge.
        @(negedge clk_pix); pixel_running = 0;
        #7; pll_locked = 0;
        #1;
        if ({red, green, blue} !== 12'h000 || !hsync_n || !vsync_n || !reset_sys || !reset_pix)
            $fatal(1, "VGA_RESET_MASK: stopped pixel reset outputs");
        repeat (5) @(negedge clk_sys);
        pixel_running = 1; pll_locked = 1; source_epoch = 0;
        wait (!reset_sys && !reset_pix);
        send_pixels(23040, 1, 0);
        repeat (840000) @(negedge clk_pix);
        $display("PASS vga every-pixel observer ownership fast slow pause core-reset lockloss stopped-pixel");
        $finish;
    end
    initial begin #250000000; $fatal(1, "VGA_WATCHDOG"); end
endmodule
