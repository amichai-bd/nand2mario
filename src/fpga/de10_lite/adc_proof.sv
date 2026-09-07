`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Early structural proof: real ADC and its dedicated PLL, public observation.
module adc_proof (
    input logic clk_sys,
    input logic clk_adc_reference,
    input logic board_reset_n,
    output logic ready,
    output logic response_valid,
    output logic [1:0] response_channel,
    output logic [11:0] response_data
);
    logic clk_adc;
    logic pll_locked;
    logic pll_areset;
    logic reset_sys;
    logic reset_adc;
    logic command_ready;
    logic command_valid;
    logic [4:0] channel_q;
    logic [4:0] channel_next;
    logic waiting_q;
    logic waiting_next;
    logic [4:0] adc_response_channel;

    n2m_reset_control u_reset (
        .clk_reference(clk_sys), .clk_sys(clk_sys), .clk_pix(clk_adc),
        .board_reset_n(board_reset_n), .pll_locked(pll_locked),
        .pll_areset(pll_areset), .ready(ready),
        .reset_sys(reset_sys), .reset_pix(reset_adc)
    );
    assign command_valid = !reset_sys && !waiting_q;
    assign response_channel = adc_response_channel[1:0];
    always_comb begin
        channel_next = channel_q;
        waiting_next = waiting_q;
        if (command_valid && command_ready) waiting_next = 1'b1;
        if (response_valid) begin
            waiting_next = 1'b0;
            channel_next = channel_q == 5'd1 ? 5'd2 : 5'd1;
        end
    end
    `DFF_ARST_VAL(channel_q, channel_next, clk_sys, reset_sys, 5'd1)
    `DFF_ARST_VAL(waiting_q, waiting_next, clk_sys, reset_sys, 1'b0)

    n2m_adc_backend u_adc (
        .clk_sys(clk_sys), .clk_adc_reference(clk_adc_reference),
        .pll_areset(pll_areset), .reset_sys(reset_sys),
        .command_valid(command_valid), .command_channel(channel_q),
        .command_ready(command_ready), .response_valid(response_valid),
        .response_channel(adc_response_channel), .response_data(response_data),
        .clk_adc(clk_adc), .pll_locked(pll_locked)
    );
endmodule
