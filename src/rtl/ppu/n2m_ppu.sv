`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// SPDX-License-Identifier: GPL-3.0-or-later
// Composes adapted Till Harbaum DMG renderer logic; source notices and original
// project integration changes are recorded in upstream.json and THIRD_PARTY.md.
module n2m_ppu (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic [31:0] epoch,
    input var logic [63:0] dot_before,
    input var logic io_commit,
    input var logic io_write,
    input var logic [15:0] io_address,
    input var logic [7:0] io_wdata,
    output logic io_selected,
    output logic [7:0] io_rdata,
    output logic vram_request,
    output logic [12:0] vram_address,
    input var logic [7:0] vram_data,
    input var logic vram_valid,
    output logic [6:0] oam_pair_address,
    output logic [1:0] oam_phase,
    output logic [5:0] oam_scan_index,
    input var logic [15:0] oam_data,
    input var logic oam_valid,
    input var logic dma_active,
    output logic vram_cpu_allow,
    output logic oam_cpu_allow,
    output logic oam_cpu_read_allow,
    output logic stat_condition,
    output logic vblank_condition,
    output logic stat_rise,
    output logic vblank_rise,
    output logic fault,
    output logic source_valid,
    output logic source_start,
    output logic [1:0] source_shade,
    output logic [7:0] source_x,
    output logic [7:0] source_y,
    output logic [31:0] source_epoch,
    output logic [63:0] source_dot,
    output logic source_abort,
    output logic blank_assert,
    output logic source_display_eligible
);
    logic reset, lcd_enable, lcd_disable, stat_write;
    logic [7:0] lcdc, scy, scx, lyc, bgp, obp0, obp1, wy, wx, ly;
    logic [3:0] stat_enable;
    logic [6:0] line_quarter;
    logic [1:0] quarter_phase, mode;
    logic coincidence, mode3, mode3_end, line_reset, scan_done, scan_active;
    logic object_found, pixel_end, background_paused, advance, source_event;
    logic [7:0] raw_x, pixel_x, window_row;
    logic [4:0] window_column;
    logic window_active, window_start, xy_match, background_first_done, window_first;
    logic [2:0] background_phase, object_phase, shift_count;
    logic background_done, object_done, background_load, object_load;
    logic map_read, background_low_read, background_high_read, object_low_read, object_high_read;
    logic [7:0] tile_index, background_low, background_high, object_low, object_high;
    logic [7:0] object_attributes;
    logic [3:0] selected_index;
    logic [10:0] object_row_address;
    logic [1:0] object_oam_phase;
    logic fetch_fault, object_fault, fetch_fault_now, object_fault_now, fault_now;
    logic [1:0] background_color, object_color, shade;
    logic palette_select, behind_background;
    logic [7:0] background_y, background_x;
    logic [9:0] map_offset;
    logic [2:0] tile_row;
    logic tile_map, tile_bank;
    logic pixel_capture, abort_capture, event_capture, complete_capture;
    logic pending_pixel, captured_start, pending_abort, pending_blank;
    logic first_frame_blank, fault_seen, vblank_history;
    logic lyc_write;
    logic [7:0] render_bgp, render_obp0, render_obp1;
    logic [7:0] readable_ly;
    logic early_oam_read_block;
    assign reset = reset_sys || core_reset;
    assign fault = fetch_fault || object_fault;
    assign fault_now = fetch_fault_now || object_fault_now;
    n2m_ppu_registers registers (
        .clk_sys, .reset, .gb_tick, .io_commit, .io_write, .io_address, .io_wdata,
        .ly(readable_ly), .mode, .coincidence, .quarter_phase, .io_selected, .io_rdata,
        .lcdc, .scy, .scx, .lyc, .bgp, .obp0, .obp1, .wy, .wx, .stat_enable,
        .stat_write, .lyc_write, .lcd_enable, .lcd_disable,
        .render_bgp, .render_obp0, .render_obp1
    );
    n2m_ppu_timing timing (
        .clk_sys, .reset, .gb_tick, .lcd_on(lcdc[7]), .lcd_disable, .ly_compare(lyc), .stat_enable, .stat_write, .lyc_write, .write_data(io_wdata),
        .scan_done, .scan_active, .pixel_end, .object_found, .line_quarter,
        .quarter_phase, .ly, .readable_ly, .coincidence, .mode, .mode3, .mode3_end,
        .line_reset, .stat_condition, .stat_rise, .vblank_condition
    );
    n2m_ppu_position position (
        .clk_sys, .reset, .gb_tick, .lcd_on(lcdc[7]),
        .fine_latch(mode3 && background_phase == 0 && !background_first_done),
        .line_reset, .mode3, .background_first_done, .window_first, .object_found,
        .shift_count, .fine_scx(scx[2:0]), .raw_x, .source_x(pixel_x),
        .background_paused, .advance, .pixel_end, .source_event
    );
    n2m_ppu_window window_control (
        .clk_sys, .reset, .gb_tick, .lcd_on(lcdc[7]), .window_enable(lcdc[5]),
        .wy, .wx, .ly, .raw_x, .quarter_phase, .line_reset, .vblank_condition,
        .background_paused, .background_load, .xy_match, .window_start,
        .window_active, .window_row, .window_column
    );
    n2m_ppu_fetch fetch (
        .clk_sys, .reset, .gb_tick, .lcd_on(lcdc[7]), .mode3, .background_paused,
        .window_start, .window_xy_match(xy_match), .object_found,
        .object_x_flip(object_attributes[5]), .vram_data, .vram_valid,
        .map_read, .background_low_read, .background_high_read,
        .object_low_read, .object_high_read, .background_phase, .object_phase,
        .shift_count, .background_done, .object_done, .background_first_done,
        .window_first, .tile_index, .background_load, .background_low, .background_high,
        .object_load, .object_low, .object_high, .fault(fetch_fault), .fault_now(fetch_fault_now)
    );
    n2m_ppu_objects objects (
        .clk_sys, .reset, .gb_tick, .lcd_on(lcdc[7]), .size16(lcdc[2]),
        .object_enable(lcdc[1]), .line_y(ly), .pixel_position(raw_x),
        .scan_reset(line_reset), .fetch_mode(mode3), .fetch_phase1(object_phase == 1),
        .fetch_done(object_done), .dma_active, .oam_data, .oam_valid,
        .oam_pair_address, .oam_phase(object_oam_phase), .scan_index(oam_scan_index),
        .scan_active, .scan_done, .object_found, .tile_row_address(object_row_address),
        .object_attributes, .selected_index, .fault(object_fault), .fault_now(object_fault_now)
    );
    n2m_ppu_shift shift_planes (
        .clk_sys, .reset, .gb_tick, .clear_line(line_reset), .advance,
        .background_load, .background_low, .background_high,
        .object_load, .object_low, .object_high,
        .object_palette(object_attributes[4]), .object_behind(object_attributes[7]),
        .background_color, .object_color, .palette_select, .behind_background
    );
    n2m_ppu_mix mixer (
        .background_enable(lcdc[0]), .object_enable(lcdc[1]),
        .background_color, .object_color, .object_behind_background(behind_background),
        .object_palette_select(palette_select), .background_palette(render_bgp),
        .object_palette0(render_obp0), .object_palette1(render_obp1), .shade
    );
    assign background_y = ly + scy;
    assign background_x = raw_x + scx;
    assign map_offset = window_active ? {window_row[7:3], window_column}
        : {background_y[7:3], background_x[7:3]};
    assign tile_row = window_active ? window_row[2:0] : background_y[2:0];
    assign tile_map = window_active ? lcdc[6] : lcdc[3];
    assign tile_bank = !lcdc[4] && !tile_index[7];
    assign vram_request = !reset && !fault_now && (map_read || background_low_read
        || background_high_read || object_low_read || object_high_read);
    assign vram_address = map_read ? {2'b11, tile_map, map_offset}
        : background_low_read ? {tile_bank, tile_index, tile_row, 1'b0}
        : background_high_read ? {tile_bank, tile_index, tile_row, 1'b1}
        : object_low_read ? {1'b0, object_row_address, 1'b0}
        : {1'b0, object_row_address, 1'b1};
    assign oam_phase = reset || fault_now ? 2'd0 : object_oam_phase;
    assign vram_cpu_allow = !mode3;
    assign oam_cpu_allow = !(scan_active || mode3 || dma_active);
    // Legal T4 before the next ordinary scan blocks reads while writes remain
    // allowed. Use renderer LY, not the exceptional CPU-readable LY153 value.
    assign early_oam_read_block = lcdc[7] && ly < 8'd144
        && line_quarter == 7'd113 && quarter_phase == 2'd3;
    assign oam_cpu_read_allow = oam_cpu_allow && !early_oam_read_block;
    assign vblank_rise = vblank_condition && !vblank_history && !reset;
    `DFF_RST(vblank_history, vblank_condition, clk_sys, reset)
    assign pixel_capture = gb_tick && source_event && !lcd_disable && !fault_now && !reset;
    assign abort_capture = !reset && ((gb_tick && lcd_disable) || (fault_now && !fault_seen));
    assign event_capture = pixel_capture || abort_capture;
    assign complete_capture = pixel_capture && pixel_x == 8'd159 && ly == 8'd143;
    `DFF_RST(fault_seen, fault_seen || fault_now, clk_sys, reset)
    `DFF_RST(pending_pixel, pixel_capture, clk_sys, reset)
    `DFF_RST(pending_abort, abort_capture, clk_sys, reset_sys)
    `DFF_RST(pending_blank, gb_tick && lcd_disable, clk_sys, reset_sys)
    `DFF_RST_EN(captured_start, pixel_x == 0 && ly == 0, clk_sys, pixel_capture, reset, 1'b0)
    `DFF_RST_EN(source_shade, first_frame_blank ? 2'd0 : shade, clk_sys, pixel_capture, reset, 2'd0)
    `DFF_RST_EN(source_x, pixel_x, clk_sys, event_capture, reset, 8'd0)
    `DFF_RST_EN(source_y, ly, clk_sys, event_capture, reset, 8'd0)
    `DFF_RST_EN(source_epoch, epoch, clk_sys, event_capture, reset, 32'd0)
    `DFF_RST_EN(source_dot, dot_before + 64'd1, clk_sys, event_capture, reset, 64'd0)
    `DFF_RST_EN(source_display_eligible, !first_frame_blank, clk_sys, pixel_capture, reset, 1'b0)
    `DFF_RST_EN(first_frame_blank, lcd_enable, clk_sys,
        gb_tick && (lcd_enable || complete_capture), reset, 1'b1)
    assign source_valid = pending_pixel && !reset;
    assign source_start = source_valid && captured_start;
    assign source_abort = pending_abort && !reset_sys;
    assign blank_assert = pending_blank && !reset_sys;
    `N2M_ASSERT_NEVER(source_abort_priority, clk_sys, reset_sys, source_valid && source_abort)
    `N2M_ASSERT(source_coordinate_range, clk_sys, reset,
        !source_valid || (source_x < 8'd160 && source_y < 8'd144))
endmodule
