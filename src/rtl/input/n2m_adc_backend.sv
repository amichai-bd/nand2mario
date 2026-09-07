`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Installed Intel control core owns the hard ADC crossing; all public transfers
// occur in clk_sys. Contract: wiki/src/fpga-controls.md.
module n2m_adc_backend (
    input logic clk_sys,
    input logic clk_adc_reference,
    input logic pll_areset,
    input logic reset_sys,
    input logic command_valid,
    input logic [4:0] command_channel,
    output logic command_ready,
    output logic response_valid,
    output logic [4:0] response_channel,
    output logic [11:0] response_data,
    output logic clk_adc,
    output logic pll_locked
);
    logic response_sop;
    logic response_eop;
    logic sync_valid;

    n2m_adc_pll u_pll (
        .areset(pll_areset),
        .inclk0(clk_adc_reference),
        .c0(clk_adc),
        .locked(pll_locked)
    );

    altera_modular_adc_control #(
        .clkdiv(5),
        .tsclkdiv(0),
        .tsclksel(1),
        .prescalar(0),
        .refsel(1),
        .device_partname_fivechar_prefix("10M50"),
        .is_this_first_or_second_adc(1),
        .analog_input_pin_mask(17'h00006),
        .hard_pwd(0),
        .dual_adc_mode(0),
        .enable_usr_sim(0),
        // Match the installed IP generator's fixed-output simulation defaults.
        // The control HDL's placeholder filenames are not support assets.
        .simfilename_ch0(""),
        .simfilename_ch1(""),
        .simfilename_ch2(""),
        .simfilename_ch3(""),
        .simfilename_ch4(""),
        .simfilename_ch5(""),
        .simfilename_ch6(""),
        .simfilename_ch7(""),
        .simfilename_ch8(""),
        .simfilename_ch9(""),
        .simfilename_ch10(""),
        .simfilename_ch11(""),
        .simfilename_ch12(""),
        .simfilename_ch13(""),
        .simfilename_ch14(""),
        .simfilename_ch15(""),
        .simfilename_ch16("")
    ) u_control (
        .clk(clk_sys),
        .rst_n(!reset_sys),
        .clk_in_pll_c0(clk_adc),
        .clk_in_pll_locked(pll_locked),
        .cmd_valid(command_valid),
        .cmd_channel(command_channel),
        .cmd_sop(1'b1),
        .cmd_eop(1'b1),
        .sync_ready(1'b1),
        .cmd_ready(command_ready),
        .rsp_valid(response_valid),
        .rsp_channel(response_channel),
        .rsp_data(response_data),
        .rsp_sop(response_sop),
        .rsp_eop(response_eop),
        .sync_valid(sync_valid)
    );

    `N2M_ASSERT(adc_command_channel, clk_sys, reset_sys,
        !command_valid || command_channel == 5'd1 || command_channel == 5'd2)
    `N2M_ASSERT_KNOWN(adc_response_known, clk_sys, reset_sys,
        {response_valid, command_ready})
endmodule
