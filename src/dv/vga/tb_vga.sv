`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
module tb_vga;
    logic clk_sys, clk_pix, pixel_running;
    bit pixel_phase;
    logic board_reset_n, pll_locked, core_reset;
    logic pll_areset, ready, reset_sys, reset_pix;
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
    logic source_valid, source_start;
    logic source_abort, blank_assert, source_display_eligible, observe_abort;

    logic [1:0] source_shade;
    logic [31:0] source_epoch;
    logic [63:0] source_dot;
    logic observe_valid, observe_complete, display_valid;
    logic [14:0] observe_index;
    logic [1:0] observe_shade;
    logic [31:0] observe_epoch, display_epoch;
    logic [63:0] observe_sequence, observe_dot, discard_count, repeat_count, display_sequence;
    logic [9:0] video_x, video_y;
    logic video_valid, video_active, video_image, hsync_n, vsync_n;
    logic [3:0] red, green, blue;
    n2m_frame_bridge dut (.*);

    function automatic logic [1:0] pattern(input int ep, seq, index);
        int sx, sy;
        sx = index % 160; sy = index / 160;
        return 2'((ep * 3 + seq + sx / 7 + sy / 5 + (sx * sy) % 3) % 4);
    endfunction
    function automatic logic [3:0] gray(input logic [1:0] shade);
        return 4'(15 - 5 * int'(shade));
    endfunction
    int observed_pixel, observed_seq, completed_total;
    bit complete_frames [int][int];
    int raster_frames, displayed_frames, source_edges;
    int pix_edges;
    int seen_banks;
    bit mutation_reuse, mutation_swap, mutation_latency;
    logic [1:0] late_shade;
    integer pixel_trace;
    // Fault injection delays the actual RAM response, not the raster oracle.
    always @(posedge clk_pix) late_shade <= dut.bank_shade[dut.display_bank];
    logic [1:0] mutation_bank;
    bit have_previous_display;
    logic [1:0] previous_display_bank;
    logic [63:0] previous_display_seq;
    logic [31:0] previous_display_epoch;

    // Event deadlines model the specified crossings without reading DUT state.
    // Source and pixel rising edges never coincide in this variable-phase fixture.
    int ref_sys_edges, ref_pix_edges, ref_ready_samples;
    int ref_index, ref_source_seq;
    int ref_writer, ref_old_display, ref_free, ref_offer_bank;
    int ref_offer_seq, ref_offer_epoch;
    int ref_capture_edge, ref_return_edge;
    int ref_display_bank, ref_display_seq, ref_display_epoch;
    longint unsigned ref_discards, ref_repeats;
    bit ref_pending, ref_returning, ref_captured, ref_display_valid;
    int ref_raster_point;
    int ack_completion_coincidences;
    bit ref_blank_requested, ref_blank_active, ref_release;
    bit sampled_blank [int];
    bit sampled_active [int];
    int abort_total, blank_cycles, blank_releases;

    always @(posedge clk_sys) begin : source_ownership_oracle
        bit returning_now;
        ref_sys_edges++;
        sampled_active[ref_sys_edges] = ref_blank_active;
        sampled_active.delete(ref_sys_edges - 3);
        if (reset_sys) begin
            ref_index = 0; ref_source_seq = 0; ref_ready_samples = 0;
            ref_writer = 0; ref_old_display = 1; ref_free = 2;
            ref_offer_bank = 0; ref_pending = 0; ref_returning = 0;
            ref_discards = 0;
            ref_blank_requested = 0; ref_release = 0; sampled_active.delete();
        end else begin
            if (blank_assert || core_reset) ref_release = 0;
            if (blank_assert) ref_blank_requested = 1;
            returning_now = ref_pending && ref_returning && ref_sys_edges == ref_return_edge;
            if (returning_now) begin
                ref_free = ref_old_display;
                ref_old_display = ref_offer_bank;
                ref_pending = 0; ref_returning = 0;
                if (ref_release) ref_blank_requested = 0;
                ref_release = 0;
            end
            if (core_reset) begin ref_index = 0; ref_source_seq = 0; end
            else if (source_abort) ref_index = 0;
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
                        ref_release = ref_blank_requested && source_display_eligible
                            && sampled_active.exists(ref_sys_edges - 2)
                            && sampled_active[ref_sys_edges - 2] && !blank_assert;
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
        (!reset_pix && display_valid && dut.writer_bank == dut.display_bank))
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
            if (observe_abort !== (source_abort && !core_reset))
                $fatal(1, "OBSERVER_ABORT: lost or invented cancellation");
            if (observe_abort) begin
                if (observe_complete || observe_sequence !== 64'(observed_seq)
                    || observe_epoch !== source_epoch) $fatal(1, "OBSERVER_ABORT_IDENTITY");
                observed_pixel = 0; abort_total++;
            end
            if (observe_valid !== (source_valid && !source_abort && !core_reset))
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
        sampled_blank[ref_pix_edges] = ref_blank_requested;
        sampled_blank.delete(ref_pix_edges - 3);
        if (reset_pix) begin
            pix_edges = 0; have_previous_display = 0;
            ref_captured = 0; ref_display_valid = 0; ref_display_bank = 1;
            ref_display_seq = 0; ref_display_epoch = 0; ref_repeats = 0; ref_raster_point = 0;
            ref_blank_active = 0; sampled_blank.delete();
        end
        else begin
            pix_edges++;
            captured_before = ref_captured;
            if (sampled_blank.exists(ref_pix_edges - 2) && sampled_blank[ref_pix_edges - 2])
                ref_blank_active = 1;
            else if (ref_raster_point == 384000) begin
                if (ref_blank_active) blank_releases++;
                ref_blank_active = 0;
            end
            if (ref_blank_active) blank_cycles++;
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
                ei = ex >= 80 && ex < 560 && ey >= 24 && ey < 456 && (ref_display_valid || ref_blank_active);
                expected_gray = 0;
                if (ei) begin
                    index = ((ey - 24) / 3) * 160 + (ex - 80) / 3;
                    expected_gray = ref_blank_active ? 4'hf : gray(pattern(ref_display_epoch, ref_display_seq, index));
                end
                if (video_x !== 10'(ex) || video_y !== 10'(ey) || video_active !== ea || video_image !== ei ||
                    hsync_n !== !(ex >= 656 && ex <= 751) || vsync_n !== !(ey >= 490 && ey <= 491) ||
                    {red, green, blue} !== {expected_gray, expected_gray, expected_gray})
                    $fatal(1, "VGA_PIXEL: coordinate=%0d,%0d actual=%0d,%0d expected=%h actual=%h epoch=%0d sequence=%0d",
                           ex, ey, video_x, video_y, expected_gray, red, display_epoch, display_sequence);
                if (ei && (ex == 80 || ex == 559))
                    $fdisplay(pixel_trace,"%0t,%0d,%0d,%0d,%0d,%h,%h",$time,ref_display_epoch,ref_display_seq,ex,ey,expected_gray,red);
                if (point == 419999) begin
                    raster_frames++;
                    $display("VGA_PROGRESS time=%0t rasters=%0d completed=%0d displayed=%0d",$time,raster_frames,completed_total,displayed_frames);
                end
            end
        end
    end

    task automatic send_pixels(input int count, gap, seq);
        int index;
        for (index = 0; index < count; index++) begin
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
    task automatic cancel(input bit white);
        @(negedge clk_sys);
        source_abort = 1; blank_assert = white; source_valid = 1;
        @(negedge clk_sys);
        source_abort = 0; blank_assert = 0; source_valid = 0; source_start = 0;
    endtask
    task automatic lcd_reset_skew;
        // Both resets share one owner. Keep the pixel clock stopped so only
        // the system reset releases; never reset an active mailbox end alone.
        pixel_running = 0;
        #7; board_reset_n = 1;
        wait (!pll_areset); #13; pll_locked = 1;
        wait (!reset_sys);
        if (!reset_pix) $fatal(1, "LCD_RESET_SKEW: pixel reset escaped stopped clock");
        @(negedge clk_sys); blank_assert = 1;
        @(negedge clk_sys); blank_assert = 0;
        send_pixels(23040, 1, 0);
        if (discard_count !== 64'd1 || !ref_blank_requested || dut.pending !== 1'b0)
            $fatal(1, "LCD_RESET_SKEW: unavailable peer acceptance");
        @(negedge clk_sys); core_reset = 1; source_epoch = 1;
        @(negedge clk_sys); core_reset = 0;
        pixel_running = 1;
        wait (!reset_pix);
        wait (video_y == 30 && video_x == 100);
        repeat (10) @(negedge clk_pix);
        if (!ref_blank_active || display_valid || {red, green, blue} !== 12'hfff)
            $fatal(1, "LCD_RESET_SKEW: retained white not visible");
        // A genuine shared lock loss masks white asynchronously, even stopped.
        @(negedge clk_pix); pixel_running = 0;
        #7; pll_locked = 0;
        #1;
        if (!reset_sys || !reset_pix || {red, green, blue} !== 12'h000)
            $fatal(1, "LCD_RESET_SKEW: global mask");
        repeat (4) @(negedge clk_sys);
        if (ref_blank_requested) $fatal(1, "LCD_RESET_SKEW: global state clear");
        $display("PASS VGA LCD shared-reset release-skew stopped-pixel retained-white global-mask");
        $finish;
    endtask
    task automatic lcd_scenario;
        // Abort wins even at a first pixel and the would-be last completion.
        source_start = 1;
        cancel(0);
        send_pixels(23039, 1, 0);
        cancel(0);
        send_pixels(23040, 1, 0);
        wait (display_valid);
        wait (video_y == 30 && video_x == 100);
        cancel(1);
        repeat (8) @(negedge clk_pix);
        if ($test$plusargs("blank_corrupt")) force dut.red = 4'h0;
        repeat (10) @(negedge clk_pix);
        if (!ref_blank_active) $fatal(1, "LCD_COVERAGE: active blank");
        // Core reset retains requested white and source sequence restarts.
        @(negedge clk_sys); core_reset = 1; source_epoch = 1;
        @(negedge clk_sys); core_reset = 0;
        source_display_eligible = 0;
        send_pixels(23040, 1, 0);
        wait (display_epoch == 1);
        repeat (8) @(negedge clk_sys);
        if (!ref_blank_requested) $fatal(1, "LCD_COVERAGE: startup released blank");
        source_display_eligible = 1;
        send_pixels(23040, 1, 1);
        // A newer disable invalidates this already offered eligible frame.
        cancel(1);
        @(negedge clk_pix); pixel_running = 0;
        repeat (100) @(negedge clk_sys);
        pixel_running = 1;
        wait (display_sequence == 1 && display_epoch == 1);
        repeat (8) @(negedge clk_sys);
        if (!ref_blank_requested) $fatal(1, "LCD_COVERAGE: stale offer released blank");
        send_pixels(23040, 1, 2);
        wait (display_sequence == 2 && display_epoch == 1);
        wait (!ref_blank_active);
        repeat (420000) @(negedge clk_pix);
        // Reassert and receive white BEFORE offering: old requested/seen levels
        // are both1, so the later invalidation gate alone prevents requalification.
        cancel(1);
        repeat (8) @(negedge clk_pix);
        repeat (8) @(negedge clk_sys);
        // Match old ack, new completion and a fresh blank invalidation exactly.
        send_pixels(23040, 1, 3);
        send_pixels(23039, 1, 4);
        wait (ref_returning);
        wait (ref_sys_edges == ref_return_edge - 1);
        @(negedge clk_sys);
        source_valid = 1; source_start = 0; blank_assert = 1;
        source_shade = pattern(1, 4, 23039); source_dot++;
        @(negedge clk_sys); source_valid = 0; blank_assert = 0;
        repeat (840000) @(negedge clk_pix);
        // Include visible scanout after the new offer's later acknowledgement.
        repeat (420000) @(negedge clk_pix);
        if (!ref_blank_requested || ref_release || abort_total != 5
            || blank_releases != 1 || ack_completion_coincidences != 1)
            $fatal(1, "LCD_COVERAGE: abort=%0d release=%0d coincidence=%0d",
                abort_total, blank_releases, ack_completion_coincidences);
        $display("PASS VGA LCD abort blank stale-offer core-reset stopped-pixel ack-completion-invalidation");
        $finish;
    endtask
    initial begin
        int seq;
        clk_sys = 0;
        clk_pix = 0;
        pixel_running = 1;
        pixel_phase = 0;
        board_reset_n = 0;
        pll_locked = 0;
        core_reset = 0;
        source_valid = 0;
        source_start = 0;
        source_abort = 0; blank_assert = 0; source_display_eligible = 1;
        source_shade = 0;
        source_epoch = 0;
        source_dot = 0;
        observed_pixel = 0;
        observed_seq = 0;
        completed_total = 0;
        raster_frames = 0;
        displayed_frames = 0;
        source_edges = 0;
        pix_edges = 0;
        seen_banks = 0;
        have_previous_display = 0;
        ref_sys_edges = 0;
        ref_pix_edges = 0;
        ref_ready_samples = 0;
        ref_index = 0;
        ref_source_seq = 0;
        ref_writer = 0;
        ref_old_display = 1;
        ref_free = 2;
        ref_offer_bank = 0;
        ref_offer_seq = 0;
        ref_offer_epoch = 0;
        ref_capture_edge = 0;
        ref_return_edge = 0;
        ref_display_bank = 1;
        ref_display_seq = 0;
        ref_display_epoch = 0;
        ref_discards = 0;
        ref_repeats = 0;
        ref_pending = 0;
        ref_returning = 0;
        ref_captured = 0;
        ref_display_valid = 0;
        ref_raster_point = 0;
        ack_completion_coincidences = 0;
        ref_blank_requested = 0; ref_blank_active = 0; ref_release = 0;
        abort_total = 0; blank_cycles = 0; blank_releases = 0;
        mutation_reuse = $test$plusargs("bank_reuse");
        mutation_swap = $test$plusargs("active_swap");
        mutation_latency = $test$plusargs("read_latency");
        pixel_trace = $fopen("vga-pixels.csv", "w");
        if (!pixel_trace) $fatal(1, "VGA_PIXEL_TRACE_OPEN");
        $fdisplay(pixel_trace,"time,epoch,sequence,x,y,expected,actual");
        $dumpfile("waves/vga.vcd");
        $dumpvars(0, clk_sys, clk_pix, reset_sys, reset_pix, core_reset,
                     source_valid, source_start, source_shade, observe_valid,
                     observe_index, observe_shade, observe_complete, display_valid,
                     display_epoch, display_sequence, video_x, video_y, video_valid,
                     video_image, red, green, blue, hsync_n, vsync_n);
        if ($test$plusargs("lcd_reset")) lcd_reset_skew();
        startup();
        if ($test$plusargs("lcd")) lcd_scenario();
        for (seq = 0; seq < 8; seq++) send_pixels(23040, 1, seq);
        wait (display_valid);
        if (mutation_latency) begin
            @(negedge clk_pix);
            force dut.read_shade = late_shade;
            wait (video_image);
            repeat (3200) @(negedge clk_pix);
            $fatal(1, "MUTATION_MISSED: read latency");
        end
        if (mutation_reuse) begin
            @(negedge clk_sys);
            force dut.writer_bank = dut.display_bank;
            send_pixels(10, 1, 8);
            $fatal(1, "MUTATION_MISSED: bank reuse");
        end
        if (mutation_swap) begin
            wait (video_y == 10 && video_x == 100);
            @(negedge clk_pix);
            // Choose the non-writer alternative so the intended swap assertion
            // wins without also injecting a cross-domain ownership violation.
            mutation_bank = 2'(3 - int'(dut.display_bank) - int'(dut.writer_bank));
            force dut.display_bank = mutation_bank;
            repeat (5) @(negedge clk_pix);
            $fatal(1, "MUTATION_MISSED: active swap");
        end
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
        for (seq = 0; seq < 3; seq++) send_pixels(23040, 1, seq);
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
        $fclose(pixel_trace);
        $display("PASS vga every-pixel observer ownership fast slow pause core-reset lockloss stopped-pixel");
        $finish;
    end
    // Keep useful reset and first-image wave windows without dumping millions
    // of vendor-internal edges. Every pixel remains checked by the same oracle.
    initial begin
        #1;
        repeat (128) @(negedge clk_sys);
        $dumpoff;
        wait (video_image);
        $dumpon;
        repeat (1600) @(negedge clk_pix);
        $dumpoff;
    end
    initial begin #250000000; $fatal(1, "VGA_WATCHDOG"); end
endmodule
