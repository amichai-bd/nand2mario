`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// DE10-Nano UART endpoint image: the qualified endpoint (wiki/src/rtl/uart/MAS_uart.md)
// behind this board's Cyclone V clocking, with `uart_rx`/`uart_tx` on GPIO_0 and
// KEY[0] as reset. Board pins and the header wiring: wiki/src/de10-nano-board.md.
// There is no core, no video and no storage here: every other endpoint input is
// tied off, so the host commands that need them are refused rather than faked.
// A passing fit is placement and timing evidence only; nothing has been
// programmed onto a DE10-Nano.
module nano_uart_proof #(
`ifdef N2M_NANO_UART_BUILD_ID
    parameter logic [127:0] BUILD_ID = `N2M_NANO_UART_BUILD_ID
`else
    parameter logic [127:0] BUILD_ID = 128'd0
`endif
) (
    input var logic clk_reference,
    input var logic board_reset_n,
    input var logic uart_rx,
    output logic uart_tx,
    output logic [7:0] leds
);
    logic clk_sys;
    logic clk_pix;
    logic reset_sys;
    logic reset_pix;
    logic ready;
    logic core_reset;
    logic pause_request;
    logic gb_tick;
    logic paused;
    logic [7:0] endpoint_state;
    logic [7:0] effective_buttons;
    n2m_input_pkg::input_update_t effective_update;
    logic transmit_idle;
    logic transmit_start;
    logic activity;
    logic [2:0] byte_count;
    logic [23:0] pixel_heartbeat;

    // The board's own system and pixel PLLs. clk_pix has one consumer, the
    // LED[3] heartbeat, so the pixel PLL and its checked reset chain stay in the
    // fit and the clock inventory is the clocking proof's.
    n2m_clocking_cyclonev u_clocking (
        .clk_reference(clk_reference), .board_reset_n(board_reset_n), .clk_sys(clk_sys),
        .clk_pix(clk_pix), .reset_sys(reset_sys), .reset_pix(reset_pix), .ready(ready)
    );
    n2m_timebase u_timebase (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(pause_request), .gb_tick(gb_tick), .paused(paused)
    );
    n2m_uart u_uart (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .uart_rx(uart_rx), .uart_tx(uart_tx), .build_id(BUILD_ID),
        .gb_tick(gb_tick), .paused(paused), .core_initialized(1'b0), .instruction_complete(1'b0),
        .retirement_valid(1'b0), .cpu_stopped(1'b0), .pause_request(pause_request), .core_reset(core_reset),
        .buttons(), .physical_commit(1'b0), .physical_buttons(8'd0),
        .effective_buttons(effective_buttons), .effective_update(effective_update), .input_source_observe(),
        .epoch(), .dot_count(), .retirement_count(), .profile(), .image_valid(),
        .endpoint_state(endpoint_state),
        .rom_write(), .rom_read(), .rom_address(), .rom_write_data(), .rom_read_data(8'd0), .rom_read_valid(1'b0),
        .snapshot_request(), .snapshot_ready(1'b0), .snapshot_done(1'b0), .snapshot_ok(1'b0),
        .snapshot_valid(1'b0), .snapshot_metadata('0), .frame_read(), .frame_address(),
        .frame_data(8'd0), .frame_valid(1'b0),
        .io_lcdc(8'd0), .io_stat(8'd0), .io_ly(8'd0), .io_lyc(8'd0), .io_scy(8'd0),
        .io_scx(8'd0), .io_wy(8'd0), .io_wx(8'd0), .io_bgp(8'd0), .io_obp0(8'd0),
        .io_obp1(8'd0), .io_div(8'd0), .io_tima(8'd0), .io_tma(8'd0), .io_tac(8'd0),
        .io_if(8'd0), .io_ie(8'd0),
        .peek_ready(1'b0), .peek_read(), .peek_select(), .peek_offset(), .peek_rdata(8'd0), .peek_valid(1'b0),
        // No SDRAM on this board's fabric: the endpoint's memory commands never
        // become ready, so the host's SDRAM test waits rather than reporting.
        .sdram_initialized(1'b0), .sdram_request_valid(), .sdram_request_write(),
        .sdram_request_address(), .sdram_request_data(), .sdram_request_ready(1'b0),
        .sdram_response_valid(1'b0), .sdram_response_data('0),
        // No loader profile in this image: the host bridge is the only requester.
        .loader_copy_busy(1'b0), .loader_swap_busy(1'b0), .engine_invalidate(1'b0), .engine_publish(1'b0),
        .engine_profile(8'd0), .library_status(32'd0), .library_key1(32'd0), .engine_pause(1'b0),
        .engine_reset_request(1'b0), .boot_run(1'b0), .engine_reset_accept(), .engine_reset_done(),
        .host_session(), .host_loading(), .host_port_busy(), .library_return()
    );
    // LED[7] clocking ready, LED[6] toggles on every byte the endpoint answers
    // with, LED[5:4] the endpoint state, LED[3] the pixel-clock heartbeat (about
    // 1.5 Hz), LED[2:0] count answered bytes. The transmitter idles high, so its
    // falling edge is one start bit; an answered packet moves LED[6] at least
    // once, which is the whole legibility claim.
    `DFF_ARST_VAL(transmit_idle, uart_tx, clk_sys, reset_sys, 1'b1)
    assign transmit_start = transmit_idle && !uart_tx;
    `DFF_RST_EN(activity, !activity, clk_sys, transmit_start, reset_sys, 1'b0)
    `DFF_RST_EN(byte_count, byte_count + 3'd1, clk_sys, transmit_start, reset_sys, 3'd0)
    `DFF_ARST_VAL(pixel_heartbeat, pixel_heartbeat + 24'd1, clk_pix, reset_pix, 24'd0)
    assign leds = {ready, activity, endpoint_state[1:0], pixel_heartbeat[23], byte_count};
endmodule
