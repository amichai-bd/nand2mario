`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Copyright (c) 2015 Till Harbaum <till@harbaum.org>
// SPDX-License-Identifier: GPL-3.0-or-later
// Derived from pinned video.v; upstream.json records changes. See GPL-3.0.txt
// and THIRD_PARTY.md. DMG fetch state only; no platform/helper dependencies.
module n2m_ppu_fetch (
    input var logic clk_sys,
    input var logic reset,
    input var logic gb_tick,
    input var logic lcd_on,
    input var logic mode3,
    input var logic background_paused,
    input var logic window_start,
    input var logic window_xy_match,
    input var logic object_found,
    input var logic object_x_flip,
    input var logic [7:0] vram_data,
    input var logic vram_valid,
    output logic map_read,
    output logic background_low_read,
    output logic background_high_read,
    output logic object_low_read,
    output logic object_high_read,
    output logic [2:0] background_phase,
    output logic [2:0] object_phase,
    output logic background_done,
    output logic object_done,
    output logic background_first_done,
    output logic window_first,
    output logic [7:0] tile_index,
    output logic background_load,
    output logic [7:0] background_low,
    output logic [7:0] background_high,
    output logic object_load,
    output logic [7:0] object_low,
    output logic [7:0] object_high,
    output logic fault
);
    logic [2:0] background_phase_next, object_phase_next;
    logic [2:0] shift_count, shift_count_next;
    logic background_first_done_next, window_first_next;
    logic [7:0] tile_low, tile_high, object_plane_low;
    logic [7:0] object_data;
    logic shift_end, reload, capture_map, capture_low, capture_high;
    logic capture_object_low, capture_object_high, missing, state_enable;

    assign map_read = mode3 && lcd_on && !fault && !reset && background_phase[2:1] == 2'd0;
    assign background_low_read = mode3 && lcd_on && !fault && !reset && background_phase[2:1] == 2'd1;
    assign background_high_read = mode3 && lcd_on && !fault && !reset && background_phase[2:1] == 2'd2;
    assign object_low_read = mode3 && lcd_on && !fault && !reset && object_phase[2:1] == 2'd1;
    assign object_high_read = mode3 && lcd_on && !fault && !reset && object_phase[2:1] == 2'd2;
    assign background_done = background_phase >= 3'd5;
    assign object_done = object_found && object_phase >= 3'd5;
    assign shift_end = &shift_count;
    assign reload = (background_done && (!background_first_done || window_first))
        || (!background_paused && shift_end && !window_xy_match);
    assign capture_map = background_phase[0] && map_read;
    assign capture_low = background_phase[0] && background_low_read;
    assign capture_high = background_phase[0] && background_high_read;
    assign capture_object_low = object_phase[0] && object_low_read;
    assign capture_object_high = object_phase[0] && object_high_read;
    assign missing = gb_tick && !vram_valid && (capture_map || capture_low
        || capture_high || capture_object_low || capture_object_high);
    assign state_enable = gb_tick && !fault && !missing;
    assign object_data = object_x_flip
        ? {vram_data[0], vram_data[1], vram_data[2], vram_data[3],
           vram_data[4], vram_data[5], vram_data[6], vram_data[7]} : vram_data;
    assign background_load = mode3 && lcd_on && reload && !reset && !fault && !missing;
    assign background_low = tile_low;
    assign background_high = background_phase == 3'd5 ? vram_data : tile_high;
    assign object_load = capture_object_high && !fault && !missing;
    assign object_low = object_plane_low;
    assign object_high = object_data;

    always_comb begin
        background_phase_next = background_phase;
        object_phase_next = object_phase;
        shift_count_next = shift_count;
        background_first_done_next = background_first_done;
        window_first_next = window_first;
        if (background_phase != 3'd7) background_phase_next = background_phase + 1'b1;
        if (!mode3) background_first_done_next = 0;
        else if (background_done) background_first_done_next = 1;
        if (reload) begin
            shift_count_next = 0;
            background_phase_next = 0;
        end
        // Preserve source update ordering: this uses the old count even when
        // reload is also true. Window/mode exit below has final priority.
        if (!background_paused && !shift_end) shift_count_next = shift_count + 1'b1;
        if (object_found && background_done && !window_first && background_first_done)
            object_phase_next = object_phase + 1'b1;
        if (!object_found || object_done) object_phase_next = 0;
        if (window_start || !mode3) begin
            background_phase_next = 0;
            shift_count_next = 0;
        end
        if (!lcd_on || (window_first && background_done)) window_first_next = 0;
        else if (window_start) window_first_next = 1;
    end
    `DFF_RST_EN(background_phase, background_phase_next, clk_sys, state_enable, reset, 3'd0)
    `DFF_RST_EN(object_phase, object_phase_next, clk_sys, state_enable, reset, 3'd0)
    `DFF_RST_EN(shift_count, shift_count_next, clk_sys, state_enable, reset, 3'd0)
    `DFF_RST_EN(background_first_done, background_first_done_next, clk_sys, state_enable, reset, 1'b0)
    `DFF_RST_EN(window_first, window_first_next, clk_sys, state_enable, reset, 1'b0)
    `DFF_RST_EN(tile_index, vram_data, clk_sys, state_enable && capture_map, reset, 8'd0)
    `DFF_RST_EN(tile_low, vram_data, clk_sys, state_enable && capture_low, reset, 8'd0)
    `DFF_RST_EN(tile_high, vram_data, clk_sys, state_enable && capture_high, reset, 8'd0)
    `DFF_RST_EN(object_plane_low, object_data, clk_sys, state_enable && capture_object_low, reset, 8'd0)
    `DFF_RST(fault, fault || missing, clk_sys, reset)
    `N2M_ASSERT_KNOWN(fetch_state_known, clk_sys, reset,
        {background_phase, object_phase, shift_count, background_first_done, window_first, fault})
    `N2M_ASSERT_NEVER(fetch_response_missing, clk_sys, reset, missing)
endmodule
