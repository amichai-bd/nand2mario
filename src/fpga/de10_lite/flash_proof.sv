`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Flash reader proof image: the installed On-Chip Flash IP behind
// n2m_flash_reader on the same system and pixel PLLs and reset bootstrap as
// the composed image, walked continuously over the user range so the whole
// read path stays in the fit. Contract: wiki/src/rtl/storage/MAS_flash_library.md.
// No UART, core or DRAM is present; the LEDs are the only observation.
module flash_proof (
    input var logic clk_reference,
    input var logic board_reset_n,
    output logic [9:0] leds
);
    import n2m_flash_pkg::*;
    logic clk_sys;
    logic clk_pix;
    logic reset_sys;
    logic reset_pix;
    logic ready;
    logic line_valid;
    logic [FLASH_WORD_BITS-1:0] line_word;
    logic [FLASH_WORD_BITS-1:0] line_word_next;
    logic line_ready;
    logic line_data_valid;
    logic [FLASH_LINE_BITS-1:0] line_data;
    logic [7:0] checksum;
    logic [7:0] checksum_next;
    logic wrap;
    logic activity;
    logic [23:0] pixel_heartbeat;
    int k;

    // clk_pix has one consumer, the LEDR6 heartbeat, so the pixel PLL output
    // and its checked reset chain stay in the fit and the clock inventory is
    // the composed image's.
    n2m_clocking u_clocking (
        .clk_reference, .clk_sys(clk_sys), .board_reset_n(board_reset_n), .clk_pix(clk_pix),
        .reset_sys(reset_sys), .reset_pix(reset_pix), .ready(ready)
    );
    n2m_flash_reader u_reader (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .line_valid(line_valid), .line_word(line_word),
        .line_ready(line_ready), .line_data_valid(line_data_valid), .line_data(line_data)
    );

    // Walk every aligned line of the user range, one request outstanding,
    // and fold each line into an eight-bit checksum shown on the LEDs.
    assign line_valid = 1'b1;
    assign wrap = line_word == FLASH_USER_LAST - 20'd3;
    assign line_word_next = wrap ? FLASH_DATA_BASE : line_word + 20'd4;
    always_comb begin
        checksum_next = checksum;
        for (k = 0; k < FLASH_LINE_BITS / 8; k = k + 1) checksum_next = checksum_next ^ line_data[k * 8 +: 8];
    end
    `DFF_RST_EN(line_word, line_word_next, clk_sys, line_valid && line_ready, reset_sys, FLASH_DATA_BASE)
    `DFF_RST_EN(checksum, checksum_next, clk_sys, line_data_valid, reset_sys, 8'd0)
    `DFF_RST_EN(activity, !activity, clk_sys, line_data_valid && wrap, reset_sys, 1'b0)
    `DFF_ARST_VAL(pixel_heartbeat, pixel_heartbeat + 24'd1, clk_pix, reset_pix, 24'd0)
    // LEDR9 clocking ready, LEDR8 reader ready, LEDR7 toggles on every pass
    // over the user range, LEDR6 the pixel-clock heartbeat (about 1.5 Hz),
    // LEDR5-0 the low checksum bits.
    assign leds = {ready, line_ready, activity, pixel_heartbeat[23], checksum[5:0]};
endmodule
