`timescale 1ns/1ps
`default_nettype none
module tb_ppu_shift;
    logic clk_sys, reset, gb_tick, clear_line, advance, background_load;
    logic [7:0] background_low, background_high, object_low, object_high;
    logic object_load, object_palette, object_behind;
    logic [1:0] background_color, object_color;
    logic palette_select, behind_background;
    logic [31:0] cases;
    n2m_ppu_shift dut (.*);
    task automatic edge_check(input logic [1:0] bg, input logic [1:0] obj);
        #5; clk_sys = 1;
        #1; cases = cases + 1;
        if ({background_color, object_color} !== {bg, obj})
            $fatal(1, "PPU_SHIFT_MISMATCH case=%0d expected=%0h actual=%0h",
                cases, {bg, obj}, {background_color, object_color});
        #4; clk_sys = 0;
    endtask
    initial begin
        clk_sys = 0;
        reset = 1;
        gb_tick = 0;
        clear_line = 0;
        advance = 0;
        background_load = 0;
        object_load = 0;
        background_low = 8'h80;
        background_high = 8'h40;
        object_low = 8'h80;
        object_high = 8'h40;
        object_palette = 1;
        object_behind = 1;
        cases = 0;
        edge_check(0, 0);
        reset = 0;
        gb_tick = 1;
        background_load = 1;
        object_load = 1;
        edge_check(1, 1);
        if (!palette_select || !behind_background) $fatal(1, "PPU_SHIFT_METADATA");
        background_load = 0;
        object_load = 0;
        advance = 1;
        edge_check(2, 2);
        advance = 0;
        object_load = 1;
        object_low = 8'hff;
        object_high = 8'hff;
        object_palette = 0;
        object_behind = 0;
        edge_check(2, 2);
        if (!palette_select || !behind_background) $fatal(1, "PPU_SHIFT_PRIORITY_METADATA");
        object_load = 0;
        advance = 1;
        edge_check(0, 3);
        gb_tick = 0;
        edge_check(0, 3);
        reset = 1;
        edge_check(0, 0);
        reset = 0;
        gb_tick = 1;
        advance = 0;
        object_load = 1;
        object_low = 8'h80;
        object_high = 0;
        edge_check(0, 1);
        advance = 1;
        object_low = 0;
        object_high = 8'hff;
        edge_check(0, 0); // pre-edge occupied bit7 is not overwritten after shift
        object_load = 0;
        edge_check(0, 2);
        background_load = 1;
        edge_check(1, 2); // background load wins over advance
        clear_line = 1;
        edge_check(0, 0);
        clear_line = 0;
        background_load = 0;
        advance = 0;
        if ($test$plusargs("unknown")) begin
            force dut.obj_low = 8'hxx;
            edge_check(0, 0); // named state assertion must terminate before check
        end
        $display("PASS PPU shift literal_cases=12");
        $finish;
    end
    initial begin
        #1000;
        $fatal(1, "PPU_SHIFT_TIMEOUT");
    end
endmodule
