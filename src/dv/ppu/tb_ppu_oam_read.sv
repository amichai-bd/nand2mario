`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module tb_ppu_oam_read;
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
    integer cases;
    logic vram_cpu_allow, oam_cpu_allow, oam_cpu_read_allow, dma_active;
    logic [63:0] enable_dot;
    n2m_timebase timebase (.*);
    n2m_ppu dut (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .epoch(32'd2), .dot_before,
        .io_commit, .io_write, .io_address, .io_wdata, .io_rdata, .io_selected,
        .vram_request, .vram_address, .vram_data(8'd0), .vram_valid,
        .oam_pair_address, .oam_phase, .oam_scan_index(), .oam_data(16'd0),
        .oam_valid, .dma_active, .vram_cpu_allow, .oam_cpu_allow, .vram_cpu_read_allow(), .oam_cpu_read_allow,
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
        if (io_commit && io_address == 16'hff40 && io_wdata[7]) enable_dot = dot_before;
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
    task automatic check_permissions(input logic read_allowed, input logic write_allowed);
        if (oam_cpu_read_allow !== read_allowed || oam_cpu_allow !== write_allowed)
            $fatal(1, "PPU_OAM_READ_WINDOW expected=%0d/%0d actual=%0d/%0d",
                read_allowed, write_allowed, oam_cpu_read_allow, oam_cpu_allow);
        cases = cases + 1;
    endtask
    task automatic check_at(input integer elapsed, input logic read_allowed, input logic write_allowed);
        @(negedge clk_sys);
        if (elapsed == 452 && $test$plusargs("read_corrupt")) force dut.oam_cpu_read_allow = 1'b1;
        do @(posedge clk_sys); while (!(gb_tick && dot_before == enable_dot + 64'(elapsed)));
        if (cpu_phase != 3) $fatal(1, "PPU_OAM_READ_PHASE");
        check_permissions(read_allowed, write_allowed);
        @(negedge clk_sys);
    endtask
    task automatic hold_before(input integer elapsed);
        @(negedge clk_sys);
        do @(negedge clk_sys); while (!(gb_tick && dot_before == enable_dot + 64'(elapsed - 1)));
        pause_request = 1;
        @(posedge clk_sys); @(negedge clk_sys);
        repeat (20) begin
            @(negedge clk_sys);
            if (gb_tick || dot_before != enable_dot + 64'(elapsed)
                || oam_cpu_read_allow !== 1'b0 || oam_cpu_allow !== 1'b1)
                $fatal(1, "PPU_OAM_READ_PAUSE");
        end
        check_permissions(0, 1);
    endtask
    initial begin
        $dumpfile("waves/oam-read.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, dot_before,
            cpu_phase, io_commit, io_address, io_wdata, oam_cpu_read_allow,
            oam_cpu_allow, dma_active, cases, fault, pause_request, paused);
        clk_sys = 0; reset_sys = 1; core_reset = 0; pause_request = 0;
        pending_write = 0; io_write = 1; io_address = 0; io_wdata = 0;
        dma_active = 0; cases = 0; enable_dot = 0;
        repeat (4) @(negedge clk_sys); reset_sys = 0;
        check_permissions(1, 1);
        write_reg(16'hff45, 255, 0);
        write_reg(16'hff40, 129, 0);
        check_at(8, 1, 1);
        check_at(76, 1, 1);
        check_at(80, 0, 0);
        check_at(448, 1, 1);
        hold_before(452);
        pause_request = 0;
        check_at(452, 0, 1);
        check_at(456, 0, 0);
        check_at(904, 1, 1);
        check_at(908, 0, 1);
        check_at(912, 0, 0);
        // Renderer LY is144 at this boundary; early read denial is excluded.
        check_at(65660, 1, 1);
        // At the next frame boundary internal LY0 must block again.
        hold_before(70220);
        dma_active = 1; @(negedge clk_sys); check_permissions(0, 0);
        dma_active = 0; @(negedge clk_sys); check_permissions(0, 1);
        core_reset = 1; repeat (3) @(negedge clk_sys); check_permissions(1, 1);
        if (cases != 16) $fatal(1, "PPU_OAM_READ_COUNT");
        $display("PASS PPU early OAM read window cases=16");
        $finish;
    end
    initial begin
        #30000000;
        $fatal(1, "PPU_OAM_READ_TIMEOUT");
    end
endmodule
