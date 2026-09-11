`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Physical input diagnostic; generated VGA pattern is not a Game Boy frame.
module controls_proof #(
`ifdef N2M_CONTROLS_BUILD_ID
    parameter logic [127:0] BUILD_ID = `N2M_CONTROLS_BUILD_ID
`else
    parameter logic [127:0] BUILD_ID = 128'd0
`endif
) (
    input var logic clk_reference,
    input var logic clk_adc_reference,
    input var logic board_reset_n,
    input var logic [3:0] buttons_n,
    input var logic uart_rx,
    output logic uart_tx,
    output logic [9:0] leds,
    output logic [3:0] red,
    output logic [3:0] green,
    output logic [3:0] blue,
    output logic hsync_n,
    output logic vsync_n,
    // Virtual proof observations retain the existing bridge CDC metadata paths.
    output logic ready,
    output logic paused,
    output logic [63:0] discard_count,
    output logic [63:0] repeat_count,
    output logic [63:0] display_sequence,
    output logic [31:0] display_epoch,
    output logic [63:0] observed_sequence,
    output logic [14:0] observed_index,
    output logic observed_complete
);
    logic clk_sys;
    logic clk_pix;
    logic reset_sys;
    logic reset_pix;
    logic clk_adc;
    logic adc_pll_reset;
    logic adc_pll_locked;
    logic adc_ready;
    logic adc_reset;
    logic adc_domain_reset;
    logic command_valid;
    logic [4:0] command_channel;
    logic command_ready;
    logic response_valid;
    logic [4:0] response_channel;
    logic [11:0] response_data;
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic fresh;
    logic adc_fault;
    logic [7:0] effective_buttons;
    logic [7:0] input_source;
    n2m_input_pkg::input_update_t effective_update;
    logic core_reset;
    logic pause_request;
    logic gb_tick;
    logic [7:0] joypad_buttons;
    logic [3:0] display_divider;
    logic display_sample;
    logic [14:0] pixel_index;
    logic [63:0] display_dot;
    logic [31:0] source_epoch;
    logic [1:0] shade;
    n2m_clocking u_clocking (
        .clk_reference, .clk_sys(clk_sys), .board_reset_n(board_reset_n), .clk_pix(clk_pix),
        .reset_sys(reset_sys), .reset_pix(reset_pix), .ready(ready)
    );
    // A system reset cancels the ADC generation as well as its sampler. ADC
    // lock loss alone resets only acquisition; buttons/UART/display stay live.
    n2m_reset_control u_adc_reset (
        .clk_reference(clk_reference), .clk_sys(clk_sys), .clk_pix(clk_adc), .board_reset_n(board_reset_n && !reset_sys),
        .pll_locked(adc_pll_locked), .pll_areset(adc_pll_reset), .ready(adc_ready),
        .reset_sys(adc_reset), .reset_pix(adc_domain_reset)
    );
    n2m_adc_backend u_adc (
        .clk_sys(clk_sys), .clk_adc_reference(clk_adc_reference), .pll_areset(adc_pll_reset),
        .reset_sys(adc_reset), .command_valid(command_valid), .command_channel(command_channel),
        .command_ready(command_ready), .response_valid(response_valid), .response_channel(response_channel),
        .response_data(response_data), .clk_adc(clk_adc), .pll_locked(adc_pll_locked)
    );
    n2m_physical_controls u_physical (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .gb_tick(gb_tick), .buttons_n(buttons_n),
        .adc_available(!adc_reset), .command_valid(command_valid), .command_channel(command_channel),
        .command_ready(command_ready), .response_valid(response_valid), .response_channel(response_channel),
        .response_data(response_data), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .adc_fresh(fresh), .adc_fault(adc_fault)
    );
    n2m_timebase u_timebase (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .pause_request(pause_request),
        .gb_tick(gb_tick), .paused(paused)
    );
    n2m_uart u_uart (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .uart_rx(uart_rx), .uart_tx(uart_tx), .build_id(BUILD_ID),
        .gb_tick(gb_tick), .paused(paused), .core_initialized(1'b0), .instruction_complete(1'b0),
        .retirement_valid(1'b0), .cpu_stopped(1'b0), .pause_request(pause_request), .core_reset(core_reset),
        .buttons(), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .effective_buttons(effective_buttons), .effective_update(effective_update), .input_source_observe(input_source),
        .epoch(), .dot_count(), .retirement_count(), .profile(), .image_valid(), .endpoint_state(),
        .rom_write(), .rom_read(), .rom_address(), .rom_write_data(), .rom_read_data(8'd0), .rom_read_valid(1'b0),
        .snapshot_request(), .snapshot_ready(1'b0), .snapshot_done(1'b0), .snapshot_ok(1'b0),
        .snapshot_valid(1'b0), .snapshot_metadata('0), .frame_read(), .frame_address(),
        .frame_data(8'd0), .frame_valid(1'b0),
        .io_lcdc(8'd0), .io_stat(8'd0), .io_ly(8'd0), .io_lyc(8'd0), .io_scy(8'd0),
        .io_scx(8'd0), .io_wy(8'd0), .io_wx(8'd0), .io_bgp(8'd0), .io_obp0(8'd0),
        .io_obp1(8'd0), .io_div(8'd0), .io_tima(8'd0), .io_tma(8'd0), .io_tac(8'd0),
        .io_if(8'd0), .io_ie(8'd0),
        .peek_read(), .peek_select(), .peek_offset(), .peek_rdata(8'd0), .peek_valid(1'b0)
    );
    n2m_joypad u_joypad (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .input_commit(effective_update.valid), .input_buttons(effective_update.buttons),
        .io_commit(1'b0), .io_write(1'b0), .io_address(16'hFF00), .io_wdata(8'd0),
        .io_selected(), .io_rdata(), .buttons_observe(joypad_buttons), .selected_active(), .request_event()
    );
    assign leds = {fresh, input_source == n2m_interfaces_pkg::INPUT_SOURCE_PHYSICAL, effective_buttons};
    // Diagnostic producer runs while the emulation timebase is paused. It
    // supplies synthetic shades only and is never reported as PPU observation.
    assign display_sample = display_divider == 4'd11;
    `DFF_ARST_VAL(display_divider, display_sample ? 4'd0 : display_divider + 4'd1, clk_sys, reset_sys, 4'd0)
    `DFF_RST_EN(pixel_index, pixel_index == 15'd23039 ? 15'd0 : pixel_index + 15'd1,
        clk_sys, display_sample, reset_sys || core_reset, 15'd0)
    `DFF_RST_EN(display_dot, display_dot + 64'd1, clk_sys, display_sample, reset_sys || core_reset, 64'd0)
    `DFF_RST_EN(source_epoch, source_epoch + 32'd1, clk_sys, core_reset, reset_sys, 32'd0)
    assign shade = pixel_index[1:0] ^ pixel_index[9:8] ^ joypad_buttons[1:0] ^
        joypad_buttons[3:2] ^ joypad_buttons[5:4] ^ joypad_buttons[7:6];
    n2m_frame_bridge u_bridge (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .clk_pix(clk_pix), .reset_pix(reset_pix),
        .source_valid(display_sample), .source_start(pixel_index == 0), .source_shade(shade),
        .source_dot(display_dot), .source_epoch(source_epoch), .source_abort(1'b0), .blank_assert(1'b0),
        .source_display_eligible(1'b1), .observe_abort(), .observe_valid(), .observe_complete(observed_complete),
        .observe_index(observed_index), .observe_shade(), .observe_epoch(), .observe_sequence(observed_sequence), .observe_dot(),
        .discard_count(discard_count), .repeat_count(repeat_count), .display_valid(), .display_sequence(display_sequence), .display_epoch(display_epoch),
        .video_x(), .video_y(), .video_valid(), .video_active(), .video_image(),
        .red(red), .green(green), .blue(blue), .hsync_n(hsync_n), .vsync_n(vsync_n)
    );
endmodule
