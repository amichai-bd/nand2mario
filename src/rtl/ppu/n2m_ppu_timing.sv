`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Copyright (c) 2015 Till Harbaum <till@harbaum.org>
// SPDX-License-Identifier: GPL-3.0-or-later
// Pinned video.v controller adaptation; provenance/local changes: upstream.json.
// See GPL-3.0.txt and THIRD_PARTY.md. Exact integration gates remain in MAS_ppu.
module n2m_ppu_timing (
    input var logic clk_sys,
    input var logic reset,
    input var logic gb_tick,
    input var logic lcd_on,
    input var logic [7:0] ly_compare,
    input var logic [3:0] stat_enable,
    input var logic scan_done,
    input var logic scan_active,
    input var logic pixel_end,
    input var logic object_found,
    output logic [6:0] line_quarter,
    output logic [1:0] quarter_phase,
    output logic [7:0] ly,
    output logic coincidence,
    output logic [1:0] mode,
    output logic mode3,
    output logic mode3_end,
    output logic line_reset,
    output logic stat_condition,
    output logic vblank_condition
);
    logic disabled_reset, quarter_edge, half_quarter_edge, quarter_end;
    logic raw_vblank, line153, compare_equal;
    logic [6:0] line_quarter_next;
    logic [7:0] ly_next;
    logic end_of_line, end_of_line_next, end_of_line_delayed;
    logic vblank_stage, vblank_stage_next;
    logic comparison_stage, comparison_stage_next, coincidence_next;
    logic mode3_end_delayed, mode3_end_delayed_next;
    logic mode3_delayed, scan_delayed;
    logic line_end_sample, line_end_sample_next, ly_reset_hold, ly_reset_hold_next;

    assign disabled_reset = reset || !lcd_on;
    assign quarter_edge = lcd_on && quarter_phase == 0;
    assign half_quarter_edge = lcd_on && quarter_phase == 2;
    assign quarter_end = line_quarter == 7'd113;
    assign raw_vblank = ly >= 8'd144;
    assign line153 = ly == 8'd153;
    assign compare_equal = ly == ly_compare;
    assign line_quarter_next = quarter_end ? 7'd0 : line_quarter + 1'b1;
    assign mode3_end = !object_found && pixel_end;
    assign mode3 = lcd_on && !mode3_end_delayed && scan_done;
    assign line_reset = quarter_edge && end_of_line && !raw_vblank;
    assign mode = vblank_condition && vblank_stage ? 2'd1
        : scan_delayed ? 2'd2 : mode3_delayed && !mode3_end ? 2'd3 : 2'd0;
    assign stat_condition = (stat_enable[3] && coincidence)
        || (stat_enable[2] && end_of_line_delayed && !vblank_condition)
        || (stat_enable[1] && vblank_condition)
        || (stat_enable[0] && mode3_end_delayed && !vblank_condition);

    always_comb begin
        end_of_line_next = end_of_line;
        vblank_stage_next = vblank_stage;
        if (half_quarter_edge && quarter_end) end_of_line_next = 1;
        else if (end_of_line) begin
            if (quarter_edge) vblank_stage_next = raw_vblank;
            if (half_quarter_edge) end_of_line_next = 0;
        end
        comparison_stage_next = comparison_stage;
        coincidence_next = comparison_stage;
        if (quarter_edge) begin
            comparison_stage_next = compare_equal;
            // Preserve the DMG falling comparison's earlier visible edge.
            if (comparison_stage && !compare_equal) coincidence_next = 0;
        end
        mode3_end_delayed_next = line_reset ? 1'b0 : mode3_end;
        ly_next = ly;
        line_end_sample_next = line_end_sample;
        ly_reset_hold_next = ly_reset_hold;
        if (!ly_reset_hold && half_quarter_edge && quarter_end) ly_next = ly + 1'b1;
        if (quarter_edge) begin
            line_end_sample_next = end_of_line;
            if (line_end_sample && !end_of_line) begin
                ly_reset_hold_next = line153;
                if (line153) ly_next = 0;
            end
        end
    end
    `DFF_RST_EN(quarter_phase, quarter_phase + 2'd1, clk_sys, gb_tick, disabled_reset, 2'd0)
    `DFF_RST_EN(line_quarter, line_quarter_next, clk_sys, gb_tick && quarter_edge, disabled_reset, 7'd0)
    `DFF_RST_EN(ly, ly_next, clk_sys, gb_tick, disabled_reset, 8'd0)
    `DFF_RST_EN(end_of_line, end_of_line_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(end_of_line_delayed, end_of_line, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(vblank_stage, vblank_stage_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(vblank_condition, vblank_stage, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(line_end_sample, line_end_sample_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(ly_reset_hold, ly_reset_hold_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(mode3_end_delayed, mode3_end_delayed_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(mode3_delayed, mode3, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(scan_delayed, scan_active, clk_sys, gb_tick, disabled_reset, 1'b0)
    // LCD disable retains comparison history; system/core reset initializes it.
    `DFF_RST_EN(comparison_stage, comparison_stage_next, clk_sys, gb_tick, reset, 1'b0)
    `DFF_RST_EN(coincidence, coincidence_next, clk_sys, gb_tick, reset, 1'b0)
    `N2M_ASSERT(timing_quarter_range, clk_sys, reset, line_quarter <= 7'd113)
    `N2M_ASSERT(timing_ly_range, clk_sys, reset, ly <= 8'd153)
    `N2M_ASSERT_KNOWN(timing_state_known, clk_sys, reset,
        {line_quarter, quarter_phase, ly, coincidence, mode, stat_condition, vblank_condition})
endmodule
