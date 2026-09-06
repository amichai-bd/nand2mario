`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module tb_ppu_stat_oam;
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
    integer cases, scenario, rises, elapsed, trace;
    logic [7:0] old_stat;
    logic [4:0] if_stored, if_observe;
    logic if_commit;
    logic [4:0] irq_sources;
    logic vram_cpu_allow, oam_cpu_allow;
    logic [63:0] enable_dot;
    n2m_timebase timebase (.*);
    n2m_ppu dut (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .epoch(32'd2), .dot_before,
        .io_commit, .io_write, .io_address, .io_wdata, .io_rdata, .io_selected,
        .vram_request, .vram_address, .vram_data(8'd0), .vram_valid,
        .oam_pair_address, .oam_phase, .oam_scan_index(), .oam_data(16'd0),
        .oam_valid, .dma_active(1'b0), .vram_cpu_allow, .oam_cpu_allow,
        .stat_condition, .stat_rise, .vblank_condition(), .vblank_rise(), .fault,
        .source_valid(), .source_start(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot(), .source_abort(), .blank_assert(),
        .source_display_eligible()
    );
    assign irq_sources = {3'b000, stat_rise, 1'b0};
    assign if_commit = io_commit && io_address == 16'hff0f;
    n2m_interrupts irq_owner (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_commit(if_commit), .io_write(if_commit), .io_address(16'hff0f), .io_wdata(8'd0),
        .source_event(5'd0), .source_level(irq_sources), .irq_ack(5'd0), .io_selected(), .io_rdata(),
        .ie_stored(), .if_stored, .ie_observe(), .if_observe
    );
    assign io_commit = pending_write && cpu_phase == 3 && gb_tick;
    `DFF_RST_EN(cpu_phase, cpu_phase + 2'd1, clk_sys, gb_tick, reset_sys || core_reset, 2'd0)
    `DFF_RST_EN(dot_before, dot_before + 64'd1, clk_sys, gb_tick, reset_sys || core_reset, 64'd0)
    `DFF_RST(vram_valid, vram_request, clk_sys, reset_sys)
    `DFF_RST(oam_valid, oam_phase != 0, clk_sys, reset_sys)
    always #10 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        if (io_commit && io_address == 16'hff40 && io_wdata[7]) enable_dot = dot_before;
        if (!reset_sys && !core_reset && stat_rise) rises = rises + 1;
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

    task automatic observe_at(input integer at_dot, input logic do_write,
        input logic [15:0] address, input logic expected_line, input logic expected_rise,
        input logic [4:0] expected_if, input integer expected_edges);
        @(negedge clk_sys);
        io_address = address; io_wdata = 0; io_write = do_write; pending_write = 0;
        do @(negedge clk_sys); while (!(gb_tick && dot_before == enable_dot + 64'(at_dot)));
        pending_write = do_write;
        #1;
        if (do_write && cpu_phase != 3) $fatal(1, "PPU_STAT_OAM_ILLEGAL_WRITE");
        if (do_write && address == 16'hff41) begin
            if ($test$plusargs("qualifier_fault") && scenario == 0)
                force dut.timing.final_enable = 4'hf;
            #1;
            // This is the explicitly scoped internal compatibility qualifier;
            // the simultaneous HBlank OR masks its public IRQ effect at452.
            if (dut.timing.final_enable !== (scenario == 0 ? 4'hb : 4'hf))
                $fatal(1, "PPU_STAT_OAM_QUALIFIER case=%0d expected=%h actual=%h",
                    scenario, scenario == 0 ? 4'hb : 4'hf, dut.timing.final_enable);
        end
        if (at_dot == 452 || at_dot == 456) begin
            if (vram_cpu_allow !== 1'b1 || oam_cpu_allow !== (at_dot == 452))
                $fatal(1, "PPU_STAT_OAM_ACCESS dot=%0d", at_dot);
            // Public STAT read fields remain readable during its write cycle.
            if (address == 16'hff41 && io_rdata[1:0] !== (at_dot == 452 ? 2'd0 : 2'd2))
                $fatal(1, "PPU_STAT_OAM_MODE dot=%0d", at_dot);
        end
        @(posedge clk_sys);
        @(negedge clk_sys);
        pending_write = 0;
        $fdisplay(trace, "%0d,%0d,%0d,%0d,%0d,%0d,%0h,%0h",
            scenario, at_dot, expected_line, stat_condition, expected_rise, stat_rise, expected_if, if_observe);
        if (stat_condition !== expected_line || stat_rise !== expected_rise || if_observe !== expected_if)
            $fatal(1, "PPU_STAT_OAM_A case=%0d dot=%0d line=%0d rise=%0d if=%h",
                scenario, at_dot, stat_condition, stat_rise, if_observe);
        @(posedge clk_sys);
        @(negedge clk_sys);
        if (stat_rise !== 0 || if_stored !== expected_if || rises != expected_edges)
            $fatal(1, "PPU_STAT_OAM_B case=%0d dot=%0d rises=%0d expected=%0d if=%h",
                scenario, at_dot, rises, expected_edges, if_stored);
        cases = cases + 1;
    endtask
    initial begin
        $dumpfile("waves/stat-oam.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, dot_before,
            cpu_phase, io_commit, io_address, io_wdata, io_rdata,
            vram_cpu_allow, oam_cpu_allow, stat_condition, stat_rise,
            if_stored, if_observe, rises, cases, scenario);
        clk_sys = 0; reset_sys = 1; core_reset = 0; pause_request = 0;
        pending_write = 0; io_write = 1; io_address = 0; io_wdata = 0;
        cases = 0; enable_dot = 0; rises = 0;
        trace = $fopen("stat-oam.csv", "w");
        if (!trace) $fatal(1, "PPU_STAT_OAM_TRACE");
        $fdisplay(trace, "case,dot,expected_line,line,expected_rise,rise,expected_if,if_observe");
        repeat (4) @(negedge clk_sys); reset_sys = 0;
        for (scenario = 0; scenario < 6; scenario = scenario + 1) begin
            core_reset = 1;
            repeat (4) @(negedge clk_sys);
            core_reset = 0; rises = 0; io_write = 1;
            old_stat = scenario < 4 ? (scenario % 2 == 0 ? 8'h08 : 8'h28) : 8'h20;
            write_reg(16'hff45, 255, 0);
            write_reg(16'hff41, old_stat, 0);
            write_reg(16'hff40, 128, 0);
            // Clear the actual IF after the old HBlank event, without changing
            // PPU history. OAM-only cases have no earlier source/event.
            observe_at(448, 1, 16'hff0f, scenario < 4, 0, 0, scenario < 4 ? 1 : 0);
            // Old08/28 STAT writes and natural OAM+IF writes are separate CPU
            // transactions. A single commit never writes both registers.
            observe_at(452, scenario < 2 || scenario == 5,
                scenario == 5 ? 16'hff0f : 16'hff41, 1, scenario >= 4,
                scenario == 4 ? 5'd2 : 5'd0, 1);
            for (elapsed = 453; elapsed <= 455; elapsed = elapsed + 1)
                observe_at(elapsed, 0, 16'hff41, scenario == 3 || scenario >= 4,
                    0, scenario == 4 ? 5'd2 : 5'd0, 1);
            observe_at(456, scenario == 2 || scenario == 3, 16'hff41,
                0, 0, scenario == 4 ? 5'd2 : 5'd0, 1);
            observe_at(460, 0, 16'hff41, 0, 0, scenario == 4 ? 5'd2 : 5'd0, 1);
        end
        if (cases != 42) $fatal(1, "PPU_STAT_OAM_COUNT");
        $display("PASS PPU STAT OAM compatibility qualifier public overlap IF priority cases=6 checks=42");
        $fclose(trace);
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "PPU_STAT_OAM_TIMEOUT");
    end
endmodule
