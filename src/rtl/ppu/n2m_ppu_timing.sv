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
    input var logic stat_write,
    input var logic lyc_write,
    input var logic [7:0] write_data,
    input var logic scan_done,
    input var logic scan_active,
    input var logic pixel_end,
    input var logic object_found,
    output logic [6:0] line_quarter,
    output logic [1:0] quarter_phase,
    output logic [7:0] ly,
    output logic [7:0] readable_ly,
    output logic coincidence,
    output logic [1:0] mode,
    output logic mode3,
    output logic mode3_end,
    output logic line_reset,
    output logic stat_condition,
    output logic stat_rise,
    output logic vblank_condition
);
    logic disabled_reset, quarter_edge, half_quarter_edge, quarter_end;
    logic raw_vblank, line153;
    logic [6:0] line_quarter_next;
    logic [7:0] ly_next;
    logic end_of_line, end_of_line_next, end_of_line_delayed;
    logic vblank_stage, vblank_stage_next;
    logic comparison_stage, comparison_stage_next, coincidence_next;
    logic coincidence_irq, coincidence_irq_next, coincidence_natural, irq_natural;
    logic [7:0] comparison_value, comparison_value_next;
    logic comparison_valid, comparison_valid_next;
    logic exceptional, exceptional_next;
    logic [3:0] exception_step, exception_step_next;
    logic stat_transient, natural_stat, final_stat, stat_event;
    logic [3:0] effective_enable, final_enable;
    logic next_mode0, next_mode1, next_mode2;
    logic mode3_end_delayed, mode3_end_delayed_next;
    logic mode3_delayed, scan_delayed;
    logic line_end_sample, line_end_sample_next, ly_reset_hold, ly_reset_hold_next;

    assign disabled_reset = reset || !lcd_on;
    assign quarter_edge = lcd_on && quarter_phase == 0;
    assign half_quarter_edge = lcd_on && quarter_phase == 2;
    assign quarter_end = line_quarter == 7'd113;
    assign raw_vblank = ly >= 8'd144;
    assign line153 = ly == 8'd153;
    assign readable_ly = exceptional && exception_step >= 4'd6 ? 8'd0 : ly;
    assign effective_enable = stat_transient ? 4'hf : stat_enable;
    assign final_enable = stat_write ? 4'hf : stat_enable;
    assign line_quarter_next = quarter_end ? 7'd0 : line_quarter + 1'b1;
    assign mode3_end = !object_found && pixel_end;
    assign mode3 = lcd_on && !mode3_end_delayed && scan_done;
    assign line_reset = quarter_edge && end_of_line && !raw_vblank;
    assign mode = vblank_condition && vblank_stage ? 2'd1
        : scan_delayed ? 2'd2 : mode3_delayed && !mode3_end ? 2'd3 : 2'd0;
    assign stat_condition = (effective_enable[3] && coincidence_irq)
        || (effective_enable[2] && end_of_line_delayed && !vblank_condition)
        || (effective_enable[1] && vblank_condition)
        || (effective_enable[0] && mode3_end_delayed && !vblank_condition);

    always_comb begin
        end_of_line_next = end_of_line;
        vblank_stage_next = vblank_stage;
        if (half_quarter_edge && quarter_end) end_of_line_next = 1;
        else if (end_of_line) begin
            if (quarter_edge) vblank_stage_next = raw_vblank;
            if (half_quarter_edge) end_of_line_next = 0;
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
    // The renderer counter is unchanged. Only CPU readback/comparison has the
    // early line153 window; MAS_ppu defines the accepted A0 and write ordering.
    always_comb begin
        comparison_stage_next = comparison_stage;
        comparison_value_next = comparison_value;
        comparison_valid_next = comparison_valid;
        coincidence_natural = coincidence;
        irq_natural = coincidence_irq;
        exceptional_next = exceptional;
        exception_step_next = exception_step;
        if (lcd_on) begin
            if (ly == 8'd152 && line_quarter == 7'd112 && quarter_phase == 0) begin
                exceptional_next = 1;
                exception_step_next = 0;
                comparison_valid_next = 0;
                coincidence_natural = 0;
            end else if (exceptional) begin
                exception_step_next = exception_step + 4'd1;
                if (exception_step == 4'd5 || exception_step == 4'd11) begin
                    comparison_value_next = exception_step == 4'd5 ? 8'd153 : 8'd0;
                    comparison_valid_next = 1;
                    comparison_stage_next = comparison_value_next == ly_compare;
                    coincidence_natural = comparison_stage_next;
                    irq_natural = comparison_stage_next;
                end else if (exception_step == 4'd7) begin
                    comparison_valid_next = 0;
                    coincidence_natural = 0;
                end else if (exception_step == 4'd12) begin
                    exceptional_next = 0;
                    exception_step_next = 0;
                end
            end else begin
                coincidence_natural = comparison_stage;
                irq_natural = comparison_stage;
                if (quarter_edge) begin
                    comparison_value_next = ly;
                    comparison_valid_next = 1;
                    comparison_stage_next = ly == ly_compare;
                    if (comparison_stage && !comparison_stage_next) begin
                        coincidence_natural = 0;
                        irq_natural = 0;
                    end
                end
            end
        end
        coincidence_next = coincidence_natural;
        coincidence_irq_next = irq_natural;
        // Legal CPU writes follow the natural observation on this same dot.
        // Invalid comparison keeps IRQ history while its readable flag is zero.
        if (lcd_on && lyc_write && comparison_valid_next) begin
            comparison_stage_next = comparison_value_next == write_data;
            coincidence_next = comparison_stage_next;
            coincidence_irq_next = comparison_stage_next;
        end
    end
    assign next_mode0 = mode3_end_delayed_next && !vblank_stage;
    assign next_mode1 = vblank_stage;
    assign next_mode2 = end_of_line && !vblank_stage;
    assign natural_stat = (stat_enable[3] && irq_natural)
        || (stat_enable[2] && next_mode2) || (stat_enable[1] && next_mode1)
        || (stat_enable[0] && next_mode0);
    assign final_stat = (final_enable[3] && coincidence_irq_next)
        || (final_enable[2] && next_mode2) || (final_enable[1] && next_mode1)
        || (final_enable[0] && next_mode0);
    assign stat_event = (!stat_condition && natural_stat) || (!natural_stat && final_stat);
    // Capture both ordered transitions at A; owner133 consumes before B. This
    // pulse clears on the next system edge even when host pause stops dots.
    `DFF_RST(stat_rise, gb_tick && stat_event, clk_sys, reset)
    `DFF_RST_EN(stat_transient, stat_write, clk_sys, gb_tick, reset, 1'b0)
    `DFF_RST_EN(exceptional, exceptional_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(exception_step, exception_step_next, clk_sys, gb_tick, disabled_reset, 4'd0)
    `DFF_RST_EN(comparison_value, comparison_value_next, clk_sys, gb_tick, reset, 8'd0)
    `DFF_RST_EN(comparison_valid, comparison_valid_next, clk_sys, gb_tick, reset, 1'b0)
    `DFF_RST_EN(coincidence_irq, coincidence_irq_next, clk_sys, gb_tick, reset, 1'b0)
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
    `N2M_ASSERT(timing_exception_range, clk_sys, reset, exception_step <= 4'd12)
    `N2M_ASSERT(timing_quarter_range, clk_sys, reset, line_quarter <= 7'd113)
    `N2M_ASSERT(timing_ly_range, clk_sys, reset, ly <= 8'd153)
    `N2M_ASSERT_KNOWN(timing_state_known, clk_sys, reset,
        {line_quarter, quarter_phase, ly, readable_ly, coincidence, coincidence_irq,
         comparison_valid, comparison_value, exceptional, exception_step,
         mode, stat_condition, stat_rise, vblank_condition})
endmodule
