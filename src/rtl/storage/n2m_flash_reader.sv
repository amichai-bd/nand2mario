// Line reader over the MAX 10 On-Chip Flash IP. Contract:
// wiki/src/rtl/storage/MAS_flash_library.md#on-chip-flash-ip-boundary.
//
// One line request at a time: the accepted flash word becomes one Avalon-MM
// read of burstcount 4 at the IP's 0-based data address, the four words are
// collected in order and published for one clock, then the line holds until
// the next acceptance. Every register is in clk_sys. Synthesis instantiates
// the installed altera_onchip_flash with the parameters its hw.tcl derives for
// the 10M50DAF484C7G in the read-only parallel incrementing-burst, single
// compressed image configuration; Verilator predefines VERILATOR and selects
// the repository double n2m_sim_onchip_flash instead. No writer is connected:
// the data slave write port and the control slave are tied off.
`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

module n2m_flash_reader #(
    // Quartus assembles this file into the .pof user range; empty leaves the
    // flash uninitialized. The library builder names the image (#676).
    parameter string INIT_FILENAME = ""
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic line_valid,
    input var logic [n2m_flash_pkg::FLASH_WORD_BITS-1:0] line_word,
    output logic line_ready,
    output logic line_data_valid,
    output logic [n2m_flash_pkg::FLASH_LINE_BITS-1:0] line_data
);
    import n2m_flash_pkg::*;

    flash_reader_state_t state, state_next;
    logic accept;
    logic avmm_read;
    logic avmm_write;
    logic [FLASH_AVMM_ADDR_BITS-1:0] avmm_address;
    logic [31:0] avmm_writedata;
    logic [FLASH_AVMM_BURST_BITS-1:0] avmm_burstcount;
    logic avmm_waitrequest;
    logic avmm_readdatavalid;
    logic [31:0] avmm_readdata;
    logic csr_read;
    logic csr_write;
    logic csr_address;
    logic [31:0] csr_writedata;
    logic [31:0] csr_readdata;

    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, FLASH_RESET_STATE)

    assign line_ready = !reset_sys && state.phase == FLASH_IDLE;
    assign accept = line_valid && line_ready;
    assign line_data_valid = !reset_sys && state.phase == FLASH_PUBLISH;
    assign line_data = state.line;

    assign avmm_read = state.phase == FLASH_ISSUE;
    assign avmm_address = state.address;
    assign avmm_burstcount = FLASH_BURST_COUNT;
    assign avmm_write = 1'b0;
    assign avmm_writedata = '0;
    assign csr_read = 1'b0;
    assign csr_write = 1'b0;
    assign csr_address = 1'b0;
    assign csr_writedata = '0;

    always_comb begin
        state_next = state;
        case (state.phase)
            FLASH_IDLE: begin
                if (accept) begin
                    state_next.address = flash_avmm_address(line_word);
                    state_next.word = '0;
                    state_next.phase = FLASH_ISSUE;
                end
            end
            FLASH_ISSUE: begin
                // The read is held until the IP samples it without waitrequest.
                if (!avmm_waitrequest) state_next.phase = FLASH_DATA;
            end
            FLASH_DATA: begin
                if (avmm_readdatavalid) begin
                    state_next.line[int'(state.word) * 32 +: 32] = avmm_readdata;
                    state_next.word = state.word + 2'd1;
                    if (state.word == 2'd3) state_next.phase = FLASH_PUBLISH;
                end
            end
            FLASH_PUBLISH: state_next.phase = FLASH_IDLE;
            default: state_next = FLASH_RESET_STATE;
        endcase
    end

`ifdef VERILATOR
    n2m_sim_onchip_flash #(
        .AVMM_DATA_ADDR_WIDTH(FLASH_AVMM_ADDR_BITS),
        .AVMM_DATA_BURSTCOUNT_WIDTH(FLASH_AVMM_BURST_BITS)
    ) u_flash (
        .clock(clk_sys), .reset_n(!reset_sys),
        .avmm_data_read(avmm_read), .avmm_data_write(avmm_write), .avmm_data_addr(avmm_address),
        .avmm_data_writedata(avmm_writedata), .avmm_data_burstcount(avmm_burstcount),
        .avmm_data_waitrequest(avmm_waitrequest), .avmm_data_readdatavalid(avmm_readdatavalid),
        .avmm_data_readdata(avmm_readdata)
    );
    assign csr_readdata = '1;
