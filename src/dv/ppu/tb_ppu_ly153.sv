`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module tb_ppu_ly153;
    logic clk_sys, reset_sys, core_reset, gb_tick, paused, pause_request;
    logic [1:0] cpu_phase;
    logic [63:0] dot_before;
    logic io_commit, io_write, pending_write;
    logic [15:0] io_address;
    logic [7:0] io_wdata, io_rdata;
    logic io_selected, vram_request, vram_valid, oam_valid;
    logic [12:0] vram_address;
    logic [6:0] oam_pair_address;
    logic [1:0] oam_phase;
    logic stat_condition, stat_rise, fault;
    integer rises, cases, elapsed;
    n2m_timebase timebase (.*);
    n2m_ppu dut (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .epoch(32'd2), .dot_before,
        .io_commit, .io_write, .io_address, .io_wdata, .io_rdata, .io_selected,
        .vram_request, .vram_address, .vram_data(8'd0), .vram_valid,
        .oam_pair_address, .oam_phase, .oam_scan_index(), .oam_data(16'd0),
        .oam_valid, .dma_active(1'b0), .vram_cpu_allow(), .oam_cpu_allow(),
        .stat_condition, .stat_rise, .vblank_condition(), .vblank_rise(), .fault,
        .source_valid(), .source_start(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot(), .source_abort(), .blank_assert(),
        .source_display_eligible()
    );
    assign io_commit = pending_write && cpu_phase == 3 && gb_tick;
    `DFF_RST_EN(cpu_phase, cpu_phase + 2'd1, clk_sys, gb_tick, reset_sys || core_reset, 2'd0)
    `DFF_RST_EN(dot_before, dot_before + 64'd1, clk_sys, gb_tick, reset_sys || core_reset, 64'd0)
    `DFF_RST(vram_valid, vram_request, clk_sys, reset_sys)
    `DFF_RST(oam_valid, oam_phase != 0, clk_sys, reset_sys)
    always #10 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        if (!reset_sys && stat_rise) rises = rises + 1;
        if (!reset_sys && fault) $fatal(1, "PPU_LY153_MEMORY_FAULT");
    end
    task automatic write_reg(input logic [15:0] addr, input logic [7:0] value, input logic stop);
        @(negedge clk_sys);
        io_address = addr;
        io_wdata = value;
        pending_write = 1;
        do @(negedge clk_sys); while (!(gb_tick && cpu_phase == 3));
        pause_request = stop;
        @(posedge clk_sys);
        @(negedge clk_sys);
        pending_write = 0;
    endtask
    task automatic next_dot;
        do @(posedge clk_sys); while (!gb_tick);
        @(negedge clk_sys);
    endtask
    task automatic advance_to(input integer target);
        while (elapsed < target) begin
            next_dot();
            elapsed = elapsed + 1;
        end
    endtask
    task automatic check_read(input logic [7:0] line_value, input logic flag_value,
                              input logic irq_value, input logic event_value);
        io_address = 16'hff44;
        #1;
        if (io_rdata !== line_value)
            $fatal(1, "PPU_LY153_READ elapsed=%0d expected=%0d actual=%0d", elapsed, line_value, io_rdata);
        io_address = 16'hff41;
        #1;
        if (io_rdata[2] !== flag_value || stat_condition !== irq_value)
            $fatal(1, "PPU_LY153_COMPARE elapsed=%0d expected_flag=%0d actual_flag=%0d expected_irq=%0d actual_irq=%0d",
                elapsed, flag_value, io_rdata[2], irq_value, stat_condition);
        if (stat_rise !== event_value)
            $fatal(1, "PPU_LY153_EVENT elapsed=%0d expected=%0d actual=%0d", elapsed, event_value, stat_rise);
        cases = cases + 1;
    endtask
    task automatic initialize_case(input logic [7:0] compare, input logic [7:0] mask);
        @(negedge clk_sys);
        core_reset = 1;
        pause_request = 0;
        pending_write = 0;
        repeat (3) @(negedge clk_sys);
        rises = 0;
        core_reset = 0;
        write_reg(16'hff45, compare, 0);
        write_reg(16'hff41, mask, 0);
        write_reg(16'hff40, 128, 0);
        elapsed = 0;
    endtask
    task automatic fixed_compare(input logic [7:0] compare, input logic [7:0] mask);
        integer expected_edges;
        initialize_case(compare, mask);
        advance_to(100);
        if ($test$plusargs("extra_irq")) begin
            force dut.stat_rise = 1'b1;
            @(negedge clk_sys);
            release dut.stat_rise;
        end
        advance_to(69760);
        check_read(152, compare == 152, mask[4] || compare == 152, 0);
        advance_to(69761);
        check_read(152, 0, mask[4] || compare == 152, 0);
        advance_to(69763);
        if ($test$plusargs("ly_corrupt")) force dut.readable_ly = 8'd0;
        check_read(153, 0, mask[4] || compare == 152, 0);
        advance_to(69766);
        check_read(153, 0, mask[4] || compare == 152, 0);
        advance_to(69767);
        check_read(0, compare == 153, mask[4] || compare == 153, !mask[4] && compare == 153);
        advance_to(69768);
        check_read(0, compare == 153, mask[4] || compare == 153, 0);
        advance_to(69769);
        check_read(0, 0, mask[4] || compare == 153, 0);
        advance_to(69772);
        check_read(0, 0, mask[4] || compare == 153, 0);
        advance_to(69773);
        if ($test$plusargs("irq_corrupt")) force dut.stat_rise = 1'b0;
        check_read(0, compare == 0, mask[4] || compare == 0, !mask[4] && compare == 0);
        @(negedge clk_sys);
        expected_edges = mask[4] ? 1 : compare == 0 ? 2 : 1;
        if (rises != expected_edges)
            $fatal(1, "PPU_LY153_EDGE_COUNT compare=%0d expected=%0d actual=%0d", compare, expected_edges, rises);
    endtask
    initial begin
        $dumpfile("waves/ly153.vcd");
        $dumpvars(0, dut.timing);
        $dumpvars(0, io_address, io_wdata, io_rdata, io_commit, stat_rise);
        clk_sys = 0;
        reset_sys = 1;
        core_reset = 0;
        pause_request = 0;
        pending_write = 0;
        io_write = 1;
        io_address = 0;
        io_wdata = 0;
        rises = 0;
        cases = 0;
        elapsed = 0;
        repeat (4) @(negedge clk_sys);
        reset_sys = 0;
        fixed_compare(0, 64);
        fixed_compare(152, 64);
        fixed_compare(153, 64);
        fixed_compare(7, 64);
        // A held VBlank source keeps the OR high through comparator changes.
        fixed_compare(153, 80);
        // A0+1 is a legal T4 inside the first invalid comparison interval.
        initialize_case(152, 64);
        advance_to(69763);
        write_reg(16'hff45, 153, 0);
        elapsed = 69764;
        check_read(153, 0, 1, 0);
        advance_to(69767);
        check_read(0, 1, 1, 0);
        // A0+5 is valid: new LYC recomputes immediately on the commit.
        write_reg(16'hff45, 0, 0);
        elapsed = 69768;
        check_read(0, 0, 0, 0);
        advance_to(69769);
        check_read(0, 0, 0, 0);
        // A0+9 is invalid: neither write creates a false equality or IRQ.
        advance_to(69771);
        write_reg(16'hff45, 153, 0);
        elapsed = 69772;
        check_read(0, 0, 0, 0);
        advance_to(69773);
        check_read(0, 0, 0, 0);
        // Valid write after the window rises once and survives a paused dot.
        write_reg(16'hff45, 0, 1);
        elapsed = 69776;
        check_read(0, 1, 1, 1);
        repeat (20) @(negedge clk_sys);
        if (!paused || stat_rise) $fatal(1, "PPU_LY153_PAUSE_EVENT");
        check_read(0, 1, 1, 0);
        if (rises != 2) $fatal(1, "PPU_LY153_WRITE_EDGE_COUNT expected=2 actual=%0d", rises);
        core_reset = 1;
        repeat (2) @(negedge clk_sys);
        check_read(0, 0, 0, 0);
        if (cases != 54) $fatal(1, "PPU_LY153_COUNT actual=%0d", cases);
        $display("PASS PPU LY153 public reads cases=54 legal LYC invalid valid held-mode edge-count pause reset");
        $finish;
    end
    initial begin
        #120000000;
        $fatal(1, "PPU_LY153_TIMEOUT");
    end
endmodule
