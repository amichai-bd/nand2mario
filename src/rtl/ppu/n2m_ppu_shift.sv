`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Copyright (c) 2015 Till Harbaum <till@harbaum.org>
// SPDX-License-Identifier: GPL-3.0-or-later
// Derived from the pinned video.v shift state in upstream.json. GPL-3.0.txt
// and THIRD_PARTY.md retain terms. Adaptation: explicit reset, DMG only,
// independent control ports, shared register/assertion macros.
module n2m_ppu_shift (
    input var logic clk_sys,
    input var logic reset,
    input var logic gb_tick,
    input var logic clear_line,
    input var logic advance,
    input var logic background_load,
    input var logic [7:0] background_low,
    input var logic [7:0] background_high,
    input var logic object_load,
    input var logic [7:0] object_low,
    input var logic [7:0] object_high,
    input var logic object_palette,
    input var logic object_behind,
    output logic [1:0] background_color,
    output logic [1:0] object_color,
    output logic palette_select,
    output logic behind_background
);
    logic [7:0] bg_low, bg_high, obj_low, obj_high, obj_palette, obj_behind;
    logic [7:0] bg_low_next, bg_high_next, obj_low_next, obj_high_next;
    logic [7:0] obj_palette_next, obj_behind_next;
    integer i;

    // Consumers sample these pre-edge bits at A. Loading and shifting below
    // change only the next pixel state; B must not recompute the captured pixel.
    assign background_color = {bg_high[7], bg_low[7]};
    assign object_color = {obj_high[7], obj_low[7]};
    assign palette_select = obj_palette[7];
    assign behind_background = obj_behind[7];
    always_comb begin
        i = 0;
        bg_low_next = bg_low;
        bg_high_next = bg_high;
        obj_low_next = obj_low;
        obj_high_next = obj_high;
        obj_palette_next = obj_palette;
        obj_behind_next = obj_behind;
        if (advance) begin
            bg_low_next = {bg_low[6:0], 1'b0};
            bg_high_next = {bg_high[6:0], 1'b0};
            obj_low_next = {obj_low[6:0], 1'b0};
            obj_high_next = {obj_high[6:0], 1'b0};
            obj_palette_next = {obj_palette[6:0], 1'b0};
            obj_behind_next = {obj_behind[6:0], 1'b0};
        end
        if (background_load) begin
            bg_low_next = background_low;
            bg_high_next = background_high;
        end
        // Existing nontransparent objects win. The fetch controller presents
        // objects in DMG X/OAM priority order; raw zero remains replaceable.
        if (object_load) begin
            for (i = 0; i < 8; i = i + 1) begin
                if (!(obj_low[i] || obj_high[i])) begin
                    obj_low_next[i] = object_low[i];
                    obj_high_next[i] = object_high[i];
                    obj_palette_next[i] = object_palette;
                    obj_behind_next[i] = object_behind;
                end
            end
        end
        if (clear_line) begin
            bg_low_next = '0;
            bg_high_next = '0;
            obj_low_next = '0;
            obj_high_next = '0;
            obj_palette_next = '0;
            obj_behind_next = '0;
        end
    end
    `DFF_RST_EN(bg_low, bg_low_next, clk_sys, gb_tick, reset, 8'd0)
    `DFF_RST_EN(bg_high, bg_high_next, clk_sys, gb_tick, reset, 8'd0)
    `DFF_RST_EN(obj_low, obj_low_next, clk_sys, gb_tick, reset, 8'd0)
    `DFF_RST_EN(obj_high, obj_high_next, clk_sys, gb_tick, reset, 8'd0)
    `DFF_RST_EN(obj_palette, obj_palette_next, clk_sys, gb_tick, reset, 8'd0)
    `DFF_RST_EN(obj_behind, obj_behind_next, clk_sys, gb_tick, reset, 8'd0)
    `N2M_ASSERT_KNOWN(shift_state_known, clk_sys, reset,
        {bg_low, bg_high, obj_low, obj_high, obj_palette, obj_behind})
    `N2M_ASSERT_STABLE_WHEN(shift_without_tick_holds, clk_sys, reset,
        !gb_tick, {bg_low, bg_high, obj_low, obj_high, obj_palette, obj_behind})
endmodule
