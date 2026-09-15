`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// SDRAM bring-up board image: the ported controller on the DE10-Lite DRAM pins
// with the UART endpoint's SDRAM_WRITE/SDRAM_READ line commands, so the host
// memory test can run without the loader. Contract:
// wiki/src/rtl/storage/MAS_sdram.md. No core, VGA or joypad is present.
module sdram_proof #(
`ifdef N2M_SDRAM_BUILD_ID
    parameter logic [127:0] BUILD_ID = `N2M_SDRAM_BUILD_ID
`else
    parameter logic [127:0] BUILD_ID = 128'd0
`endif
) (
    input var logic clk_reference,
    input var logic board_reset_n,
    input var logic uart_rx,
    output logic uart_tx,
    output logic [9:0] leds,
    output logic [12:0] DRAM_ADDR,
    output logic [1:0] DRAM_BA,
    output logic DRAM_CAS_N,
    output logic DRAM_CKE,
    output logic DRAM_CLK,
    output logic DRAM_CS_N,
    inout tri [15:0] DRAM_DQ,
    output logic DRAM_DQML,
    output logic DRAM_DQMH,
    output logic DRAM_RAS_N,
    output logic DRAM_WE_N
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
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic [7:0] effective_buttons;
    n2m_input_pkg::input_update_t effective_update;
    logic sdram_initialized;
    logic sdram_idle;
    logic sdram_request_valid;
    logic sdram_request_write;
    logic [n2m_sdram_pkg::SDRAM_ADDRESS_BITS-1:0] sdram_request_address;
    logic [n2m_sdram_pkg::SDRAM_LINE_BITS-1:0] sdram_request_data;
    logic sdram_request_ready;
    logic sdram_response_valid;
    logic [n2m_sdram_pkg::SDRAM_LINE_BITS-1:0] sdram_response_data;
    logic activity;
    logic [4:0] line_count;
    logic [23:0] pixel_heartbeat;

    // The same system and pixel PLLs as the composed image. clk_pix has one
    // consumer, the LEDR5 heartbeat, so the pixel PLL output and its checked
    // reset chain stay in the fit and the clock inventory is unchanged.
    n2m_clocking u_clocking (
        .clk_reference, .clk_sys(clk_sys), .board_reset_n(board_reset_n), .clk_pix(clk_pix),
        .reset_sys(reset_sys), .reset_pix(reset_pix), .ready(ready)
    );
    n2m_timebase u_timebase (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .pause_request(pause_request),
        .gb_tick(gb_tick), .paused(paused)
    );
    assign physical_commit = 1'b0;
    assign physical_buttons = '0;
    n2m_uart u_uart (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .uart_rx(uart_rx), .uart_tx(uart_tx), .build_id(BUILD_ID),
        .gb_tick(gb_tick), .paused(paused), .core_initialized(1'b0), .instruction_complete(1'b0),
        .retirement_valid(1'b0), .cpu_stopped(1'b0), .pause_request(pause_request), .core_reset(core_reset),
        .buttons(), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .effective_buttons(effective_buttons), .effective_update(effective_update), .input_source_observe(),
        .epoch(), .dot_count(), .retirement_count(), .profile(), .image_valid(), .endpoint_state(),
        .rom_write(), .rom_read(), .rom_address(), .rom_write_data(), .rom_read_data(8'd0), .rom_read_valid(1'b0),
        .snapshot_request(), .snapshot_ready(1'b0), .snapshot_done(1'b0), .snapshot_ok(1'b0),
        .snapshot_valid(1'b0), .snapshot_metadata('0), .frame_read(), .frame_address(),
        .frame_data(8'd0), .frame_valid(1'b0),
        .io_lcdc(8'd0), .io_stat(8'd0), .io_ly(8'd0), .io_lyc(8'd0), .io_scy(8'd0),
        .io_scx(8'd0), .io_wy(8'd0), .io_wx(8'd0), .io_bgp(8'd0), .io_obp0(8'd0),
        .io_obp1(8'd0), .io_div(8'd0), .io_tima(8'd0), .io_tma(8'd0), .io_tac(8'd0),
        .io_if(8'd0), .io_ie(8'd0),
        .peek_ready(1'b0), .peek_read(), .peek_select(), .peek_offset(), .peek_rdata(8'd0), .peek_valid(1'b0),
        .sdram_initialized(sdram_initialized), .sdram_request_valid(sdram_request_valid),
        .sdram_request_write(sdram_request_write), .sdram_request_address(sdram_request_address),
        .sdram_request_data(sdram_request_data), .sdram_request_ready(sdram_request_ready),
        .sdram_response_valid(sdram_response_valid), .sdram_response_data(sdram_response_data),
        // No loader profile in this image: the host bridge is the only requester.
        .loader_copy_busy(1'b0), .loader_swap_busy(1'b0), .engine_invalidate(1'b0), .engine_publish(1'b0),
        .engine_profile(8'd0), .library_status(32'd0), .library_key1(32'd0), .engine_pause(1'b0),
        .engine_reset_request(1'b0), .engine_reset_accept(), .engine_reset_done(), .host_session(),
        .host_port_busy(), .library_return()
    );
    n2m_sdram_ctrl u_sdram (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .request_valid(sdram_request_valid), .request_write(sdram_request_write),
        .request_address(sdram_request_address), .request_data(sdram_request_data),
        .request_ready(sdram_request_ready), .response_valid(sdram_response_valid),
        .response_data(sdram_response_data), .idle(sdram_idle), .initialized(sdram_initialized),
        .DRAM_ADDR(DRAM_ADDR), .DRAM_BA(DRAM_BA), .DRAM_CAS_N(DRAM_CAS_N), .DRAM_CKE(DRAM_CKE),
        .DRAM_CLK(DRAM_CLK), .DRAM_CS_N(DRAM_CS_N), .DRAM_DQ(DRAM_DQ), .DRAM_DQML(DRAM_DQML),
        .DRAM_DQMH(DRAM_DQMH), .DRAM_RAS_N(DRAM_RAS_N), .DRAM_WE_N(DRAM_WE_N)
    );
    // LEDR9 clocking ready, LEDR8 SDRAM initialized, LEDR7 controller idle,
    // LEDR6 toggles on every accepted line, LEDR5 is the pixel-clock
    // heartbeat (about 1.5 Hz), LEDR4-0 count accepted lines.
    `DFF_RST_EN(activity, !activity, clk_sys, sdram_request_valid && sdram_request_ready, reset_sys, 1'b0)
    `DFF_RST_EN(line_count, line_count + 5'd1, clk_sys, sdram_request_valid && sdram_request_ready, reset_sys, 5'd0)
    `DFF_ARST_VAL(pixel_heartbeat, pixel_heartbeat + 24'd1, clk_pix, reset_pix, 24'd0)
    assign leds = {ready, sdram_initialized, sdram_idle, activity, pixel_heartbeat[23], line_count};
endmodule
