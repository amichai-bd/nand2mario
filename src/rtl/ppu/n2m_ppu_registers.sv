`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Copyright (c) 2015 Till Harbaum <till@harbaum.org>
// SPDX-License-Identifier: GPL-3.0-or-later
// Selected video.v register adaptation; upstream.json records local changes.
// See GPL-3.0.txt and THIRD_PARTY.md. Generated schema owns addresses/reset fill.
module n2m_ppu_registers (
    input var logic clk_sys,
    input var logic reset,
    input var logic gb_tick,
    input var logic io_commit,
    input var logic io_write,
    input var logic [15:0] io_address,
    input var logic [7:0] io_wdata,
    input var logic [7:0] ly,
    input var logic [1:0] mode,
    input var logic coincidence,
    input var logic [1:0] quarter_phase,
    output logic io_selected,
    output logic [7:0] io_rdata,
    output logic [7:0] lcdc,
    output logic [7:0] scy,
    output logic [7:0] scx,
    output logic [7:0] lyc,
    output logic [7:0] bgp,
    output logic [7:0] obp0,
    output logic [7:0] obp1,
    output logic [7:0] render_bgp,
    output logic [7:0] render_obp0,
    output logic [7:0] render_obp1,
    output logic [7:0] wy,
    output logic [7:0] wx,
    output logic [3:0] stat_enable,
    output logic [7:0] stat_observe,
    output logic stat_write,
    output logic lyc_write,
    output logic lcd_enable,
    output logic lcd_disable
);
    logic write_commit, lcdc_write, palette_write, palette_pending;
    logic [1:0] palette_id, palette_id_next;
    logic [7:0] palette_conflict, palette_old;
    assign palette_write = write_commit && (io_address == n2m_interfaces_pkg::GB_REG_BGP
        || io_address == n2m_interfaces_pkg::GB_REG_OBP0 || io_address == n2m_interfaces_pkg::GB_REG_OBP1);
    always_comb begin
        palette_id_next = 2'd0;
        palette_old = bgp;
        case (io_address)
            n2m_interfaces_pkg::GB_REG_OBP0: begin palette_id_next = 2'd1; palette_old = obp0; end
            n2m_interfaces_pkg::GB_REG_OBP1: begin palette_id_next = 2'd2; palette_old = obp1; end
            default: begin end
        endcase
    end
    // A normal write updates readback now. The following dot samples the DMG
    // old|new conflict, even if no visible pixel is emitted on that dot.
    `DFF_RST_EN(palette_pending, palette_write, clk_sys, gb_tick, reset, 1'b0)
    `DFF_RST_EN(palette_id, palette_id_next, clk_sys, palette_write, reset, 2'd0)
    `DFF_RST_EN(palette_conflict, palette_old | io_wdata, clk_sys, palette_write, reset, 8'd0)
    assign render_bgp = palette_pending && palette_id == 2'd0 ? palette_conflict : bgp;
    assign render_obp0 = palette_pending && palette_id == 2'd1 ? palette_conflict : obp0;
    assign render_obp1 = palette_pending && palette_id == 2'd2 ? palette_conflict : obp1;
    `N2M_ASSERT(ppu_palette_conflict_id, clk_sys, reset, !palette_pending || palette_id < 2'd3)
    `N2M_ASSERT_KNOWN(ppu_palette_conflict_known, clk_sys, reset,
        {palette_pending, palette_id, palette_conflict})
    // Host observation of STAT. Same composition the CPU reads, with bit 7
    // left zero: the host reports held storage, not CPU read bit stuffing.
    assign stat_observe = {1'b0, stat_enable, coincidence, mode};
    assign write_commit = gb_tick && io_commit && io_write && !reset;
    assign lcdc_write = write_commit && io_address == n2m_interfaces_pkg::GB_REG_LCDC;
    assign lyc_write = write_commit && io_address == n2m_interfaces_pkg::GB_REG_LYC;
    assign stat_write = write_commit && io_address == n2m_interfaces_pkg::GB_REG_STAT;
    assign lcd_enable = lcdc_write && !lcdc[7] && io_wdata[7];
    assign lcd_disable = lcdc_write && lcdc[7] && !io_wdata[7];
    always_comb begin
        io_selected = 1;
        io_rdata = 8'hff;
        case (io_address)
            n2m_interfaces_pkg::GB_REG_LCDC: io_rdata = lcdc;
            n2m_interfaces_pkg::GB_REG_STAT: io_rdata = {1'b1, stat_enable, coincidence, mode};
            n2m_interfaces_pkg::GB_REG_SCY: io_rdata = scy;
            n2m_interfaces_pkg::GB_REG_SCX: io_rdata = scx;
            n2m_interfaces_pkg::GB_REG_LY: io_rdata = ly;
            n2m_interfaces_pkg::GB_REG_LYC: io_rdata = lyc;
            n2m_interfaces_pkg::GB_REG_BGP: io_rdata = bgp;
            n2m_interfaces_pkg::GB_REG_OBP0: io_rdata = obp0;
            n2m_interfaces_pkg::GB_REG_OBP1: io_rdata = obp1;
            n2m_interfaces_pkg::GB_REG_WY: io_rdata = wy;
            n2m_interfaces_pkg::GB_REG_WX: io_rdata = wx;
            default: io_selected = 0;
        endcase
    end
    `DFF_RST_EN(lcdc, io_wdata, clk_sys, lcdc_write, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(scy, io_wdata, clk_sys, write_commit && io_address == n2m_interfaces_pkg::GB_REG_SCY, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(scx, io_wdata, clk_sys, write_commit && io_address == n2m_interfaces_pkg::GB_REG_SCX, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(lyc, io_wdata, clk_sys, write_commit && io_address == n2m_interfaces_pkg::GB_REG_LYC, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(bgp, io_wdata, clk_sys, write_commit && io_address == n2m_interfaces_pkg::GB_REG_BGP, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(obp0, io_wdata, clk_sys, write_commit && io_address == n2m_interfaces_pkg::GB_REG_OBP0, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(obp1, io_wdata, clk_sys, write_commit && io_address == n2m_interfaces_pkg::GB_REG_OBP1, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(wy, io_wdata, clk_sys, write_commit && io_address == n2m_interfaces_pkg::GB_REG_WY, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(wx, io_wdata, clk_sys, write_commit && io_address == n2m_interfaces_pkg::GB_REG_WX, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(stat_enable, io_wdata[6:3], clk_sys, stat_write, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[6:3])
    `N2M_ASSERT_NEVER(ppu_commit_requires_tick, clk_sys, reset, io_commit && !gb_tick)
    `N2M_ASSERT(ppu_commit_quarter_alignment, clk_sys, reset,
        !io_commit || !lcdc[7] || quarter_phase == 2'd3)
endmodule
