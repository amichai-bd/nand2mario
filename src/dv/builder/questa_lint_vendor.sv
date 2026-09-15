// Questa compile-gate stand-ins for vendor units Quartus generates or installs
// during `fpga build`. Empty bodies with the instantiated ports and parameters:
// the gate binds repository RTL to these ports and claims no vendor behavior.
// tools/n2m/lint.py requires exactly these four units, in this order.
`timescale 1ns/1ps
module n2m_system_pll (
    input  logic inclk0,
    input  logic areset,
    output logic c0,
    output logic locked
);
endmodule

module n2m_pixel_pll (
    input  logic inclk0,
    input  logic areset,
    output logic c0,
    output logic locked
);
endmodule

module n2m_adc_pll (
    input  logic inclk0,
    input  logic areset,
    output logic c0,
    output logic locked
);
endmodule

module altera_modular_adc_control #(
    parameter int clkdiv = 1,
    parameter int tsclkdiv = 0,
    parameter int tsclksel = 0,
    parameter int prescalar = 0,
    parameter int refsel = 0,
    parameter string device_partname_fivechar_prefix = "10M50",
    parameter int is_this_first_or_second_adc = 1,
    parameter logic [16:0] analog_input_pin_mask = 17'h0,
    parameter int hard_pwd = 0,
    parameter int dual_adc_mode = 0,
    parameter int enable_usr_sim = 0,
    parameter int reference_voltage_sim = 0,
    parameter string simfilename_ch0 = "",
    parameter string simfilename_ch1 = "",
    parameter string simfilename_ch2 = "",
    parameter string simfilename_ch3 = "",
    parameter string simfilename_ch4 = "",
    parameter string simfilename_ch5 = "",
    parameter string simfilename_ch6 = "",
    parameter string simfilename_ch7 = "",
    parameter string simfilename_ch8 = "",
    parameter string simfilename_ch9 = "",
    parameter string simfilename_ch10 = "",
    parameter string simfilename_ch11 = "",
    parameter string simfilename_ch12 = "",
    parameter string simfilename_ch13 = "",
    parameter string simfilename_ch14 = "",
    parameter string simfilename_ch15 = "",
    parameter string simfilename_ch16 = ""
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        clk_in_pll_c0,
    input  logic        clk_in_pll_locked,
    input  logic        cmd_valid,
    input  logic [4:0]  cmd_channel,
    input  logic        cmd_sop,
    input  logic        cmd_eop,
    input  logic        sync_ready,
    output logic        cmd_ready,
    output logic        rsp_valid,
    output logic [4:0]  rsp_channel,
    output logic [11:0] rsp_data,
    output logic        rsp_sop,
    output logic        rsp_eop,
    output logic        sync_valid
);
endmodule
