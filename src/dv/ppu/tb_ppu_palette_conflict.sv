`timescale 1ns/1ps
`default_nettype none
// Original literal old/conflict/new cases. No model or DUT-derived oracle.
module tb_ppu_palette_conflict;
    logic clk_sys, reset, gb_tick, io_commit, io_write;
    logic [15:0] io_address;
    logic [7:0] io_wdata, ly;
    logic [1:0] mode, quarter_phase;
    logic coincidence, io_selected;
    logic [7:0] io_rdata, lcdc, scy, scx, lyc, bgp, obp0, obp1, wy, wx;
    logic [7:0] render_bgp, render_obp0, render_obp1;
    logic [3:0] stat_enable;
    logic stat_write, lyc_write, lcd_enable, lcd_disable;
    logic corrupt;
    integer palette, checks, trace_file;
    logic [23:0] expected_render;
    n2m_ppu_registers dut (.*);
    always #5 clk_sys = ~clk_sys;

    task automatic check(input logic [7:0] expected, input logic [7:0] readback);
        #1;
        case (palette)
            0: expected_render = {16'd0, expected};
            1: expected_render = {8'd0, expected, 8'd0};
            default: expected_render = {expected, 16'd0};
        endcase
        checks = checks + 1;
        $fdisplay(trace_file, "%0d,%0d,%06x,%06x,%02x,%02x", checks, palette,
            expected_render, {render_obp1, render_obp0, render_bgp}, readback, io_rdata);
        if ({render_obp1, render_obp0, render_bgp} !== expected_render)
            $fatal(1, "PPU_PALETTE_CONFLICT palette=%0d expected=%06x actual=%06x",
                palette, expected_render, {render_obp1, render_obp0, render_bgp});
        if (!io_selected || io_rdata !== readback)
            $fatal(1, "PPU_PALETTE_READBACK expected=%02x actual=%02x", readback, io_rdata);
    endtask
    task automatic tick;
        @(negedge clk_sys); gb_tick = 1;
        @(posedge clk_sys); #1;
        @(negedge clk_sys); gb_tick = 0;
    endtask
    task automatic write_palette(input logic [7:0] value, input logic [7:0] old_value);
        @(negedge clk_sys); gb_tick = 1; io_commit = 1; io_wdata = value;
        check(old_value, old_value); // Actual renderer input before accepting edge.
        @(posedge clk_sys); #1;
        @(negedge clk_sys); gb_tick = 0; io_commit = 0;
    endtask
    initial begin
        clk_sys = 0; reset = 1; gb_tick = 0; io_commit = 0; io_write = 1;
        io_address = 16'hff47; io_wdata = 0; ly = 0; mode = 0;
        quarter_phase = 3; coincidence = 0; checks = 0;
        corrupt = $test$plusargs("corrupt");
        trace_file = $fopen("palette-conflict.csv", "w");
        if (!trace_file) $fatal(1, "PPU_PALETTE_TRACE_OPEN");
        $fdisplay(trace_file, "check,palette,expected_render,actual_render,expected_read,actual_read");
        $dumpfile("waves/palette-conflict.vcd"); $dumpvars(0, tb_ppu_palette_conflict);
        for (palette = 0; palette < 3; palette = palette + 1) begin
            reset = 1; @(posedge clk_sys); #1;
            @(negedge clk_sys); reset = 0; io_address = 16'hff47 + 16'(palette);
            check(0, 0);
            write_palette(8'h55, 0); check(8'h55, 8'h55); tick(); check(8'h55, 8'h55);
            write_palette(8'haa, 8'h55);
            if (corrupt && palette == 0) force dut.render_bgp = 8'h55;
            check(8'hff, 8'haa); // OR differs from BOTH old55 and newAA.
            repeat (5) begin @(posedge clk_sys); check(8'hff, 8'haa); end
            // No pixel input exists: expiration is dot-based, including LCD-off.
            tick(); check(8'haa, 8'haa);
            write_palette(8'h55, 8'haa); check(8'hff, 8'h55); tick(); check(8'h55, 8'h55);
            write_palette(8'h55, 8'h55); check(8'h55, 8'h55); tick(); check(8'h55, 8'h55);
            write_palette(0, 8'h55); check(8'h55, 0);
            @(negedge clk_sys); reset = 1; @(posedge clk_sys); #1;
            @(negedge clk_sys); reset = 0; check(0, 0); tick(); check(0, 0);
        end
        $fclose(trace_file);
        $display("PASS PPU palette conflict palettes=3 checks=%0d", checks);
        $finish;
    end
    initial begin #100000; $fatal(1, "PPU_PALETTE_WATCHDOG"); end
endmodule
