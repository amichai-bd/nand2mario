`timescale 1ns/1ps
module tb_clocking;
    logic clk_sys;
    logic clk_reference;
    logic clk_pix;
    logic pixel_running;
    logic board_reset_n;
    logic pll_locked;
    logic core_reset;
    logic pause_request;
    logic pll_areset, ready, reset_sys, reset_pix, gb_tick, paused;
    always #10 clk_reference = ~clk_reference;
    always #20 clk_sys = ~clk_sys;
    // Independent destination edges exercise reset control, not a vendor PLL model.
    always #19 if (pixel_running) clk_pix = ~clk_pix; else clk_pix = 0;
    n2m_reset_control u_reset (.clk_reference, .clk_sys, .clk_pix, .board_reset_n, .pll_locked,
                              .pll_areset, .ready, .reset_sys, .reset_pix);
    n2m_timebase u_tick (.clk_sys, .reset_sys, .core_reset, .pause_request, .gb_tick, .paused);
    logic [18:0] bad_sum;
    assign bad_sum = u_tick.phase + 19'd65537;
    bit corrupt_numerator, corrupt_drop, corrupt_reset;
    string mode;
    longint unsigned active_edges;
    longint unsigned seen_ticks;
    longint unsigned total_checked_edges;
    longint unsigned previous_tick;
    longint unsigned expected_ticks;
    bit expected_running;
    bit expected_carry;
    bit observed_carry;
    int gaps5, gaps6;

    // Cumulative integer arithmetic is independent of the DUT accumulator.
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) begin
            active_edges = 0;
            seen_ticks = 0;
            previous_tick = 0;
            expected_running = 0;
            if (gb_tick !== 0) $fatal(1, "TIMEBASE_RESET_TICK");
        end else begin
            expected_carry = expected_running &&
                (((active_edges + 1) * 65536 / 390625) != (active_edges * 65536 / 390625));
            observed_carry = gb_tick && !(corrupt_drop && active_edges == 5);
            if (expected_running) begin
                active_edges++;
                total_checked_edges++;
            end
            if (observed_carry) seen_ticks++;
            expected_ticks = active_edges * 65536 / 390625;
            if (observed_carry !== expected_carry || seen_ticks != expected_ticks) begin
                $dumpon;
                $fatal(1, "TIMEBASE_MISMATCH mode=%s edge=%0d expected=%0d actual=%0d", mode, active_edges, expected_ticks, seen_ticks);
            end
            if (expected_carry) begin
                if (previous_tick != 0) begin
                    if (active_edges - previous_tick == 5) gaps5++;
                    else if (active_edges - previous_tick == 6) gaps6++;
                    else $fatal(1, "TIMEBASE_GAP");
                end
                previous_tick = active_edges;
                // ceil(tick * denominator / numerator) is the independent jitter bound.
                if (active_edges != (seen_ticks * 390625 + 65535) / 65536)
                    $fatal(1, "TIMEBASE_JITTER");
            end
            if (!expected_running && !pause_request) expected_running = 1;
            else if (expected_running && pause_request && expected_carry) expected_running = 0;
            #1;
            if (paused !== !expected_running) $fatal(1, "TIMEBASE_PAUSE_ACK");
        end
    end

    task automatic step;
        @(posedge clk_sys); #2;
    endtask
    task automatic reset_asserted;
        if (pll_areset !== 1 || ready !== 0 || reset_sys !== 1 || reset_pix !== 1)
            $fatal(1, "RESET_MISMATCH mode=%s expected=asserted", mode);
    endtask
    task automatic qualify_board(input int remaining);
        int i;
        for (i = 1; i < remaining; i++) begin
            @(posedge clk_reference); #2;
            if (i == 32) $dumpoff;
            if (i == remaining - 32) $dumpon;
            reset_asserted;
        end
        @(posedge clk_reference); #2;
        if (pll_areset !== 0 || ready !== 0 || reset_sys !== 1 || reset_pix !== 1)
            $fatal(1, "RESET_QUALIFICATION_EDGE");
    endtask
    task automatic qualify_lock;
        int i;
        for (i = 1; i <= 1025; i++) begin
            step;
            if (ready !== 0 || reset_sys !== 1 || reset_pix !== 1)
                $fatal(1, "RESET_LOCK_EARLY edge=%0d", i);
        end
        step;
        if (ready !== 1 || reset_sys !== 1 || reset_pix !== 1)
            $fatal(1, "RESET_LOCK_EDGE");
        step;
        if (reset_sys !== 1) $fatal(1, "RESET_SYS_EARLY");
        step;
        if (reset_sys !== 0) $fatal(1, "RESET_SYS_LATE");
    endtask

    initial begin
        clk_sys = 0;
        clk_reference = 0;
        clk_pix = 0;
        pixel_running = 0;
        board_reset_n = 1;
        pll_locked = 0;
        core_reset = 0;
        pause_request = 1;
        mode = "normal";
        active_edges = 0;
        seen_ticks = 0;
        total_checked_edges = 0;
        previous_tick = 0;
        expected_running = 0;
        gaps5 = 0;
        gaps6 = 0;
        $dumpfile("clocking.vcd"); $dumpvars(0, tb_clocking);
        corrupt_numerator = $test$plusargs("bad_numerator");
        corrupt_drop = $test$plusargs("drop_tick");
        corrupt_reset = $test$plusargs("early_reset");
        if (corrupt_numerator) begin mode = "numerator"; force u_tick.sum = bad_sum; end
        if (corrupt_drop) mode = "drop";
        if (corrupt_reset) begin mode = "early-reset"; force reset_pix = 1'b0; end
        #2; reset_asserted;
        // Configuration startup works without pressing the button, with no pixel clock.
        qualify_board(500002);
        repeat (8) step;
        if (ready !== 0) $fatal(1, "RESET_LOCK_REQUIRED");
        @(negedge clk_sys); #3; pll_locked = 1;
        qualify_lock;
        if (reset_pix !== 1) $fatal(1, "RESET_STOPPED_PIXEL");
        pixel_running = 1;
        @(posedge clk_pix); #1;
        if (reset_pix !== 1) $fatal(1, "RESET_PIX_EARLY");
        @(posedge clk_pix); #1;
        if (reset_pix !== 0) $fatal(1, "RESET_PIX_LATE");
        @(negedge clk_sys); pause_request = 0;
        repeat (800) step;
        $dumpoff;
        repeat (780500) step;
        $dumpon;
        repeat (200) step;
        if (active_edges < 781250 || seen_ticks < 65536 || gaps5 == 0 || gaps6 == 0)
            $fatal(1, "TIMEBASE_PERIOD_COVERAGE");
        // Pause requested between dots completes the current dot before acknowledging.
        @(negedge clk_sys); pause_request = 1;
        repeat (20) step;
        if (!paused) $fatal(1, "TIMEBASE_PAUSE_TIMEOUT");
        repeat (50) step;
        @(negedge clk_sys); pause_request = 0;
        repeat (100) step;
        @(negedge clk_sys); core_reset = 1; pause_request = 1;
        step;
        if (!paused || gb_tick || reset_pix || pll_areset || !ready)
            $fatal(1, "TIMEBASE_CORE_RESET_BOUNDARY");
        @(negedge clk_sys); core_reset = 0; pause_request = 0;
        repeat (100) step;
        // Losing raw lock asserts both resets between clock edges, without resetting PLL.
        @(negedge clk_sys); #3; pll_locked = 0; #1;
        if (ready || !reset_sys || !reset_pix || pll_areset) $fatal(1, "RESET_RAW_LOCK_LOSS");
        pixel_running = 0;
        @(negedge clk_sys); #7; pll_locked = 1;
        qualify_lock;
        if (!reset_pix) $fatal(1, "RESET_STOPPED_RELOCK");
        pixel_running = 1;
        repeat (3) @(posedge clk_pix);
        #2; if (reset_pix) $fatal(1, "RESET_RESTART_PIXEL");
        // A stopped pixel clock with lock retained does not invent a reset or detector.
        pixel_running = 0; repeat (10) step;
        if (reset_pix || reset_sys || !ready) $fatal(1, "RESET_FALSE_CLOCK_DETECTOR");
        @(negedge clk_sys); #5; board_reset_n = 0; #1; reset_asserted;
        @(negedge clk_sys); #3; board_reset_n = 1;
        repeat (100) step;
        @(negedge clk_sys); #7; board_reset_n = 0; #1; reset_asserted;
        @(negedge clk_sys); #1; board_reset_n = 1;
        qualify_board(500002);
        if (total_checked_edges < 781450) $fatal(1, "TIMEBASE_TOTAL_COVERAGE");
        $display("PASS clocking startup qualification lockloss pause core-reset periods jitter stopped-pixel");
        $finish;
    end
    initial begin #100000000; $fatal(1, "CLOCKING_WATCHDOG"); end
endmodule