`else
    // Parameters as altera_onchip_flash_hw_proc.tcl derives them for the
    // 10M50DAF484C7G: parallel data interface, incrementing burst of 4,
    // UFM1/UFM0/CFM2/CFM1 read only (Avalon words 0x00000-0x2DFFF, flash
    // words 0x00800-0x2E7FF through ADDR_RANGE1_OFFSET), CFM0 hidden, single
    // compressed image, 25 MHz timeouts, 128-bit data register (4 words per
    // sequential read, read cycle index 5).
    altera_onchip_flash #(
        .DEVICE_FAMILY("MAX 10"),
        .PART_NAME("10M50DAF484C7G"),
        .IS_DUAL_BOOT("False"),
        .IS_ERAM_SKIP("True"),
        .IS_COMPRESSED_IMAGE("True"),
        .INIT_FILENAME(INIT_FILENAME),
        .DEVICE_ID("50"),
        .INIT_FILENAME_SIM(""),
        .PARALLEL_MODE(1),
        .READ_AND_WRITE_MODE(0),
        .WRAPPING_BURST_MODE(0),
        .AVMM_CSR_DATA_WIDTH(32),
        .AVMM_DATA_DATA_WIDTH(32),
        .AVMM_DATA_ADDR_WIDTH(FLASH_AVMM_ADDR_BITS),
        .AVMM_DATA_BURSTCOUNT_WIDTH(FLASH_AVMM_BURST_BITS),
        .FLASH_DATA_WIDTH(32),
        .FLASH_ADDR_WIDTH(23),
        .FLASH_SEQ_READ_DATA_COUNT(4),
        .FLASH_READ_CYCLE_MAX_INDEX(5),
        .FLASH_ADDR_ALIGNMENT_BITS(2),
        .FLASH_RESET_CYCLE_MAX_INDEX(6),
        .FLASH_BUSY_TIMEOUT_CYCLE_MAX_INDEX(30),
        .FLASH_ERASE_TIMEOUT_CYCLE_MAX_INDEX(8750000),
        .FLASH_WRITE_TIMEOUT_CYCLE_MAX_INDEX(7625),
        .MIN_VALID_ADDR(0),
        .MAX_VALID_ADDR(188415),
        .MIN_UFM_VALID_ADDR(0),
        .MAX_UFM_VALID_ADDR(188415),
        .SECTOR1_START_ADDR(0),
        .SECTOR1_END_ADDR(8191),
        .SECTOR2_START_ADDR(8192),
        .SECTOR2_END_ADDR(16383),
        .SECTOR3_START_ADDR(16384),
        .SECTOR3_END_ADDR(114687),
        .SECTOR4_START_ADDR(114688),
        .SECTOR4_END_ADDR(188415),
        .SECTOR5_START_ADDR(0),
        .SECTOR5_END_ADDR(0),
        .SECTOR_READ_PROTECTION_MODE(31),
        .SECTOR1_MAP(1),
        .SECTOR2_MAP(2),
        .SECTOR3_MAP(3),
        .SECTOR4_MAP(4),
        .SECTOR5_MAP(0),
        .ADDR_RANGE1_END_ADDR(188415),
        .ADDR_RANGE2_END_ADDR(188415),
        .ADDR_RANGE1_OFFSET(2048),
        .ADDR_RANGE2_OFFSET(0),
        .ADDR_RANGE3_OFFSET(0)
    ) u_flash (
        .clock(clk_sys),
        .reset_n(!reset_sys),
        .avmm_data_read(avmm_read),
        .avmm_data_write(avmm_write),
        .avmm_data_addr(avmm_address),
        .avmm_data_writedata(avmm_writedata),
        .avmm_data_burstcount(avmm_burstcount),
        .avmm_data_waitrequest(avmm_waitrequest),
        .avmm_data_readdatavalid(avmm_readdatavalid),
        .avmm_data_readdata(avmm_readdata),
        .avmm_csr_read(csr_read),
        .avmm_csr_write(csr_write),
        .avmm_csr_addr(csr_address),
        .avmm_csr_writedata(csr_writedata),
        .avmm_csr_readdata(csr_readdata)
    );
`endif

    `N2M_ASSERT(FLASH_LINE_ALIGNED, clk_sys, reset_sys, accept |-> line_word[1:0] == 2'd0)
    `N2M_ASSERT(FLASH_LINE_RANGE, clk_sys, reset_sys,
        accept |-> line_word >= FLASH_DATA_BASE && line_word <= FLASH_USER_LAST)
    `N2M_ASSERT(FLASH_ONE_OUTSTANDING, clk_sys, reset_sys, accept |-> state.phase == FLASH_IDLE)
    `N2M_ASSERT(FLASH_DATA_EXPECTED, clk_sys, reset_sys, avmm_readdatavalid |-> state.phase == FLASH_DATA)
    `N2M_ASSERT(FLASH_NO_WRITE, clk_sys, reset_sys, !avmm_write && !csr_write)
    `N2M_ASSERT_KNOWN(FLASH_KNOWN_REQUEST, clk_sys, reset_sys, accept ? line_word : '0)
    `N2M_ASSERT_KNOWN(FLASH_KNOWN_DATA, clk_sys, reset_sys, avmm_readdatavalid ? avmm_readdata : '0)
endmodule
`default_nettype wire
