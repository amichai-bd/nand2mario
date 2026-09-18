// Elaboration stand-ins, not models, for the vendor units Quartus generates or
// installs during `fpga build`. Port- and parameter-compatible empty bodies:
// `lint questa` binds repository RTL to these ports and claims no vendor
// behavior. Only that command compiles this file; it is in no synthesis source
// set. tools/n2m/lint.py requires exactly these eight units, in this order.
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

// The Cyclone V pair the Altera PLL IP generates: a different reference and
// reset port name from ALTPLL's, and the outclk_0 the wrapper reads.
module n2m_system_pll_cyclonev (
    input  logic refclk,
    input  logic rst,
    output logic outclk_0,
    output logic locked
);
endmodule

module n2m_pixel_pll_cyclonev (
    input  logic refclk,
    input  logic rst,
    output logic outclk_0,
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

// Installed Intel megafunction behind n2m_intel_ram outside VERILATOR builds.
module altsyncram #(
    parameter string intended_device_family = "MAX 10",
    parameter string ram_block_type = "AUTO",
    parameter string operation_mode = "BIDIR_DUAL_PORT",
    parameter string lpm_type = "altsyncram",
    parameter int width_a = 8,
    parameter int widthad_a = 10,
    parameter int numwords_a = 1024,
    parameter int width_b = 8,
    parameter int widthad_b = 10,
    parameter int numwords_b = 1024,
    parameter int width_byteena_a = 1,
    parameter int width_byteena_b = 1,
    parameter int byte_size = 8,
    parameter string address_reg_b = "CLOCK0",
    parameter string rdcontrol_reg_b = "CLOCK0",
    parameter string indata_reg_b = "CLOCK0",
    parameter string wrcontrol_wraddress_reg_b = "CLOCK0",
    parameter string byteena_reg_b = "CLOCK0",
    parameter string outdata_reg_a = "UNREGISTERED",
    parameter string outdata_reg_b = "UNREGISTERED",
    parameter string clock_enable_input_a = "BYPASS",
    parameter string clock_enable_input_b = "BYPASS",
    parameter string clock_enable_output_a = "BYPASS",
    parameter string clock_enable_output_b = "BYPASS",
    parameter string read_during_write_mode_port_a = "NEW_DATA_NO_NBE_READ",
    parameter string read_during_write_mode_port_b = "NEW_DATA_NO_NBE_READ",
    parameter string read_during_write_mode_mixed_ports = "OLD_DATA",
    parameter string power_up_uninitialized = "FALSE",
    parameter string init_file = "UNUSED"
) (
    input  logic                       clock0,
    input  logic                       clock1,
    input  logic                       clocken0,
    input  logic                       clocken1,
    input  logic                       clocken2,
    input  logic                       clocken3,
    input  logic                       aclr0,
    input  logic                       aclr1,
    input  logic [widthad_a-1:0]       address_a,
    input  logic [width_a-1:0]         data_a,
    input  logic                       wren_a,
    input  logic                       rden_a,
    input  logic [width_byteena_a-1:0] byteena_a,
    input  logic                       addressstall_a,
    output logic [width_a-1:0]         q_a,
    input  logic [widthad_b-1:0]       address_b,
    input  logic [width_b-1:0]         data_b,
    input  logic                       wren_b,
    input  logic                       rden_b,
    input  logic [width_byteena_b-1:0] byteena_b,
    input  logic                       addressstall_b,
    output logic [width_b-1:0]         q_b,
    output logic [2:0]                 eccstatus
);
endmodule

