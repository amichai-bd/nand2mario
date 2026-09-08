`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Original scene and coordinate oracle. No expected value uses DUT fetch,
// position, mode, line counters or window state.
module tb_ppu_live_scroll;
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
    logic case_done, lcdc_cases, ref_lcd_on;
    integer case_index, first_pixels;
    logic [63:0] expected_first;
    logic [7:0] vram [0:8191];
    logic [7:0] oam [0:159];
    integer frame_count, pixel_count, trace_file;
    integer t, x, y, p, n;
    logic [7:0] lo, hi;
    logic [1:0] color, expected;
    n2m_timebase timebase (.*);
    n2m_ppu dut (.vram_cpu_read_allow(), .oam_cpu_read_allow(), .oam_late_future(), .oam_cpu_late_write(), .*);
    assign io_commit = write_pending && cpu_phase == 3 && gb_tick;
    `DFF_RST_EN(cpu_phase, cpu_phase + 2'd1, clk_sys, gb_tick, reset_sys || core_reset, 2'd0)
    `DFF_RST_EN(dot_before, dot_before + 64'd1, clk_sys, gb_tick, reset_sys || core_reset, 64'd0)
    `DFF_RST_EN(ref_lcd_on, io_wdata[7], clk_sys,
        io_commit && io_address == 16'hff40, reset_sys, 1'b0)
    // Response-valid refers to the prior request, never the fault-masked current
    // request. Returned bytes remain available before the later consuming dot.
    `DFF_RST(vram_valid, vram_request, clk_sys, reset_sys)
    `DFF_RST_EN(vram_data, vram[vram_address], clk_sys, vram_request, reset_sys, 8'd0)
    `DFF_RST(oam_valid, oam_phase != 0, clk_sys, reset_sys)
    `DFF_RST_EN(oam_data, {oam[{oam_pair_address, 1'b1}], oam[{oam_pair_address, 1'b0}]},
        clk_sys, oam_phase != 0, reset_sys, 16'd0)


    task automatic write_register(input logic [15:0] address, input logic [7:0] value);
        @(negedge clk_sys);
        io_address = address; io_wdata = value; write_pending = 1;
        do @(posedge clk_sys); while (!(gb_tick && cpu_phase == 3));
        @(negedge clk_sys);
        write_pending = 0;
    endtask
    task automatic write_at(input integer elapsed);
        @(negedge clk_sys);
        case (case_index)
            0: begin io_address = 16'hff42; io_wdata = 1; end
            1: begin io_address = 16'hff43; io_wdata = 8; end
            2: begin io_address = 16'hff40; io_wdata = 8'h99; end
            3: begin io_address = 16'hff40; io_wdata = 8'h81; end
        endcase
        do @(negedge clk_sys); while (!(gb_tick && dot_before == enable_dot + 64'(elapsed)));
        if (cpu_phase != 3) $fatal(1, "PPU_LIVE_SCROLL_ILLEGAL_WRITE");
        write_pending = 1;
        @(posedge clk_sys);
        @(negedge clk_sys);
        write_pending = 0;
    endtask
    always #10 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        if (io_commit && io_address == 16'hff40 && io_wdata[7] && !ref_lcd_on) enable_dot = dot_before;
        if (!reset_sys && source_valid && !case_done) begin
            if (gb_tick || source_abort || fault) $fatal(1, "PPU_LIVE_SCROLL_FORWARD");
            if (source_x !== 8'(pixel_count % 160) || source_y !== 8'(pixel_count / 160)
                || source_start !== (pixel_count == 0))
                $fatal(1, "PPU_LIVE_SCROLL_ORDER case=%0d frame=%0d index=%0d", case_index, frame_count, pixel_count);
            if (source_dot !== dot_before || source_dot <= previous_dot || source_epoch !== 32'd5)
                $fatal(1, "PPU_LIVE_SCROLL_DOT");
            expected = 0;
            if (frame_count == 1) begin
                if (case_index == 0 || case_index == 3)
                    expected = pixel_count < 8 ? (pixel_count % 2 == 0 ? 2'd3 : 2'd0)
                        : (pixel_count % 2 == 0 ? 2'd2 : 2'd1);
                else if (case_index == 1) expected = pixel_count < 8 ? 2'd0 : 2'(((pixel_count + 8) / 8) % 4);
                else expected = pixel_count < 8 ? 2'd0 : 2'((pixel_count / 8 + 2) % 4);
            end
            if (frame_count == 1 && pixel_count == 0) begin
                expected_first = enable_dot + 64'd70317;
                if (source_dot !== expected_first)
                    $fatal(1, "PPU_LIVE_SCROLL_FIRST case=%0d expected=%0d actual=%0d", case_index, expected_first, source_dot);
                first_pixels = first_pixels + 1;
            end
            if (source_shade !== expected)
                $fatal(1, "PPU_LIVE_SCROLL_PIXEL case=%0d frame=%0d index=%0d expected=%0d actual=%0d",
                    case_index, frame_count, pixel_count, expected, source_shade);
            if (source_display_eligible !== (frame_count != 0)) $fatal(1, "PPU_LIVE_SCROLL_ELIGIBILITY");
            $fdisplay(trace_file, "%0d,%0d,%0d,%0d,%0d,%0d", case_index, frame_count, pixel_count, source_dot, expected, source_shade);
            previous_dot = source_dot;
            if (frame_count == 1 && pixel_count == 159) case_done = 1;
            else if (pixel_count == 23039) begin frame_count = frame_count + 1; pixel_count = 0; end
            else pixel_count = pixel_count + 1;
        end
    end
    initial begin
        $dumpfile("waves/live-scroll.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, dot_before,
            io_commit, io_address, io_wdata, vram_request, vram_address,
            vram_valid, vram_data, source_valid, source_x, source_y,
            source_shade, source_dot, frame_count, pixel_count, expected);
        clk_sys = 0; reset_sys = 1; core_reset = 0; pause_request = 0;
        epoch = 5; write_pending = 0; io_write = 1; io_address = 0; io_wdata = 0;
        dma_active = 0; frame_count = 0; pixel_count = 0; previous_dot = 0; case_done = 0;
        first_pixels = 0; enable_dot = 0; lcdc_cases = $test$plusargs("lcdc_fetch");
        trace_file = $fopen("live-scroll.csv", "w");
        if (!trace_file) $fatal(1, "PPU_LIVE_SCROLL_TRACE");
        $fdisplay(trace_file, "case,frame,index,completed_dot,expected,actual");
        for (n = 0; n < 8192; n = n + 1) vram[n] = 0;
        for (n = 0; n < 160; n = n + 1) oam[n] = 0;
        for (case_index = lcdc_cases ? 2 : 0; case_index < (lcdc_cases ? 4 : 2); case_index = case_index + 1) begin
            // Original literals: SCY crosses independently fetched planes;
            // SCX crosses a captured map tile and later live map selection.
            for (n = 0; n < 8192; n = n + 1) vram[n] = 0;
            if (case_index == 0) begin
                vram[0] = 8'haa; vram[1] = 8'h55;
                vram[2] = 8'h55; vram[3] = 8'haa;
            end else if (case_index == 3) begin
                vram[0] = 8'haa; vram[1] = 8'h55;
                vram['h1000] = 8'h55; vram['h1001] = 8'haa;
            end else begin
                for (t = 0; t < 4; t = t + 1)
                    for (y = 0; y < 8; y = y + 1) begin
                        vram[t*16+y*2] = t % 2 != 0 ? 8'hff : 8'h00;
                        vram[t*16+y*2+1] = t >= 2 ? 8'hff : 8'h00;
                    end
                for (n = 0; n < 1024; n = n + 1) begin
                    vram[6144+n] = 8'(n % 4);
                    vram[7168+n] = 8'((n+2) % 4);
                end
            end
            reset_sys = 1;
            repeat (4) @(negedge clk_sys);
            frame_count = 0; pixel_count = 0; previous_dot = 0; case_done = 0;
            reset_sys = 0;
            write_register(16'hff43, 0); write_register(16'hff42, 0);
            write_register(16'hff47, 8'he4); write_register(16'hff4b, 255);
            write_register(16'hff40, 8'h91);
            // Selected source trace: second map starts70308/captures70309,
            // low70311, high70313. Legal T4 write lies between plane captures.
            write_at(70312);
            if ($test$plusargs("live_scroll_corrupt") && case_index == 0) begin
                @(negedge clk_sys);
                force dut.source_shade = 2'd0;
            end
            if ($test$plusargs("lcdc_fetch_corrupt") && case_index == 2) begin
                @(negedge clk_sys);
                force dut.source_shade = 2'd3;
            end
            wait (case_done);
            @(negedge clk_sys);
        end
        if (first_pixels != 2) $fatal(1, "PPU_LIVE_SCROLL_COUNT");
        $fclose(trace_file);
        if (lcdc_cases) $display("PASS PPU LCDC live map and tile-bank fetch cases=2 visible_pixels=320");
        else $display("PASS PPU live SCY planes and coarse SCX fetch cases=2 visible_pixels=320");
        $finish;
    end
    initial begin
        #100000000;
        $fatal(1, "PPU_LIVE_SCROLL_TIMEOUT");
    end
endmodule
