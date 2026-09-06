`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Geometry authority: wiki/src/clocks-resets-cdc.md. Two-stage output latency.
module n2m_vga_scan (
    input logic clk_pix, reset_pix, display_valid,
    input logic [1:0] read_shade,
    output logic read_enable,
    output logic [14:0] read_address,
    output logic swap_boundary,
    output logic [9:0] video_x, video_y,
    output logic video_valid, video_active, video_image,
    output logic [3:0] red, green, blue,
    output logic hsync_n, vsync_n
);
    logic [9:0] x, y, x_next, y_next;
    logic [9:0] x_q, y_q, x_out, y_out;
    logic active_q, image_q, valid_q, hs_q, vs_q;
    logic active_out, image_out, valid_out, hs_out, vs_out;
    logic [3:0] gray, gray_out;
    logic [9:0] source_x, source_y;
    wire active;
    assign active = x < 10'd640 && y < 10'd480;
    wire image_area;
    assign image_area = x >= 10'd80 && x < 10'd560 &&
                      y >= 10'd24 && y < 10'd456;
    always_comb begin
        x_next = x == 10'd799 ? 10'd0 : x + 10'd1;
        y_next = y;
        if (x == 10'd799) y_next = y == 10'd524 ? 10'd0 : y + 10'd1;
        source_x = (x - 10'd80) / 10'd3;
        source_y = (y - 10'd24) / 10'd3;
        read_address = 15'(source_y * 16'd160 + source_x);
        if (!image_area) read_address = 15'd0;
        case (read_shade)
            2'd0: gray = 4'hf;
            2'd1: gray = 4'ha;
            2'd2: gray = 4'h5;
            default: gray = 4'h0;
        endcase
    end
    assign read_enable = !reset_pix && display_valid && image_area;
    assign swap_boundary = !reset_pix && x == 10'd0 && y == 10'd480;
    `DFF_RST(x, x_next, clk_pix, reset_pix)
    `DFF_RST(y, y_next, clk_pix, reset_pix)
    `DFF_RST(x_q, x, clk_pix, reset_pix)
    `DFF_RST(y_q, y, clk_pix, reset_pix)
    `DFF_RST(active_q, active, clk_pix, reset_pix)
    `DFF_RST(image_q, read_enable, clk_pix, reset_pix)
    `DFF_RST(valid_q, 1'b1, clk_pix, reset_pix)
    `DFF_RST_VAL(hs_q, !(x >= 10'd656 && x < 10'd752), clk_pix, reset_pix, 1'b1)
    `DFF_RST_VAL(vs_q, !(y >= 10'd490 && y < 10'd492), clk_pix, reset_pix, 1'b1)
    `DFF_RST(x_out, x_q, clk_pix, reset_pix)
    `DFF_RST(y_out, y_q, clk_pix, reset_pix)
    `DFF_RST(active_out, active_q, clk_pix, reset_pix)
    `DFF_RST(image_out, image_q, clk_pix, reset_pix)
    `DFF_RST(valid_out, valid_q, clk_pix, reset_pix)
    `DFF_RST_VAL(hs_out, hs_q, clk_pix, reset_pix, 1'b1)
    `DFF_RST_VAL(vs_out, vs_q, clk_pix, reset_pix, 1'b1)
    `DFF_RST(gray_out, image_q ? gray : 4'h0, clk_pix, reset_pix)
    assign video_x = x_out;
    assign video_y = y_out;
    assign video_valid = valid_out && !reset_pix;
    assign video_active = active_out && video_valid;
    assign video_image = image_out && video_valid;
    assign red = video_valid ? gray_out : 4'h0;
    assign green = red;
    assign blue = red;
    assign hsync_n = video_valid ? hs_out : 1'b1;
    assign vsync_n = video_valid ? vs_out : 1'b1;
endmodule
