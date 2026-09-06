`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Copyright (c) 2015 Till Harbaum <till@harbaum.org>
// SPDX-License-Identifier: GPL-3.0-or-later
// DMG window state from pinned video.v; local changes in upstream.json.
// Terms retained in GPL-3.0.txt and THIRD_PARTY.md.
module n2m_ppu_window (
    input var logic clk_sys,
    input var logic reset,
    input var logic gb_tick,
    input var logic lcd_on,
    input var logic window_enable,
    input var logic [7:0] wy,
    input var logic [7:0] wx,
    input var logic [7:0] ly,
    input var logic [7:0] raw_x,
    input var logic [1:0] quarter_phase,
    input var logic line_reset,
    input var logic vblank_condition,
    input var logic background_paused,
    input var logic background_load,
    output logic xy_match,
    output logic window_start,
    output logic window_active,
    output logic [7:0] window_row,
    output logic [4:0] window_column
);
    logic y_matched, y_matched_next, xy_delayed, xy_delayed_next;
    logic active_latch, active_latch_next, active_delayed;
    logic [7:0] window_row_next;
    logic [4:0] window_column_next;
    logic disabled_reset, window_reset;
    assign disabled_reset = reset || !lcd_on;
    assign xy_match = y_matched && raw_x == wx;
    assign window_start = !active_latch && window_enable
        && ((!background_paused && xy_match) || xy_delayed);
    assign window_reset = line_reset || !window_enable;
    assign window_active = active_latch && !window_reset;
    always_comb begin
        y_matched_next = y_matched;
        xy_delayed_next = xy_delayed;
        active_latch_next = active_latch;
        window_row_next = window_row;
        window_column_next = window_column;
        if (vblank_condition) y_matched_next = 0;
        else if (quarter_phase == 0 && window_enable && ly == wy) y_matched_next = 1;
        // Intentionally retained across line/VBlank: part of the DMG WX166
        // behavior, not a generic per-line clearable comparator.
        if (!background_paused) xy_delayed_next = xy_match;
        if (window_reset) active_latch_next = 0;
        else if (window_start) active_latch_next = 1;
        if (vblank_condition) window_row_next = 0;
        else if (active_delayed && !window_active) window_row_next = window_row + 1'b1;
        if (window_reset) window_column_next = 0;
        else if (window_active && background_load) window_column_next = window_column + 1'b1;
    end
    `DFF_RST_EN(y_matched, y_matched_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(xy_delayed, xy_delayed_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(active_latch, active_latch_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(active_delayed, window_active, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(window_row, window_row_next, clk_sys, gb_tick, disabled_reset, 8'd0)
    `DFF_RST_EN(window_column, window_column_next, clk_sys, gb_tick, disabled_reset, 5'd0)
    `N2M_ASSERT_KNOWN(window_state_known, clk_sys, reset,
        {y_matched, xy_delayed, active_latch, active_delayed, window_row, window_column})
endmodule
