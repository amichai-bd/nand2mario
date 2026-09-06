`timescale 1ns/1ps
`default_nettype none
// Original literal cases; expected shades are independent of the DUT decoder.
module tb_ppu_mix;
    logic background_enable, object_enable;
    logic [1:0] background_color, object_color;
    logic object_behind_background, object_palette_select;
    logic [7:0] background_palette, object_palette0, object_palette1;
    logic [1:0] shade;
    logic corrupt;
    logic [31:0] case_id;
    logic [31:0] trace_file;
    n2m_ppu_mix dut (.*);

    task automatic check(input logic [1:0] expected);
        #1;
        case_id = case_id + 1;
        $fdisplay(trace_file, "%0d,%0d,%0d", case_id, expected, shade);
        if (shade !== expected)
            $fatal(1, "PPU_MIX_MISMATCH case=%0d expected=%0d actual=%0d", case_id, expected, shade);
    endtask

    initial begin
        case_id = 0;
        corrupt = $test$plusargs("corrupt");
        trace_file = $fopen("mix.csv", "w");
        if (!trace_file) $fatal(1, "PPU_MIX_TRACE_OPEN");
        $fdisplay(trace_file, "case,expected,actual");
        $dumpfile("waves/mix.vcd");
        $dumpvars(0, tb_ppu_mix);
        background_enable = 1;
        object_enable = 1;
        background_color = 0;
        object_color = 0;
        object_behind_background = 0;
        object_palette_select = 0;
        background_palette = 8'h03; // BG raw0 black, raw1/2/3 white.
        object_palette0 = 8'h40; // OBJ raw3 light gray.
        object_palette1 = 8'h80; // OBJ raw3 dark gray.
        check(3); // transparent OBJ, remapped BG0
        object_color = 3;
        object_behind_background = 1;
        check(1); // raw BG0 permits the object despite black final BG
        background_color = 1;
        if (corrupt) force dut.shade = 2'd3;
        check(0); // nonzero BG hides object despite white final BG
        object_behind_background = 0;
        check(1);
        object_palette_select = 1;
        check(2);
        object_enable = 0;
        check(0);
        background_enable = 0;
        check(3); // LCDC0 disable still maps BG0 through BGP
        object_enable = 1;
        object_behind_background = 1;
        check(2); // disabled BG cannot hide behind-BG object
        object_color = 0;
        object_palette1 = 8'hff;
        check(3); // OBJ raw0 remains transparent even when mapped black
        background_enable = 1;
        background_palette = 8'h1b;
        background_color = 2;
        check(1);
        $fclose(trace_file);
        $display("PASS PPU mixer literal_cases=10");
        $finish;
    end
    initial begin
        #1000;
        $fatal(1, "PPU_MIX_TIMEOUT");
    end
endmodule
