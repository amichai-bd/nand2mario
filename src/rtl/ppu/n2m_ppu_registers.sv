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
    output logic [7:0] wy,
    output logic [7:0] wx,
    output logic [3:0] stat_enable,
    output logic stat_write,
    output logic lcd_enable,
    output logic lcd_disable
);
    import n2m_interfaces_pkg::*;
    logic write_commit, lcdc_write;
    assign write_commit = gb_tick && io_commit && io_write && !reset;
    assign lcdc_write = write_commit && io_address == GB_REG_LCDC;
    assign stat_write = write_commit && io_address == GB_REG_STAT;
    assign lcd_enable = lcdc_write && !lcdc[7] && io_wdata[7];
    assign lcd_disable = lcdc_write && lcdc[7] && !io_wdata[7];
    always_comb begin
        io_selected = 1;
        io_rdata = 8'hff;
        case (io_address)
            GB_REG_LCDC: io_rdata = lcdc;
            GB_REG_STAT: io_rdata = {1'b1, stat_enable, coincidence, mode};
            GB_REG_SCY: io_rdata = scy;
            GB_REG_SCX: io_rdata = scx;
            GB_REG_LY: io_rdata = ly;
            GB_REG_LYC: io_rdata = lyc;
            GB_REG_BGP: io_rdata = bgp;
            GB_REG_OBP0: io_rdata = obp0;
            GB_REG_OBP1: io_rdata = obp1;
            GB_REG_WY: io_rdata = wy;
            GB_REG_WX: io_rdata = wx;
            default: io_selected = 0;
        endcase
    end
    `DFF_RST_EN(lcdc, io_wdata, clk_sys, lcdc_write, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(scy, io_wdata, clk_sys, write_commit && io_address == GB_REG_SCY, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(scx, io_wdata, clk_sys, write_commit && io_address == GB_REG_SCX, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(lyc, io_wdata, clk_sys, write_commit && io_address == GB_REG_LYC, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(bgp, io_wdata, clk_sys, write_commit && io_address == GB_REG_BGP, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(obp0, io_wdata, clk_sys, write_commit && io_address == GB_REG_OBP0, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(obp1, io_wdata, clk_sys, write_commit && io_address == GB_REG_OBP1, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(wy, io_wdata, clk_sys, write_commit && io_address == GB_REG_WY, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(wx, io_wdata, clk_sys, write_commit && io_address == GB_REG_WX, reset, PROFILE_PERIPHERAL_FILL)
    `DFF_RST_EN(stat_enable, io_wdata[6:3], clk_sys, stat_write, reset, PROFILE_PERIPHERAL_FILL[6:3])
    `N2M_ASSERT_NEVER(ppu_commit_requires_tick, clk_sys, reset, io_commit && !gb_tick)
    `N2M_ASSERT(ppu_commit_quarter_alignment, clk_sys, reset,
        !io_commit || !lcdc[7] || quarter_phase == 2'd3)
endmodule
