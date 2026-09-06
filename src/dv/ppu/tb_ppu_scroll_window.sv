`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Original scene and coordinate oracle. No expected value uses DUT fetch,
// position, mode, line counters or window state.
module tb_ppu_scroll_window;
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
    logic case_done, wy_case, wy_late, wx166_case, wx0_case, disabled_wx_case;
    integer disabled_pixels;
    integer fine7_distinct;
    integer current_scx, current_wx, write_line, expected_window_row;
    integer window_lines, background_lines;
    logic [7:0] vram [0:8191];
    logic [7:0] oam [0:159];
    integer frame_count, pixel_count, trace_file;
    integer t, x, y, p, n;
    logic [7:0] lo, hi;
    logic [1:0] color, expected;
    n2m_timebase timebase (.*);
    n2m_ppu dut (.*);
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


    function automatic integer line_scx(input integer row);
        line_scx = wy_case || wx166_case || disabled_wx_case ? 0 : row % 8;
    endfunction
    function automatic integer line_wx(input integer row);
        if (disabled_wx_case) line_wx = row >= 33 ? 47 : 255;
        else if (wx0_case) line_wx = 0;
        else if (wx166_case) line_wx = row == 32 || row == 33 ? 166 : 255;
        else if (wy_case) line_wx = 47;
        else case (row % 16)
            8: line_wx = 7;
            9: line_wx = 8;
            10: line_wx = 15;
            11: line_wx = 47;
            12: line_wx = 80;
            13: line_wx = 159;
            14: line_wx = 167;
            default: line_wx = 255;
        endcase
    endfunction
    function automatic integer window_row_before(input integer row);
        integer r, count;
        begin
            count = 0;
            for (r = 0; r < row; r = r + 1)
                if (line_wx(r) < 167) count = count + 1;
            window_row_before = wy_case ? (row <= 33 ? row - 32 : row - 33) : count;
        end
    endfunction
    function automatic integer wx0_offset(input integer fine);
        case (fine)
            0: wx0_offset = 7;
            1: wx0_offset = 9;
            2: wx0_offset = 10;
            3: wx0_offset = 11;
            4: wx0_offset = 12;
            5: wx0_offset = 13;
            default: wx0_offset = 14;
        endcase
    endfunction
    function automatic integer map_tile(input integer tx, input integer ty, input logic win);
        map_tile = win ? (7 * ty + 11 * tx + 91) % 256 : (5 * ty + 3 * tx + 17) % 256;
    endfunction
    function automatic logic [1:0] pattern(input integer tile, input integer px, input integer py);
        pattern = 2'((tile >> (px % 6)) + px + 3 * py + (tile >> 5) + (py >> 2) * (px + 1));
    endfunction
    function automatic logic [1:0] scene(input integer px, input integer py);
        integer sx, sy, tile;
        logic win;
        begin
            win = (wy_case ? !wy_late && py >= 32 && py != 34 : line_wx(py) < 167)
                && px >= line_wx(py) - 7;
            sx = win ? px - (line_wx(py) - 7) : (px + line_scx(py)) % 256;
            sy = win ? window_row_before(py) : (py + 11) % 256;
            // Selected WX166 carry: trigger line32 remains BG; next two
            // lines start at window column8, rows1/2, even after WX255 on34.
            if (wx166_case) begin
                win = py == 33 || py == 34;
                sx = win ? px + 8 : px;
                sy = win ? py - 32 : (py + 11) % 256;
            end
            if (wx0_case) begin
                win = 1;
                sx = px + wx0_offset(py % 8);
                sy = py;
            end
            if (disabled_wx_case) begin
                win = 0;
                sx = py >= 33 && px > 40 ? px - 1 : px;
                sy = (py + 11) % 256;
            end
            tile = map_tile(sx / 8, sy / 8, win);
            scene = disabled_wx_case && py >= 33 && px == 40
                ? 2'd0 : pattern(tile, sx % 8, sy % 8);
        end
    endfunction
    task automatic write_register(input logic [15:0] address, input logic [7:0] value);
        @(negedge clk_sys);
        io_address = address; io_wdata = value; write_pending = 1;
        do @(posedge clk_sys); while (!(gb_tick && cpu_phase == 3));
        @(negedge clk_sys);
        write_pending = 0;
    endtask
    always #10 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        if (!reset_sys && source_valid) begin
            if (gb_tick || source_abort || fault) $fatal(1, "PPU_SCROLL_FORWARD");
            if (source_x !== 8'(pixel_count % 160) || source_y !== 8'(pixel_count / 160)
                || source_start !== (pixel_count == 0))
                $fatal(1, "PPU_SCROLL_ORDER frame=%0d index=%0d", frame_count, pixel_count);
            if (source_dot !== dot_before || source_dot <= previous_dot || source_epoch !== 32'd5)
                $fatal(1, "PPU_SCROLL_DOT");
            expected = frame_count == 0 ? 2'd0 : scene(pixel_count % 160, pixel_count / 160);
            if (source_shade !== expected)
                $fatal(1, "PPU_SCROLL_PIXEL frame=%0d index=%0d scx=%0d wx=%0d wrow=%0d expected=%0d actual=%0d",
                    frame_count, pixel_count, line_scx(pixel_count / 160), line_wx(pixel_count / 160),
                    window_row_before(pixel_count / 160), expected, source_shade);
            if (wx0_case && frame_count == 1 && pixel_count % 160 == 0
                && (pixel_count / 160) % 8 == 7
                && expected != pattern(map_tile(1, (pixel_count / 160) / 8, 1), 7, (pixel_count / 160) % 8))
                fine7_distinct = fine7_distinct + 1;
            if (disabled_wx_case && frame_count == 1 && pixel_count / 160 >= 33
                && pixel_count % 160 == 40) disabled_pixels = disabled_pixels + 1;
            if (source_display_eligible !== (frame_count != 0)) $fatal(1, "PPU_SCROLL_ELIGIBILITY");
            $fdisplay(trace_file, "%0d,%0d,%0d,%0d,%0d", frame_count, pixel_count, source_dot, expected, source_shade);
            previous_dot = source_dot;
            if (pixel_count == 23039) begin
                frame_count = frame_count + 1; pixel_count = 0;
                if (frame_count == 2) begin
                    $fclose(trace_file);
                    if (disabled_wx_case) begin
                        if (disabled_pixels != 111) $fatal(1, "PPU_DISABLED_WX_COUNT");
                        $display("PASS PPU disabled WX match inserted zero pixels=111 frame_pixels=46080");
                    end
                    else if (wx0_case) begin
                        if (fine7_distinct != 14) $fatal(1, "PPU_WX0_ORACLE_INSENSITIVE");
                        $display("PASS PPU WX0 static fine=8 pixels=46080 distinct14vs15=%0d", fine7_distinct);
                    end
                    else if (wx166_case) $display("PASS PPU WX166 retained carry rows1/2 column8 pixels=46080");
                    else if (wy_case) $display("PASS PPU WY qualified equality retained eligibility hidden row pixels=46080 late=%0d", wy_late);
                    else $display("PASS PPU scroll/window static pixels=46080 fine=8 wx=8");
                    case_done = 1;
                    $finish;
                end
            end else pixel_count = pixel_count + 1;
        end
    end
    initial begin
        $dumpfile("waves/scroll-window.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, dot_before,
            io_commit, io_address, io_wdata, source_valid, source_start,
            source_abort, source_x, source_y, source_shade, source_dot,
            source_display_eligible, frame_count, pixel_count, expected);
        clk_sys = 0; reset_sys = 1; core_reset = 0; pause_request = 0;
        epoch = 5; write_pending = 0; io_write = 1; io_address = 0; io_wdata = 0;
        disabled_wx_case = $test$plusargs("disabled_wx"); disabled_pixels = 0;
        wx166_case = $test$plusargs("wx166"); wx0_case = $test$plusargs("wx0"); fine7_distinct = 0;
        wy_case = $test$plusargs("wy"); wy_late = $test$plusargs("wy_late");
        dma_active = 0; frame_count = 0; pixel_count = 0; previous_dot = 0; case_done = 0;
        trace_file = $fopen("scroll-window.csv", "w");
        if (!trace_file) $fatal(1, "PPU_SCROLL_TRACE");
        $fdisplay(trace_file, "frame,index,completed_dot,expected,actual");
        for (n = 0; n < 8192; n = n + 1) vram[n] = 0;
        for (n = 0; n < 160; n = n + 1) oam[n] = 0;
        for (t = 0; t < 256; t = t + 1) begin
            for (y = 0; y < 8; y = y + 1) begin
                lo = 0; hi = 0;
                for (x = 0; x < 8; x = x + 1) begin
                    color = pattern(t, x, y); lo[7-x] = color[0]; hi[7-x] = color[1];
                end
                vram[16*t+2*y] = lo; vram[16*t+2*y+1] = hi;
            end
        end
        for (y = 0; y < 32; y = y + 1) begin
            for (x = 0; x < 32; x = x + 1) begin
                vram['h1800+32*y+x] = 8'(map_tile(x, y, 0));
                vram['h1c00+32*y+x] = 8'(map_tile(x, y, 1));
            end
        end
        repeat (4) @(negedge clk_sys);
        reset_sys = 0;
        write_register(16'hff43, 0); write_register(16'hff42, 11);
        write_register(16'hff47, 8'he4); write_register(16'hff4a, wy_case || wx166_case || disabled_wx_case ? 32 : 0);
        write_register(16'hff4b, wx0_case ? 0 : wy_case ? 47 : 255);
        write_register(16'hff40, wy_case ? 8'hd1 : 8'hf1);
        // Constant offscreen window during warm-up. The next frame's WY latch
        // starts afresh after VBlank; line0 uses the same prepared configuration.
        wait (frame_count == 1);
        if ($test$plusargs("scroll_corrupt")) begin
            @(negedge clk_sys);
            force dut.source_shade = 2'd0;
        end
        if (disabled_wx_case) begin
            // WY32 qualifies with Window enabled and WX offscreen. Hide on33
            // while retaining the match. Raw47 suppresses reload at count7;
            // raw48/source40 emits raw0, then the retained tile is one pixel late.
            wait (pixel_count == 33 * 160);
            write_register(16'hff40, 8'hd1);
            write_register(16'hff4b, 47);
            if (pixel_count != 33 * 160) $fatal(1, "PPU_DISABLED_WX_LATE_SETUP");
            if ($test$plusargs("disabled_wx_corrupt")) begin
                wait (pixel_count == 33 * 160 + 40);
                @(negedge clk_sys);
                force dut.source_shade = 2'd3;
            end
        end else if (wx166_case) begin
            wait (pixel_count == 32 * 160);
            write_register(16'hff4b, 166);
            if (pixel_count != 32 * 160) $fatal(1, "PPU_WX166_LATE_START");
            wait (pixel_count == 34 * 160);
            write_register(16'hff4b, 255);
            if (pixel_count != 34 * 160) $fatal(1, "PPU_WX166_LATE_HIDE");
        end else if (wy_case) begin
            // Enabling during LY32 qualifies equality on the next quarter0,
            // well before WX47. Enabling after LY32 has ended cannot qualify.
            wait (pixel_count == (wy_late ? 33 : 32) * 160 + 16);
            write_register(16'hff40, 8'hf1);
            if (!wy_late) begin
                wait (pixel_count == 33 * 160);
                write_register(16'hff4a, 255);
                // Isolate hidden-row bookkeeping from the DMG disabled-window
                // WX-match reload glitch (pinned video.v844-851).
                wait (pixel_count == 34 * 160);
                write_register(16'hff40, 8'hd1);
                write_register(16'hff4b, 255);
                if (pixel_count != 34 * 160) $fatal(1, "PPU_WY_LATE_HIDE");
                wait (pixel_count == 35 * 160);
                write_register(16'hff4b, 47);
                write_register(16'hff40, 8'hf1);
                if (pixel_count != 35 * 160) $fatal(1, "PPU_WY_LATE_RESTORE");
            end
        end else for (write_line = 1; write_line < 144; write_line = write_line + 1) begin
            wait (pixel_count == write_line * 160);
            write_register(16'hff43, 8'(line_scx(write_line)));
            write_register(16'hff4b, 8'(line_wx(write_line)));
            // Two legal T4 writes must finish in the preceding line's HBlank.
            if (pixel_count != write_line * 160) $fatal(1, "PPU_SCROLL_LATE_SETUP line=%0d", write_line);
        end
    end
    initial begin
        #70000000;
        $fatal(1, "PPU_SCROLL_TIMEOUT");
    end
endmodule
