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
    logic temporal, simulation_done, rich_scene, dynamic_palette;
    logic object_zero;
    integer zero_lines;
    logic [63:0] zero_expected_dot;
    logic [7:0] ref_bgp, ref_obp0, ref_obp1, sampled_bgp, sampled_obp0, sampled_obp1;
    logic [7:0] sampled_new_palette, prior_palette [0:2];
    logic [63:0] sampled_dot, palette_write_dot [0:2];
    logic [1:0] sampled_write;
    logic [3:0] selected_pixel;
    logic [1:0] replacement_shade;
    integer commit_pixels [0:2];
    integer after_pixels [0:2];
    integer write_number, palette_index, coverage_index;
    integer startup_reads;
    logic [7:0] vram [0:8191];
    logic [7:0] oam [0:159];
    integer frame_count, pixel_count, trace_file;
    integer t, x, y, p, n;
    logic [7:0] lo, hi;
    logic [1:0] color, expected;
    n2m_timebase timebase (.*);
    n2m_ppu dut (.vram_cpu_read_allow(), .oam_cpu_read_allow(), .oam_late_future(), .oam_cpu_late_write(), .*,
        .lcdc_observe(), .stat_observe(), .ly_observe(), .lyc_observe(),
        .scy_observe(), .scx_observe(), .wy_observe(), .wx_observe(),
        .bgp_observe(), .obp0_observe(), .obp1_observe()
    );
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
        pattern = 2'((tile >> (px % 6)) + px + 3 * py + (tile >> 5)
            + (rich_scene ? (py >> 2) * (px + 1) : 0));
    endfunction
    function automatic integer map_tile(input integer tx, input integer ty, input logic win);
        map_tile = win ? (7 * ty + 11 * tx + 91) % 256 : (5 * ty + 3 * tx + 17) % 256;
    endfunction
    function automatic logic [3:0] scene_pick(input integer px, input integer py);
        integer sx, sy, tile, raw_bg, raw_obj, chosen, best_x, ox, oy, row, col;
        integer i, attr;
        logic win;
        begin
            win = py >= 32 && px >= 40;
            sx = win ? px - 40 : (px + 5) % 256;
            sy = win ? py - 32 : (py + 11) % 256;
            tile = map_tile(sx / 8, sy / 8, win);
            if (rich_scene && tile < 128) tile = tile + 256;
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
                if (px >= ox && px < ox + 8 && py >= oy && py < oy + (rich_scene ? 8 : 16)) begin
                    row = py - oy;
                    col = px - ox;
                    if (attr & 64) row = (rich_scene ? 7 : 15) - row;
                    if (attr & 32) col = 7 - col;
                    tile = rich_scene ? int'(oam[4*i+2]) : (int'(oam[4*i+2]) & 254) + row / 8;
                    if (pattern(tile, col, row % 8) != 0 && ox < best_x) begin
                        chosen = i;
                        best_x = ox;
                        raw_obj = int'(pattern(tile, col, row % 8));
                    end
                end
            end
            scene_pick = {2'd0, 2'(raw_bg)};
            if (chosen >= 0) begin
                attr = int'(oam[4*chosen+3]);
                if (!(attr & 128) || raw_bg == 0)
                    scene_pick = {(attr & 16) ? 2'd2 : 2'd1, 2'(raw_obj)};
            end
        end
    endfunction
    function automatic logic [1:0] palette_scene(input integer px, input integer py,
        input logic [7:0] bg, input logic [7:0] obj0, input logic [7:0] obj1);
        logic [3:0] pick;
        logic [7:0] selected_palette;
        begin
            pick = scene_pick(px, py);
            selected_palette = pick[3:2] == 0 ? bg : pick[3:2] == 1 ? obj0 : obj1;
            palette_scene = selected_palette[2 * pick[1:0] +: 2];
        end
    endfunction
    function automatic logic [1:0] scene(input integer px, input integer py);
        scene = palette_scene(px, py, 8'he4, 8'he4, 8'h1b);
    endfunction
    // Independent input history: sample old palettes before applying this A
    // edge's CPU write. The B observer must use the same completed-dot snapshot.
    always @(posedge clk_sys) begin
        if (reset_sys) begin
            ref_bgp = 0; ref_obp0 = 0; ref_obp1 = 0;
            sampled_bgp = 0; sampled_obp0 = 0; sampled_obp1 = 0;
            sampled_dot = 0; sampled_write = 3; sampled_new_palette = 0;
            for (palette_index = 0; palette_index < 3; palette_index = palette_index + 1) begin
                prior_palette[palette_index] = 0;
                palette_write_dot[palette_index] = 0;
            end
        end else if (gb_tick) begin
            sampled_dot = dot_before + 64'd1;
            sampled_bgp = sampled_dot == palette_write_dot[0] + 64'd1 ? prior_palette[0] | ref_bgp : ref_bgp;
            sampled_obp0 = sampled_dot == palette_write_dot[1] + 64'd1 ? prior_palette[1] | ref_obp0 : ref_obp0;
            sampled_obp1 = sampled_dot == palette_write_dot[2] + 64'd1 ? prior_palette[2] | ref_obp1 : ref_obp1;
            sampled_write = 3;
            if (io_commit && io_write) begin
                case (io_address)
                    16'hff47: begin sampled_write = 0; prior_palette[0] = ref_bgp; ref_bgp = io_wdata; end
                    16'hff48: begin sampled_write = 1; prior_palette[1] = ref_obp0; ref_obp0 = io_wdata; end
                    16'hff49: begin sampled_write = 2; prior_palette[2] = ref_obp1; ref_obp1 = io_wdata; end
                    default: begin end
                endcase
                if (sampled_write != 3) begin
                    sampled_new_palette = io_wdata;
                    palette_write_dot[sampled_write] = sampled_dot;
                end
            end
        end
    end
    always @(negedge clk_sys) begin
        if (dynamic_palette && $test$plusargs("palette_corrupt") && source_valid && frame_count == 1) begin
            selected_pixel = scene_pick(pixel_count % 160, pixel_count / 160);
            replacement_shade = sampled_new_palette[2 * selected_pixel[1:0] +: 2];
            if (sampled_write == selected_pixel[3:2] && replacement_shade !=
                palette_scene(pixel_count % 160, pixel_count / 160, sampled_bgp, sampled_obp0, sampled_obp1)) begin
                case (replacement_shade)
                    0: force dut.source_shade = 2'd0;
                    1: force dut.source_shade = 2'd1;
                    2: force dut.source_shade = 2'd2;
                    3: force dut.source_shade = 2'd3;
                endcase
            end
        end
    end
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
            // Pinned Pan Docs X0 exception is11 dots independent of SCX.
            // Y100 and 8x16 imply visible lines84..99; X0 has no visible pixels.
            // The first normal line anchors only the common frame origin.
            if (object_zero && frame_count == 1 && pixel_count == 0) normal_first_dot = source_dot;
            if (object_zero && frame_count == 1 && pixel_count % 160 == 0) begin
                zero_expected_dot = normal_first_dot + 64'(456 * (pixel_count / 160)
                    + (pixel_count / 160 >= 84 && pixel_count / 160 < 100 ? 11 : 0));
                if (source_dot !== zero_expected_dot)
                    $fatal(1, "PPU_X0_FIRST line=%0d expected=%0d actual=%0d",
                        pixel_count / 160, zero_expected_dot, source_dot);
                if (pixel_count / 160 >= 84 && pixel_count / 160 < 100) zero_lines = zero_lines + 1;
            end
            if (source_dot !== dot_before || source_dot <= previous_dot || source_epoch !== 32'd5)
                $fatal(1, "PPU_RENDER_TIMESTAMP frame=%0d index=%0d", frame_count, pixel_count);
            if (temporal && pixel_count == 0 && frame_count == 1) normal_first_dot = source_dot;
            if (temporal && pixel_count == 0 && frame_count == 2
                && source_dot - normal_first_dot != 64'd70224)
                $fatal(1, "PPU_RENDER_PERIOD expected=70224 actual=%0d", source_dot - normal_first_dot);
            expected = frame_count == 0 ? 2'd0 : dynamic_palette
                ? palette_scene(pixel_count % 160, pixel_count / 160, sampled_bgp, sampled_obp0, sampled_obp1)
                : scene(pixel_count % 160, pixel_count / 160);
            if (dynamic_palette && frame_count != 0) begin
                if (source_dot != sampled_dot) $fatal(1, "PPU_PALETTE_SNAPSHOT_DOT");
                selected_pixel = scene_pick(pixel_count % 160, pixel_count / 160);
                if (sampled_write == selected_pixel[3:2] && expected != sampled_new_palette[2 * selected_pixel[1:0] +: 2])
                    commit_pixels[selected_pixel[3:2]] = commit_pixels[selected_pixel[3:2]] + 1;
                if (source_dot > palette_write_dot[selected_pixel[3:2]] && expected != prior_palette[selected_pixel[3:2]][2 * selected_pixel[1:0] +: 2])
                    after_pixels[selected_pixel[3:2]] = after_pixels[selected_pixel[3:2]] + 1;
                if (source_shade !== expected)
                    $fatal(1, "PPU_PALETTE_PIXEL frame=%0d index=%0d palette=%0d expected=%0d actual=%0d",
                        frame_count, pixel_count, selected_pixel[3:2], expected, source_shade);
            end
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
                    // Let composed passive observers sample this accepting edge.
                    #1;
                    if (object_zero) begin
                        if (zero_lines != 16) $fatal(1, "PPU_X0_COUNT");
                        $display("PASS PPU X0 hidden object fixed11 lines=16 line_first=144 pixels=46080");
                    end else if (dynamic_palette) begin
                        for (coverage_index = 0; coverage_index < 3; coverage_index = coverage_index + 1)
                            if (commit_pixels[coverage_index] == 0 || after_pixels[coverage_index] == 0)
                                $fatal(1, "PPU_PALETTE_COVERAGE palette=%0d commit=%0d after=%0d", coverage_index,
                                    commit_pixels[coverage_index], after_pixels[coverage_index]);
                        $display("PASS PPU palette signed tiles 8x8 objects asymmetric rows pixels=46080 commit=%0d,%0d,%0d after=%0d,%0d,%0d",
                            commit_pixels[0], commit_pixels[1], commit_pixels[2], after_pixels[0], after_pixels[1], after_pixels[2]);
                    end else if (temporal) begin
                        if (startup_reads != 4) $fatal(1, "PPU_RENDER_STARTUP_COUNT");
                        $display("PASS PPU renderer temporal frames=3 pixels=69120 startup_reads=4 period=70224");
                    end else $display("PASS PPU renderer original_scene frames=2 pixels=46080");
                    if ($test$plusargs("video")) simulation_done = 1;
                    else $finish;
                end
            end else pixel_count = pixel_count + 1;
        end
    end
    initial begin
        $dumpfile("waves/renderer.vcd");
        if ($test$plusargs("object_zero"))
            $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, dot_before,
                io_commit, io_address, io_wdata, source_valid, source_start,
                source_abort, source_x, source_y, source_shade, source_dot,
                source_display_eligible, frame_count, pixel_count, expected,
                zero_expected_dot, zero_lines);
        else $dumpvars(0, dut);
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
        object_zero = $test$plusargs("object_zero"); zero_lines = 0;
        dynamic_palette = $test$plusargs("palette");
        rich_scene = dynamic_palette;
        write_number = 0;
        for (coverage_index = 0; coverage_index < 3; coverage_index = coverage_index + 1) begin
            commit_pixels[coverage_index] = 0;
            after_pixels[coverage_index] = 0;
        end
        simulation_done = 0;
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
        oam[12]=100; oam[13]=object_zero ? 0 : 1; oam[14]=48; oam[15]=32;
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
        write_register(16'hff40, rich_scene ? 8'he3 : 8'hf7);
        if (temporal) begin
            if ($test$plusargs("timing_corrupt")) force dut.io_rdata = 8'h83;
            // Mooneye pinned lcdon_timing-GS brackets, relative to write T4:
            // LD A,(DE) read commits at 4*N+8, using old state at that edge.
            startup_read(76, 16'hff41, 8'h03, 0);
            startup_read(80, 16'hff41, 8'h03, 3);
            startup_read(448, 16'hff44, 8'hff, 0);
            startup_read(452, 16'hff44, 8'hff, 1);
        end
        if (dynamic_palette) begin
            wait (frame_count == 1);
            while (frame_count < 2) begin
                case (write_number % 3)
                    0: write_register(16'hff47, ref_bgp == 8'he4 ? 8'h1b : 8'he4);
                    1: write_register(16'hff48, ref_obp0 == 8'he4 ? 8'h1b : 8'he4);
                    2: write_register(16'hff49, ref_obp1 == 8'he4 ? 8'h1b : 8'he4);
                endcase
                write_number = write_number + 1;
            end
        end
        if ($test$plusargs("object_zero_corrupt")) begin
            wait (frame_count == 1 && pixel_count == 84 * 160);
            @(negedge clk_sys);
            force dut.source_dot = 64'd0;
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
