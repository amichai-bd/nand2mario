`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Copyright (c) 2015 Till Harbaum <till@harbaum.org>
// SPDX-License-Identifier: GPL-3.0-or-later
// Selected video.v position/enable logic; owner fine-scroll latch adaptation.
// Provenance: upstream.json. Terms: GPL-3.0.txt and THIRD_PARTY.md.
module n2m_ppu_position (
    input var logic clk_sys,
    input var logic reset,
    input var logic gb_tick,
    input var logic lcd_on,
    input var logic fine_latch,
    input var logic line_reset,
    input var logic mode3,
    input var logic background_first_done,
    input var logic window_first,
    input var logic object_found,
    input var logic [2:0] shift_count,
    input var logic [2:0] fine_scx,
    output logic [7:0] raw_x,
    output logic [7:0] source_x,
    output logic background_paused,
    output logic advance,
    output logic pixel_end,
    output logic source_event
);
    logic [2:0] fine_scroll;
    logic fine_sampled, sample_fine;
    logic scroll_done, scroll_done_next, scroll_end, paused, disabled_reset;
    logic [7:0] raw_x_next;
    assign disabled_reset = reset || !lcd_on;
    assign sample_fine = fine_latch && !fine_sampled && !line_reset && lcd_on;
    assign pixel_end = raw_x == 8'd167;
    assign background_paused = !background_first_done || window_first || object_found || pixel_end;
    assign scroll_end = !background_paused && shift_count == fine_scroll && !scroll_done;
    assign paused = background_paused || !(scroll_done || scroll_end);
    assign advance = !paused;
    assign source_x = raw_x - 8'd8;
    // The terminal pixel is sampled without shifting beyond rawX167.
    assign source_event = lcd_on && mode3
        && ((!paused && raw_x >= 8'd8) || (pixel_end && !object_found));
    always_comb begin
        raw_x_next = raw_x;
        scroll_done_next = scroll_done;
        if (line_reset) raw_x_next = 0;
        else if (!paused) raw_x_next = raw_x + 1'b1;
        if (!mode3) scroll_done_next = 0;
        else if (scroll_end) scroll_done_next = 1;
    end
    `DFF_RST_EN(raw_x, raw_x_next, clk_sys, gb_tick, disabled_reset, 8'd0)
    `DFF_RST_EN(scroll_done, scroll_done_next, clk_sys, gb_tick, disabled_reset, 1'b0)
    `DFF_RST_EN(fine_scroll, fine_scx, clk_sys, gb_tick && sample_fine, reset, 3'd0)
    `DFF_RST_EN(fine_sampled, !(line_reset || !lcd_on), clk_sys,
        gb_tick && (line_reset || !lcd_on || sample_fine), reset, 1'b0)
    `N2M_ASSERT(pixel_position_range, clk_sys, reset, raw_x <= 8'd167)
    `N2M_ASSERT(source_position_range, clk_sys, reset, !source_event || source_x < 8'd160)
endmodule
