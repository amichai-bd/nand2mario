`timescale 1ns/1ps
`default_nettype none
module tb_ppu_fetch;
    logic clk_sys, reset, gb_tick, lcd_on, mode3, background_paused;
    logic window_start, window_xy_match, object_found, object_x_flip;
    logic [7:0] vram_data;
    logic vram_valid;
    logic map_read, background_low_read, background_high_read;
    logic object_low_read, object_high_read;
    logic [2:0] background_phase, object_phase, shift_count;
    logic background_done, object_done, background_first_done, window_first;
    logic [7:0] tile_index, background_low, background_high, object_low, object_high;
    logic background_load, object_load, fault, fault_now;
    logic [31:0] cases;
    n2m_ppu_fetch dut (.*);
    task automatic step(input logic [2:0] bg, input logic [2:0] obj);
        #5; clk_sys = 1;
        #1; cases = cases + 1;
        if ({background_phase, object_phase} !== {bg, obj})
            $fatal(1, "PPU_FETCH_PHASE case=%0d expected=%0h actual=%0h",
                cases, {bg, obj}, {background_phase, object_phase});
        #4; clk_sys = 0;
    endtask
    initial begin
        clk_sys = 0;
        reset = 1;
        gb_tick = 0;
        lcd_on = 0;
        mode3 = 0;
        background_paused = 1;
        window_start = 0;
        window_xy_match = 0;
        object_found = 0;
        object_x_flip = 0;
        vram_data = 0;
        vram_valid = 1;
        cases = 0;
        step(0, 0);
        reset = 0;
        lcd_on = 1;
        mode3 = 1;
        gb_tick = 1;
        vram_data = 8'h11;
        step(1, 0);
        if (tile_index !== 0) $fatal(1, "PPU_FETCH_EARLY_CAPTURE");
        if ($test$plusargs("missing")) vram_valid = 0;
        vram_data = 8'h22;
        step(2, 0);
        if (tile_index !== 8'h22) $fatal(1, "PPU_FETCH_MAP_CAPTURE");
        vram_data = 8'h33;
        step(3, 0);
        vram_data = 8'h80;
        step(4, 0);
        vram_data = 8'h55;
        step(5, 0);
        vram_data = 8'h40;
        #1;
        if (!background_load || {background_low, background_high} !== 16'h8040)
            $fatal(1, "PPU_FETCH_PHASE5_BYPASS");
        step(0, 0);
        if (!background_first_done || background_load) $fatal(1, "PPU_FETCH_FIRST_DONE");
        object_found = 1;
        object_x_flip = 1;
        step(1, 0);
        step(2, 0);
        step(3, 0);
        step(4, 0);
        step(5, 0);
        step(6, 1);
        step(7, 2);
        step(7, 3);
        vram_data = 8'h01;
        step(7, 4);
        step(7, 5);
        vram_data = 8'h02;
        #1;
        if (!object_load || {object_low, object_high} !== 16'h8040)
            $fatal(1, "PPU_FETCH_OBJECT_FLIP");
        step(7, 0);
        window_start = 1;
        step(0, 1);
        if (!window_first) $fatal(1, "PPU_FETCH_WINDOW_START");
        gb_tick = 0;
        step(0, 1);
        reset = 1;
        step(0, 0);
        if (fault || window_first || background_first_done || tile_index !== 0)
            $fatal(1, "PPU_FETCH_PAUSED_RESET");
        $display("PASS PPU fetch literal_schedule cases=%0d", cases);
        $finish;
    end
    initial begin
        #1000;
        $fatal(1, "PPU_FETCH_TIMEOUT");
    end
endmodule
