`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Copyright (c) 2015 Till Harbaum <till@harbaum.org>
// SPDX-License-Identifier: GPL-3.0-or-later
// Derived from pinned sprites.v. upstream.json records local changes; see
// GPL-3.0.txt and THIRD_PARTY.md. No local OAM memory or extra-sprite helpers.
module n2m_ppu_objects (
    input var logic clk_sys,
    input var logic reset,
    input var logic gb_tick,
    input var logic lcd_on,
    input var logic size16,
    input var logic object_enable,
    input var logic [7:0] line_y,
    input var logic [7:0] pixel_position,
    input var logic scan_reset,
    input var logic fetch_mode,
    input var logic fetch_phase1,
    input var logic fetch_done,
    input var logic dma_active,
    input var logic [15:0] oam_data,
    input var logic oam_valid,
    output logic [6:0] oam_pair_address,
    output logic [1:0] oam_phase,
    output logic [5:0] scan_index,
    output logic scan_active,
    output logic scan_done,
    output logic object_found,
    output logic [10:0] tile_row_address,
    output logic [7:0] object_attributes,
    output logic [3:0] selected_index,
    output logic fault
);
    logic [7:0] x_position [0:9];
    logic [7:0] x_position_next [0:9];
    logic [3:0] row_offset [0:9];
    logic [3:0] row_offset_next [0:9];
    logic [5:0] oam_index [0:9];
    logic [5:0] oam_index_next [0:9];
    logic [5:0] scan_index_next, delayed_index, delayed_index_next;
    logic [3:0] object_count, object_count_next;
    logic scan_enabled, scan_enabled_next, scan_half, scan_half_next;
    logic delayed_half, delayed_half_next, old_fetch_done, old_fetch_done_next;
    logic [7:0] captured_low, captured_high;
    logic [7:0] object_height;
    logic [3:0] fetch_row;
    logic [9:0] x_matches;
    logic on_line, save_entry, capture_scan, capture_fetch, missing, state_enable;
    integer i;
    integer k;
    genvar slot;

    assign object_height = size16 ? 8'd16 : 8'd8;
    assign on_line = line_y + 8'd16 >= captured_low
        && line_y + 8'd16 < captured_low + object_height;
    assign scan_done = scan_index == 6'd40;
    assign scan_active = lcd_on && !scan_done && scan_enabled && !scan_reset && !fault;
    assign save_entry = delayed_half && scan_enabled && on_line;
    assign capture_scan = scan_active && scan_half && !dma_active;
    assign capture_fetch = object_found && fetch_phase1;
    assign missing = gb_tick && !oam_valid && (capture_scan || capture_fetch);
    assign state_enable = gb_tick && !fault && !missing;
    assign object_found = (|x_matches) && fetch_mode && object_enable && lcd_on && !fault;
    assign object_attributes = captured_high;
    assign fetch_row = captured_high[6] ? ~row_offset[selected_index] : row_offset[selected_index];
    assign tile_row_address = size16 ? {captured_low[7:1], fetch_row}
        : {captured_low, fetch_row[2:0]};
    assign oam_phase = reset || fault ? 2'd0 : scan_active ? 2'd1 : object_found ? 2'd2 : 2'd0;
    assign oam_pair_address = scan_active ? {scan_index, 1'b0}
        : {oam_index[selected_index], 1'b1};
    always_comb begin
        selected_index = 4'd9;
        x_matches = '0;
        for (i = 9; i >= 0; i = i - 1) begin
            x_matches[i] = i < object_count && x_position[i] == pixel_position;
            if (x_matches[i]) selected_index = 4'(i);
        end
    end
    always_comb begin
        scan_index_next = scan_index;
        delayed_index_next = delayed_index;
        object_count_next = object_count;
        scan_enabled_next = scan_enabled;
        scan_half_next = scan_half;
        delayed_half_next = delayed_half;
        old_fetch_done_next = old_fetch_done;
        for (k = 0; k < 10; k = k + 1) begin
            x_position_next[k] = x_position[k];
            row_offset_next[k] = row_offset[k];
            oam_index_next[k] = oam_index[k];
        end
        if (scan_reset || !lcd_on) begin
            object_count_next = 0;
            scan_index_next = lcd_on ? 6'd0 : 6'd1;
            scan_half_next = 0;
            delayed_half_next = 0;
            scan_enabled_next = scan_reset;
            old_fetch_done_next = 0;
            for (k = 0; k < 10; k = k + 1) begin
                x_position_next[k] = 8'hff;
                row_offset_next[k] = 0;
                oam_index_next[k] = 0;
            end
        end else begin
            if (!scan_done) begin
                if (scan_half) begin
                    scan_index_next = scan_index + 1'b1;
                    delayed_index_next = scan_index;
                end
                scan_half_next = !scan_half;
            end
            delayed_half_next = scan_half;
            if (save_entry && object_count < 4'd10) begin
                oam_index_next[object_count] = delayed_index;
                x_position_next[object_count] = captured_high;
                row_offset_next[object_count] = line_y[3:0] - captured_low[3:0];
                object_count_next = object_count + 1'b1;
            end
            old_fetch_done_next = fetch_done;
            if (!old_fetch_done && fetch_done && (|x_matches))
                x_position_next[selected_index] = 8'hff;
        end
    end
    `DFF_RST_EN(scan_index, scan_index_next, clk_sys, state_enable, reset, 6'd0)
    `DFF_RST_EN(delayed_index, delayed_index_next, clk_sys, state_enable, reset, 6'd0)
    `DFF_RST_EN(object_count, object_count_next, clk_sys, state_enable, reset, 4'd0)
    `DFF_RST_EN(scan_enabled, scan_enabled_next, clk_sys, state_enable, reset, 1'b0)
    `DFF_RST_EN(scan_half, scan_half_next, clk_sys, state_enable, reset, 1'b0)
    `DFF_RST_EN(delayed_half, delayed_half_next, clk_sys, state_enable, reset, 1'b0)
    `DFF_RST_EN(old_fetch_done, old_fetch_done_next, clk_sys, state_enable, reset, 1'b0)
    `DFF_RST_EN(captured_low, oam_data[7:0], clk_sys, state_enable && (capture_scan || capture_fetch), reset, 8'd0)
    `DFF_RST_EN(captured_high, oam_data[15:8], clk_sys, state_enable && (capture_scan || capture_fetch), reset, 8'd0)
    `DFF_RST(fault, fault || missing, clk_sys, reset)
    generate
        for (slot = 0; slot < 10; slot = slot + 1) begin : retained_objects
            `DFF_RST_EN(x_position[slot], x_position_next[slot], clk_sys, state_enable, reset, 8'hff)
            `DFF_RST_EN(row_offset[slot], row_offset_next[slot], clk_sys, state_enable, reset, 4'd0)
            `DFF_RST_EN(oam_index[slot], oam_index_next[slot], clk_sys, state_enable, reset, 6'd0)
        end
    endgenerate
    `N2M_ASSERT(object_count_range, clk_sys, reset, object_count <= 4'd10)
    `N2M_ASSERT(scan_index_range, clk_sys, reset, scan_index <= 6'd40)
    `N2M_ASSERT_NEVER(oam_response_missing, clk_sys, reset, missing)
endmodule
