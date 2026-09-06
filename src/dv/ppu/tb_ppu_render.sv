`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Original scene and coordinate oracle. No expected value uses DUT fetch,
// position, mode, line counters or window state.
module tb_ppu_render;
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
    logic temporal;
    integer startup_reads;
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

    function automatic logic [1:0] pattern(input integer tile, input integer px, input integer py);
        pattern = 2'((tile >> (px % 6)) + px + 3 * py + (tile >> 5));
    endfunction
    function automatic integer map_tile(input integer tx, input integer ty, input logic win);
        map_tile = win ? (7 * ty + 11 * tx + 91) % 256 : (5 * ty + 3 * tx + 17) % 256;
    endfunction
    function automatic logic [1:0] scene(input integer px, input integer py);
        integer sx, sy, tile, raw_bg, raw_obj, chosen, best_x, ox, oy, row, col;
        integer i, attr;
        logic win;
        begin
            win = py >= 32 && px >= 40;
            sx = win ? px - 40 : (px + 5) % 256;
            sy = win ? py - 32 : (py + 11) % 256;
            tile = map_tile(sx / 8, sy / 8, win);
            raw_bg = int'(pattern(tile, sx % 8, sy % 8));
            chosen = -1;
            raw_obj = 0;
            best_x = 1000;
            // Five explicitly placed objects, all within the ten-object limit.
            // Selection is per-pixel X/OAM priority, independently of DUT slots.
            for (i = 0; i < 5; i = i + 1) begin
                ox = int'(oam[4*i+1]) - 8;
                oy = int'(oam[4*i]) - 16;
                attr = int'(oam[4*i+3]);
                if (px >= ox && px < ox + 8 && py >= oy && py < oy + 16) begin
                    row = py - oy;
                    col = px - ox;
                    if (attr & 64) row = 15 - row;
                    if (attr & 32) col = 7 - col;
                    tile = (int'(oam[4*i+2]) & 254) + row / 8;
                    if (pattern(tile, col, row % 8) != 0 && ox < best_x) begin
                        chosen = i;
                        best_x = ox;
                        raw_obj = int'(pattern(tile, col, row % 8));
                    end
                end
            end
            scene = 2'(raw_bg);
            if (chosen >= 0) begin
                attr = int'(oam[4*chosen+3]);
                if (!(attr & 128) || raw_bg == 0)
                    scene = (attr & 16) ? 2'(3 - raw_obj) : 2'(raw_obj);
            end
        end
    endfunction
    task automatic write_register(input logic [15:0] address, input logic [7:0] value);
        @(negedge clk_sys);
        io_address = address;
        io_wdata = value;
        write_pending = 1;
        do @(posedge clk_sys); while (!(gb_tick && cpu_phase == 3));
        @(negedge clk_sys);
        write_pending = 0;
    endtask
    task automatic startup_read(input integer elapsed, input logic [15:0] address,
        input logic [7:0] mask, input logic [7:0] value);
        @(negedge clk_sys);
        io_address = address;
        io_write = 0;
        do @(posedge clk_sys); while (!(gb_tick && dot_before == enable_dot + 64'(elapsed)));
        if ((io_rdata & mask) !== value)
            $fatal(1, "PPU_RENDER_STARTUP elapsed=%0d address=%h expected=%h actual=%h",
                elapsed, address, value, io_rdata & mask);
        startup_reads = startup_reads + 1;
        @(negedge clk_sys);
    endtask
    always @(posedge clk_sys) begin
        if (io_commit && io_address == 16'hff40 && io_wdata[7]) enable_dot = dot_before;
    end
    always #10 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        if (!reset_sys && source_valid) begin
            if (gb_tick || source_abort || fault) $fatal(1, "PPU_RENDER_FORWARD_PHASE");
            if (source_x !== 8'(pixel_count % 160) || source_y !== 8'(pixel_count / 160)
                || source_start !== (pixel_count == 0))
                $fatal(1, "PPU_RENDER_ORDER frame=%0d index=%0d xy=%0d,%0d",
                    frame_count, pixel_count, source_x, source_y);
            if (source_dot !== dot_before || source_dot <= previous_dot || source_epoch !== 32'd5)
                $fatal(1, "PPU_RENDER_TIMESTAMP frame=%0d index=%0d", frame_count, pixel_count);
            if (temporal && pixel_count == 0 && frame_count == 1) normal_first_dot = source_dot;
            if (temporal && pixel_count == 0 && frame_count == 2
                && source_dot - normal_first_dot != 64'd70224)
                $fatal(1, "PPU_RENDER_PERIOD expected=70224 actual=%0d", source_dot - normal_first_dot);
            expected = frame_count == 0 ? 2'd0 : scene(pixel_count % 160, pixel_count / 160);
            if (source_shade !== expected)
                $fatal(1, "PPU_RENDER_PIXEL frame=%0d index=%0d expected=%0d actual=%0d",
                    frame_count, pixel_count, expected, source_shade);
            if (source_display_eligible !== (frame_count != 0)) $fatal(1, "PPU_RENDER_ELIGIBILITY");
            $fdisplay(trace_file, "%0d,%0d,%0d,%0d,%0d", frame_count, pixel_count,
                source_dot, expected, source_shade);
            previous_dot = source_dot;
            if (pixel_count == 23039) begin
                frame_count = frame_count + 1;
                pixel_count = 0;
                if (frame_count == (temporal ? 3 : 2)) begin
                    $fclose(trace_file);
                    if (temporal) begin
                        if (startup_reads != 4) $fatal(1, "PPU_RENDER_STARTUP_COUNT");
                        $display("PASS PPU renderer temporal frames=3 pixels=69120 startup_reads=4 period=70224");
                    end else $display("PASS PPU renderer original_scene frames=2 pixels=46080");
                    $finish;
                end
            end else pixel_count = pixel_count + 1;
        end
    end
    initial begin
        $dumpfile("waves/renderer.vcd");
        $dumpvars(0, dut);
        clk_sys = 0;
        reset_sys = 1;
        core_reset = 0;
        pause_request = 0;
        epoch = 5;
        write_pending = 0;
        io_write = 1;
        io_address = 0;
        io_wdata = 0;
        dma_active = 0;
        temporal = $test$plusargs("temporal");
        startup_reads = 0;
        enable_dot = 0;
        normal_first_dot = 0;
        frame_count = 0;
        pixel_count = 0;
        previous_dot = 0;
        trace_file = $fopen("source.csv", "w");
        if (!trace_file) $fatal(1, "PPU_RENDER_TRACE_OPEN");
        $fdisplay(trace_file, "frame,index,completed_dot,expected,actual");
        for (n = 0; n < 8192; n = n + 1) vram[n] = 0;
        for (n = 0; n < 160; n = n + 1) oam[n] = 0;
        for (t = 0; t < 384; t = t + 1) begin
            for (y = 0; y < 8; y = y + 1) begin
                lo = 0;
                hi = 0;
                for (x = 0; x < 8; x = x + 1) begin
                    color = pattern(t, x, y);
                    lo[7-x] = color[0];
                    hi[7-x] = color[1];
                end
                vram[16*t+2*y] = lo;
                vram[16*t+2*y+1] = hi;
            end
        end
        for (y = 0; y < 32; y = y + 1) begin
            for (x = 0; x < 32; x = x + 1) begin
                vram['h1800+32*y+x] = 8'(map_tile(x, y, 0));
                vram['h1c00+32*y+x] = 8'(map_tile(x, y, 1));
            end
        end
        oam[0]=48; oam[1]=28; oam[2]=31; oam[3]=0;
        oam[4]=48; oam[5]=28; oam[6]=40; oam[7]=16;
        oam[8]=56; oam[9]=72; oam[10]=42; oam[11]=224;
        oam[12]=100; oam[13]=1; oam[14]=48; oam[15]=32;
        oam[16]=18; oam[17]=167; oam[18]=50; oam[19]=0;
        repeat (4) @(negedge clk_sys);
        reset_sys = 0;
        write_register(16'hff43, 5);
        write_register(16'hff42, 11);
        write_register(16'hff47, 8'he4);
        write_register(16'hff48, 8'he4);
        write_register(16'hff49, 8'h1b);
        write_register(16'hff4a, 32);
        write_register(16'hff4b, 47);
        write_register(16'hff40, 8'hf7);
        if (temporal) begin
            if ($test$plusargs("timing_corrupt")) force dut.io_rdata = 8'h83;
            // Mooneye pinned lcdon_timing-GS brackets, relative to write T4:
            // LD A,(DE) read commits at 4*N+8, using old state at that edge.
            startup_read(76, 16'hff41, 8'h03, 0);
            startup_read(80, 16'hff41, 8'h03, 3);
            startup_read(448, 16'hff44, 8'hff, 0);
            startup_read(452, 16'hff44, 8'hff, 1);
        end
        if ($test$plusargs("corrupt")) begin
            wait (frame_count == 1);
            @(negedge clk_sys);
            force dut.source_shade = 2'd3;
        end
    end
    initial begin
        #70000000;
        $fatal(1, "PPU_RENDER_TIMEOUT frames=%0d pixels=%0d", frame_count, pixel_count);
    end
endmodule
