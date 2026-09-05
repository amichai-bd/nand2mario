`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
module tb_vga;
    logic clk_sys = 0, clk_pix = 0, pixel_running = 1;
    bit pixel_phase = 0;
    logic board_reset_n = 0, pll_locked = 0, core_reset = 0;
    wire pll_areset, ready, reset_sys, reset_pix;
    always #10 clk_sys = !clk_sys;
    // Nominal 63/125 clock ratio, rounded to the fixture's 1 ps precision.
    // Preserve oscillator phase through clock stops: rising edges remain on odd
    // half-cycles, so the 3 ns offset excludes coincident system rising edges.
    initial begin
        #3;
        forever #(1250.0 / 63.0) begin
            pixel_phase = !pixel_phase;
            clk_pix = pixel_running && pixel_phase;
        end
    end
    `N2M_ASSERT_NO_RST(fixture_distinct_edges, clk_pix,
        (longint'($realtime * 1000.0) % 20000) != 10000)
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

    // Event deadlines model the specified crossings without reading DUT state.
    // Source and pixel rising edges never coincide in this variable-phase fixture.
    int ref_sys_edges = 0, ref_pix_edges = 0, ref_ready_samples = 0;
    int ref_index = 0, ref_source_seq = 0;
    int ref_writer = 0, ref_old_display = 1, ref_free = 2, ref_offer_bank = 0;
    int ref_offer_seq = 0, ref_offer_epoch = 0;
    int ref_capture_edge = 0, ref_return_edge = 0;
    int ref_display_bank = 1, ref_display_seq = 0, ref_display_epoch = 0;
    longint unsigned ref_discards = 0, ref_repeats = 0;
    bit ref_pending = 0, ref_returning = 0, ref_captured = 0, ref_display_valid = 0;
    int ref_raster_point = 0;
    int ack_completion_coincidences = 0;
    always @(posedge clk_sys) begin : source_ownership_oracle
        bit returning_now;
        ref_sys_edges++;
        if (reset_sys) begin
            ref_index = 0; ref_source_seq = 0; ref_ready_samples = 0;
            ref_writer = 0; ref_old_display = 1; ref_free = 2;
            ref_offer_bank = 0; ref_pending = 0; ref_returning = 0;
            ref_discards = 0;
        end else begin
            returning_now = ref_pending && ref_returning && ref_sys_edges == ref_return_edge;
            if (returning_now) begin
                ref_free = ref_old_display;
                ref_old_display = ref_offer_bank;
                ref_pending = 0; ref_returning = 0;
            end
            if (core_reset) begin ref_index = 0; ref_source_seq = 0; end
            else if (source_valid) begin
                if (ref_index == 23039) begin
                    if (returning_now) ack_completion_coincidences++;
                    if (!ref_pending && ref_ready_samples >= 2) begin
                        ref_offer_bank = ref_writer;
                        ref_offer_seq = ref_source_seq;
                        ref_offer_epoch = int'(source_epoch);
                        ref_pending = 1;
                        ref_writer = ref_free;
                        ref_capture_edge = ref_pix_edges + 4;
                    end else ref_discards++;
                    ref_source_seq++; ref_index = 0;
                end else ref_index++;
            end
            if (reset_pix) ref_ready_samples = 0;
            else if (ref_ready_samples < 2) ref_ready_samples++;
        end
        #1;
        if (!reset_sys && (discard_count !== ref_discards || dut.writer_bank !== 2'(ref_writer) ||
            dut.system_display_bank !== 2'(ref_old_display) || dut.pending !== ref_pending))
            $fatal(1, "FRAME_SOURCE_SELECTION: expected writer=%0d display=%0d pending=%0d discards=%0d actual=%0d,%0d,%0d,%0d",
                   ref_writer, ref_old_display, ref_pending, ref_discards,
                   dut.writer_bank, dut.system_display_bank, dut.pending, discard_count);
    end

    // Sampled local safety checks complement the independent source/raster oracle.
    `N2M_ASSERT_NEVER(frame_bank_reuse, clk_sys, reset_sys,
        (dut.pending && dut.writer_bank == dut.offer_bank) ||
        dut.writer_bank == dut.system_display_bank ||
        (display_valid && dut.writer_bank == dut.display_bank))
    `N2M_ASSERT_STABLE_WHEN(frame_offer_stable, clk_sys, reset_sys,
        dut.pending && !(dut.ack_sys[1] == dut.request && dut.pix_ready_sys[1]),
        {dut.offer_bank, dut.offer_epoch, dut.offer_sequence})
    `N2M_ASSERT_STABLE_WHEN(frame_active_swap, clk_pix, reset_pix,
        !dut.swap_boundary, dut.display_bank)

    always @(posedge clk_sys) begin
        source_edges++;
        if (reset_sys) begin
            observed_pixel = 0; observed_seq = 0;
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
        end
    end

    always @(posedge clk_pix) begin : raster_check
        int point, ex, ey, index;
        bit ea, ei;
        logic [3:0] expected_gray;
        bit captured_before;
        ref_pix_edges++;
        if (reset_pix) begin
            pix_edges = 0; have_previous_display = 0;
            ref_captured = 0; ref_display_valid = 0; ref_display_bank = 1;
            ref_display_seq = 0; ref_display_epoch = 0; ref_repeats = 0; ref_raster_point = 0;
        end
        else begin
            pix_edges++;
            captured_before = ref_captured;
            if (ref_pending && !ref_returning && ref_pix_edges == ref_capture_edge) ref_captured = 1;
            if (ref_raster_point == 384000) begin
                if (captured_before) begin
                    ref_display_valid = 1; ref_display_bank = ref_offer_bank;
                    ref_display_seq = ref_offer_seq; ref_display_epoch = ref_offer_epoch;
                    ref_captured = 0; ref_returning = 1; ref_return_edge = ref_sys_edges + 3;
                end else if (ref_display_valid) ref_repeats++;
            end
            ref_raster_point = (ref_raster_point + 1) % 420000;
        end
        #1;
        if (!reset_pix) begin
            if (display_valid !== ref_display_valid || dut.display_bank !== 2'(ref_display_bank) ||
                display_sequence !== 64'(ref_display_seq) || display_epoch !== 32'(ref_display_epoch) ||
                repeat_count !== ref_repeats)
                $fatal(1, "FRAME_DISPLAY_SELECTION: expected epoch=%0d seq=%0d bank=%0d repeats=%0d actual=%0d,%0d,%0d,%0d",
                       ref_display_epoch, ref_display_seq, ref_display_bank, ref_repeats,
                       display_epoch, display_sequence, dut.display_bank, repeat_count);
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
                ei = ex >= 80 && ex < 560 && ey >= 24 && ey < 456 && ref_display_valid;
                expected_gray = 0;
                if (ei) begin
                    index = ((ey - 24) / 3) * 160 + (ex - 80) / 3;
                    expected_gray = gray(pattern(ref_display_epoch, ref_display_seq, index));
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
            @(negedge clk_pix);
            force dut.display_bank = 2'd2;
            repeat (5) @(negedge clk_pix);
            $fatal(1, "MUTATION_MISSED: active swap");
        end
        $dumpoff;
        // Arrange an acknowledgement and completion on exactly the same system edge.
        repeat (5) @(negedge clk_sys);
        send_pixels(23040, 1, 8);
        send_pixels(23039, 1, 9);
        wait (ref_returning);
        wait (ref_sys_edges == ref_return_edge - 1);
        @(negedge clk_sys);
        source_valid = 1; source_start = 0;
        source_shade = pattern(int'(source_epoch), 9, 23039); source_dot++;
        @(negedge clk_sys); source_valid = 0;
        repeat (840000) @(negedge clk_pix);
        // Slow producer and paused intervals leave scanout and ownership alive.
        send_pixels(23040, 50, 10);
        send_pixels(23040, 50, 11);
        repeat (420000) @(negedge clk_pix);
        // Core reset abandons partial data but preserves the last complete image.
        send_pixels(311, 1, 12);
        @(negedge clk_sys); core_reset = 1; source_epoch = 1;
        @(negedge clk_sys); core_reset = 0;
        send_pixels(23040, 1, 0);
        if (!ref_pending) $fatal(1, "VGA_COVERAGE: core reset needs immutable pending frame");
        @(negedge clk_sys); core_reset = 1; source_epoch = 2;
        @(negedge clk_sys); core_reset = 0;
        @(negedge clk_pix); pixel_running = 0;
        for (int seq = 0; seq < 3; seq++) send_pixels(23040, 1, seq);
        @(negedge clk_sys); pixel_running = 1;
        repeat (840000) @(negedge clk_pix);
        if (discard_count == 0 || repeat_count == 0 || displayed_frames < 3 || raster_frames < 6 ||
            ack_completion_coincidences != 1 || seen_banks != 7)
            $fatal(1, "VGA_COVERAGE: discard=%0d repeat=%0d display=%0d rasters=%0d", discard_count, repeat_count, displayed_frames, raster_frames);
        // Raw lock loss asserts both resets even with no pixel edge.
        @(negedge clk_pix); pixel_running = 0;
        send_pixels(23040, 1, 3);
        send_pixels(23040, 1, 4);
        if (!ref_pending) $fatal(1, "VGA_COVERAGE: reset needs outstanding offer");
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
