`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module tb_ppu_stat_off;
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
    integer rises, cases;
    n2m_timebase timebase (.*);
    n2m_ppu dut (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .epoch(32'd2), .dot_before,
        .io_commit, .io_write, .io_address, .io_wdata, .io_rdata, .io_selected,
        .vram_request, .vram_address, .vram_data(8'd0), .vram_valid,
        .oam_pair_address, .oam_phase, .oam_scan_index(), .oam_data(16'd0),
        .oam_valid, .dma_active(1'b0), .vram_cpu_allow(), .oam_cpu_allow(), .oam_cpu_read_allow(),
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
        if (!reset_sys && fault) $fatal(1, "PPU_STAT_MEMORY_FAULT");
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
    task automatic check_state(input logic flag, input logic line_value,
        input integer edges, input logic off);
        @(negedge clk_sys);
        io_address = 16'hff44;
        #1;
        if (io_rdata !== 0) $fatal(1, "PPU_STAT_OFF_LY case=%0d actual=%0d", cases, io_rdata);
        io_address = 16'hff41;
        #1;
        if (io_rdata[2] !== flag || stat_condition !== line_value || rises != edges
            || (off && io_rdata[1:0] !== 0))
            $fatal(1, "PPU_STAT_OFF_STATE case=%0d expected_flag=%0d expected_line=%0d expected_edges=%0d actual_flag=%0d actual_line=%0d actual_edges=%0d mode=%0d",
                cases, flag, line_value, edges, io_rdata[2], stat_condition, rises, io_rdata[1:0]);
        cases = cases + 1;
    endtask
    initial begin
        $dumpfile("waves/stat-off.vcd");
        $dumpvars(0, dut);
        clk_sys = 0; reset_sys = 1; core_reset = 0; pause_request = 0;
        pending_write = 0; io_write = 1; io_address = 0; io_wdata = 0;
        rises = 0; cases = 0;
        repeat (4) @(negedge clk_sys);
        reset_sys = 0;
        write_reg(16'hff45, 0, 0);
        write_reg(16'hff41, 64, 0);
        check_state(0, 0, 0, 1);
        write_reg(16'hff40, 128, 0);
        repeat (4) next_dot();
        check_state(1, 1, 1, 0);
        write_reg(16'hff40, 0, 0);
        check_state(1, 1, 1, 1);
        // Writable enables and LYC change while both comparison histories hold.
        write_reg(16'hff41, 0, 0);
        check_state(1, 1, 1, 1);
        write_reg(16'hff45, 1, 0);
        check_state(1, 1, 1, 1);
        write_reg(16'hff45, 0, 0);
        write_reg(16'hff41, 64, 0);
        check_state(1, 1, 1, 1);
        // Equal to equal restart must not create a synthetic falling/rising pair.
        write_reg(16'hff40, 128, 0);
        repeat (4) next_dot();
        check_state(1, 1, 1, 0);
        write_reg(16'hff40, 0, 0);
        write_reg(16'hff45, 1, 0);
        write_reg(16'hff40, 128, 0);
        repeat (4) next_dot();
        check_state(0, 0, 1, 0);
        write_reg(16'hff40, 0, 0);
        check_state(0, 0, 1, 1);
        write_reg(16'hff45, 0, 0);
        check_state(0, 0, 1, 1);
        if ($test$plusargs("off_corrupt")) force dut.stat_condition = 1'b1;
        // A write that would enable a retained source cannot itself update off state.
        write_reg(16'hff41, 64, 0);
        check_state(0, 0, 1, 1);
        write_reg(16'hff40, 128, 0);
        repeat (4) next_dot();
        check_state(1, 1, 2, 0);
        // Pause after a legal disable; core reset clears histories without a dot.
        write_reg(16'hff40, 0, 1);
        repeat (20) @(negedge clk_sys);
        if (!paused) $fatal(1, "PPU_STAT_OFF_PAUSE");
        check_state(1, 1, 2, 1);
        core_reset = 1;
        repeat (2) @(negedge clk_sys);
        check_state(0, 0, 2, 1);
        if (cases != 14) $fatal(1, "PPU_STAT_OFF_COUNT actual=%0d", cases);
        $display("PASS PPU STAT LCD off cases=14 edges=2");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1, "PPU_STAT_OFF_TIMEOUT");
    end
endmodule
