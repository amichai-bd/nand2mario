// Contract: wiki/src/rtl/display/MAS_display.md
`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
module dmg_tile_pixel (
    input var logic       clk,
    input var logic       reset,
    input var logic       enable,
    input var logic       valid_s0,
    input var logic [7:0] row_low_s0,
    input var logic [7:0] row_high_s0,
    input var logic [2:0] pixel_x_s0,
    input var logic [7:0] palette_s0,
    output logic       valid_s1,
    output logic [1:0] color_index_s1,
    output logic [1:0] shade_s1
);
    logic [2:0] bit_select_s0;
    logic [1:0] color_index_s0;
    logic [1:0] shade_s0;

    assign bit_select_s0 = 3'd7 - pixel_x_s0;
    assign color_index_s0 = {row_high_s0[bit_select_s0], row_low_s0[bit_select_s0]};
    assign shade_s0 = palette_s0[{color_index_s0, 1'b0} +: 2];

    `DFF_RST_EN(valid_s1, valid_s0, clk, enable, reset, 1'b0)
    `DFF_RST_EN(color_index_s1, valid_s0 ? color_index_s0 : 2'b00, clk, enable, reset, 2'b00)
    `DFF_RST_EN(shade_s1, valid_s0 ? shade_s0 : 2'b00, clk, enable, reset, 2'b00)
endmodule
`default_nettype wire
