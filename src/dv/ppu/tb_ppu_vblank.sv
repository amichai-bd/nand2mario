`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module tb_ppu_vblank;
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
    logic stat_condition, stat_rise, vblank_condition, vblank_rise, fault;
    integer cases, scenario, rises, vblank_edges, trace;
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
        .stat_condition, .stat_rise, .vblank_condition, .vblank_rise, .fault,
        .source_valid(), .source_start(), .source_shade(), .source_x(), .source_y(),
        .source_epoch(), .source_dot(), .source_abort(), .blank_assert(),
        .source_display_eligible()
    );
    assign irq_sources = {3'b000, stat_rise, vblank_rise};
    assign if_commit = io_commit && io_address == 16'hff0f;
    n2m_interrupts irq_owner (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_commit(if_commit), .io_write(if_commit), .io_address(16'hff0f), .io_wdata(8'd0),
        .source_level(irq_sources), .irq_ack(5'd0), .io_selected(), .io_rdata(),
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
        if (!reset_sys && !core_reset && vblank_rise) vblank_edges = vblank_edges + 1;
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


    // Literal projection from the pinned controller pipeline: LY144/end-of-line
    // at65659, delayed OAM source at65660, VBlank stage at65661 and output at65662.
    task automatic observe_at(input integer at_dot, input logic clear_if,
        input logic expected_stat, input logic expected_stat_rise,
        input logic expected_vblank, input logic expected_vblank_rise,
        input logic [4:0] expected_if, input integer expected_stat_edges,
        input integer expected_vblank_edges);
        @(negedge clk_sys);
        io_address = 16'hff0f; io_wdata = 0; io_write = clear_if; pending_write = 0;
        do @(negedge clk_sys); while (!(gb_tick && dot_before == enable_dot + 64'(at_dot)));
        pending_write = clear_if;
        #1;
        if (clear_if && cpu_phase != 3) $fatal(1, "PPU_VBLANK_ILLEGAL_WRITE");
        @(posedge clk_sys);
        @(negedge clk_sys);
        pending_write = 0;
        if ($test$plusargs("vblank_fault") && scenario == 0 && at_dot == 65662)
            force dut.vblank_rise = 1'b0;
        #1;
        $fdisplay(trace, "%0d,%0d,%0d,%0d,%0d,%0d,%0h",
            scenario, at_dot, stat_condition, stat_rise, vblank_condition, vblank_rise, if_observe);
        if (vblank_rise !== expected_vblank_rise)
            $fatal(1, "PPU_VBLANK_EVENT case=%0d dot=%0d expected=%0d actual=%0d",
                scenario, at_dot, expected_vblank_rise, vblank_rise);
        if (stat_condition !== expected_stat || stat_rise !== expected_stat_rise
            || vblank_condition !== expected_vblank || if_observe !== expected_if)
            $fatal(1, "PPU_VBLANK_A case=%0d dot=%0d stat=%0d rise=%0d vblank=%0d if=%h expected_if=%h",
                scenario, at_dot, stat_condition, stat_rise, vblank_condition, if_observe, expected_if);
        @(posedge clk_sys);
        @(negedge clk_sys);
        if (stat_rise !== 0 || vblank_rise !== 0 || if_stored !== expected_if
            || rises != expected_stat_edges || vblank_edges != expected_vblank_edges)
            $fatal(1, "PPU_VBLANK_B case=%0d dot=%0d stat_edges=%0d vblank_edges=%0d if=%h",
                scenario, at_dot, rises, vblank_edges, if_stored);
        cases = cases + 1;
    endtask
    initial begin
        $dumpfile("waves/vblank.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, dot_before,
            cpu_phase, io_commit, io_address, io_wdata, stat_condition, stat_rise,
            vblank_condition, vblank_rise, if_stored, if_observe,
            rises, vblank_edges, cases, scenario);
        clk_sys = 0; reset_sys = 1; core_reset = 0; pause_request = 0;
        pending_write = 0; io_write = 1; io_address = 0; io_wdata = 0;
        cases = 0; enable_dot = 0; rises = 0; vblank_edges = 0;
        trace = $fopen("vblank.csv", "w");
        if (!trace) $fatal(1, "PPU_VBLANK_TRACE");
        $fdisplay(trace, "case,dot,stat,stat_rise,vblank,vblank_rise,if_observe");
        repeat (4) @(negedge clk_sys); reset_sys = 0;
        for (scenario = 0; scenario < 4; scenario = scenario + 1) begin
            core_reset = 1;
            repeat (4) @(negedge clk_sys);
            core_reset = 0; io_write = 1;
            old_stat = scenario == 0 ? 8'h10 : scenario == 2 ? 8'h30 : 8'h20;
            write_reg(16'hff45, 255, 0);
            write_reg(16'hff41, old_stat, 0);
            write_reg(16'hff40, 128, 0);
            // Begin the independent all-system-edge count before the line144
            // interval. Earlier mode2 events are outside this bounded window.
            do @(negedge clk_sys); while (dot_before < enable_dot + 64'd65652);
            rises = 0; vblank_edges = 0;
            observe_at(65656, 1, 0, 0, 0, 0, 0, 0, 0);
            observe_at(65659, 0, 0, 0, 0, 0, 0, 0, 0);
            observe_at(65660, scenario == 3, scenario != 0, scenario != 0, 0, 0,
                scenario == 1 || scenario == 2 ? 5'd2 : 5'd0, scenario != 0, 0);
            observe_at(65661, 0, scenario != 0, 0, 0, 0,
                scenario == 1 || scenario == 2 ? 5'd2 : 5'd0, scenario != 0, 0);
            observe_at(65662, 0, scenario == 0 || scenario == 2, scenario == 0, 1, 1,
                scenario == 3 ? 5'd1 : 5'd3, 1, 1);
            observe_at(65663, 0, scenario == 0 || scenario == 2, 0, 1, 0,
                scenario == 3 ? 5'd1 : 5'd3, 1, 1);
            observe_at(65664, 1, scenario == 0 || scenario == 2, 0, 1, 0, 0, 1, 1);
            observe_at(65668, 0, scenario == 0 || scenario == 2, 0, 1, 0, 0, 1, 1);
        end
        if (cases != 32) $fatal(1, "PPU_VBLANK_COUNT");
        $display("PASS PPU line144 STAT VBlank IF priority cases=4 checks=32");
        $fclose(trace);
        $finish;
    end
    initial begin
        #100000000;
        $fatal(1, "PPU_VBLANK_TIMEOUT");
    end
endmodule