// Installed Intel On-Chip Flash IP behind n2m_flash_reader outside VERILATOR
// builds; the builder copies its four pinned source files into the attempt.
module altera_onchip_flash #(
    parameter string DEVICE_FAMILY = "MAX 10",
    parameter string PART_NAME = "Unknown",
    parameter string IS_DUAL_BOOT = "False",
    parameter string IS_ERAM_SKIP = "False",
    parameter string IS_COMPRESSED_IMAGE = "False",
    parameter string INIT_FILENAME = "",
    parameter string DEVICE_ID = "08",
    parameter string INIT_FILENAME_SIM = "",
    parameter int PARALLEL_MODE = 0,
    parameter int READ_AND_WRITE_MODE = 0,
    parameter int WRAPPING_BURST_MODE = 0,
    parameter int AVMM_CSR_DATA_WIDTH = 32,
    parameter int AVMM_DATA_DATA_WIDTH = 32,
    parameter int AVMM_DATA_ADDR_WIDTH = 20,
    parameter int AVMM_DATA_BURSTCOUNT_WIDTH = 13,
    parameter int FLASH_DATA_WIDTH = 32,
    parameter int FLASH_ADDR_WIDTH = 23,
    parameter int FLASH_SEQ_READ_DATA_COUNT = 2,
    parameter int FLASH_READ_CYCLE_MAX_INDEX = 3,
    parameter int FLASH_ADDR_ALIGNMENT_BITS = 1,
    parameter int FLASH_RESET_CYCLE_MAX_INDEX = 28,
    parameter int FLASH_BUSY_TIMEOUT_CYCLE_MAX_INDEX = 112,
    parameter int FLASH_ERASE_TIMEOUT_CYCLE_MAX_INDEX = 40603248,
    parameter int FLASH_WRITE_TIMEOUT_CYCLE_MAX_INDEX = 35382,
    parameter int MIN_VALID_ADDR = 1,
    parameter int MAX_VALID_ADDR = 1,
    parameter int MIN_UFM_VALID_ADDR = 1,
    parameter int MAX_UFM_VALID_ADDR = 1,
    parameter int SECTOR1_START_ADDR = 1,
    parameter int SECTOR1_END_ADDR = 1,
    parameter int SECTOR2_START_ADDR = 1,
    parameter int SECTOR2_END_ADDR = 1,
    parameter int SECTOR3_START_ADDR = 1,
    parameter int SECTOR3_END_ADDR = 1,
    parameter int SECTOR4_START_ADDR = 1,
    parameter int SECTOR4_END_ADDR = 1,
    parameter int SECTOR5_START_ADDR = 1,
    parameter int SECTOR5_END_ADDR = 1,
    parameter int SECTOR_READ_PROTECTION_MODE = 31,
    parameter int SECTOR1_MAP = 1,
    parameter int SECTOR2_MAP = 1,
    parameter int SECTOR3_MAP = 1,
    parameter int SECTOR4_MAP = 1,
    parameter int SECTOR5_MAP = 1,
    parameter int ADDR_RANGE1_END_ADDR = 1,
    parameter int ADDR_RANGE2_END_ADDR = 1,
    parameter int ADDR_RANGE1_OFFSET = 1,
    parameter int ADDR_RANGE2_OFFSET = 1,
    parameter int ADDR_RANGE3_OFFSET = 1
) (
    input  logic                                  clock,
    input  logic                                  reset_n,
    input  logic                                  avmm_data_read,
    input  logic                                  avmm_data_write,
    input  logic [AVMM_DATA_ADDR_WIDTH-1:0]       avmm_data_addr,
    input  logic [AVMM_DATA_DATA_WIDTH-1:0]       avmm_data_writedata,
    input  logic [AVMM_DATA_BURSTCOUNT_WIDTH-1:0] avmm_data_burstcount,
    output logic                                  avmm_data_waitrequest,
    output logic                                  avmm_data_readdatavalid,
    output logic [AVMM_DATA_DATA_WIDTH-1:0]       avmm_data_readdata,
    input  logic                                  avmm_csr_read,
    input  logic                                  avmm_csr_write,
    input  logic                                  avmm_csr_addr,
    input  logic [AVMM_CSR_DATA_WIDTH-1:0]        avmm_csr_writedata,
    output logic [AVMM_CSR_DATA_WIDTH-1:0]        avmm_csr_readdata
);
endmodule
