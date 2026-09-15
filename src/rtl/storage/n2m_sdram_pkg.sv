// SPDX-License-Identifier: MIT
// Ported from bui-bui src/rtl/mafia/sdram/mafia_sdram_pkg.sv (MIT, adapted
// from FPGA-MAFIA); see wiki/tools/provenance.md. Renamed and restyled for
// this repository; the constants are the contract in
// wiki/src/rtl/storage/MAS_sdram.md.
`timescale 1ns/1ps
package n2m_sdram_pkg;
    // ISSI IS42S16320D on the DE10-Lite at the 25 MHz system clock, CL2, BL8.
    localparam int SDRAM_CLOCK_HZ = 25000000;
    localparam int SDRAM_ADDRESS_BITS = 26;
    localparam int SDRAM_LINE_BITS = 128;
    localparam int SDRAM_POWERUP_CLOCKS = 5000;
    localparam int SDRAM_REFRESH_INTERVAL = 160;
    localparam int SDRAM_REFRESH_DEADLINE_CLOCKS = 195;
    localparam int SDRAM_CAS_LATENCY = 2;
    localparam int SDRAM_BURST_BEATS = 8;
    // A WAIT phase loaded with n-1 spends n clocks before the next command, so
    // these values produce tRP 3, tRCD 3, tRC 4, tWR 2 and tMRD 3 clocks.
    localparam int SDRAM_TRP = 2;
    localparam int SDRAM_TRCD = 2;
    localparam int SDRAM_TRC = 3;
    localparam int SDRAM_TWR = 2;
    localparam int SDRAM_TMRD = 2;
    // A[2:0]=011 BL8, A3=0 sequential, A[6:4]=010 CL2, A[8:7]=00, A9=0.
    localparam logic [12:0] SDRAM_MODE_VALUE = 13'h023;

    // Command on {RAS_N, CAS_N, WE_N} with CS_N low.
    typedef enum logic [2:0] {
        SDRAM_NOP_CMD = 3'b111,
        SDRAM_READ_CMD = 3'b101,
        SDRAM_WRITE_CMD = 3'b100,
        SDRAM_ACTIVATE_CMD = 3'b011,
        SDRAM_PRECHARGE_CMD = 3'b010,
        SDRAM_REFRESH_CMD = 3'b001,
        SDRAM_MODE_CMD = 3'b000
    } sdram_command_t;

    typedef enum logic [3:0] {
        SDRAM_POWERUP,
        SDRAM_INIT_PRECHARGE,
        SDRAM_INIT_REFRESH,
        SDRAM_MODE,
        SDRAM_WAIT,
        SDRAM_IDLE,
        SDRAM_ACTIVATE,
        SDRAM_READ,
        SDRAM_WRITE,
        SDRAM_RECOVERY,
        SDRAM_PRECHARGE,
        SDRAM_REFRESH,
        SDRAM_COMPLETE
    } sdram_phase_t;

    // The whole controller state is one record with one owner.
    typedef struct packed {
        sdram_phase_t phase;
        sdram_phase_t after_wait;
        logic [12:0] count;
        logic [7:0] refresh_age;
        logic [3:0] init_refreshes;
        logic initialized;
        logic write;
        logic [SDRAM_ADDRESS_BITS-1:0] address;
        logic [SDRAM_LINE_BITS-1:0] write_data;
        logic [SDRAM_LINE_BITS-1:0] read_data;
    } sdram_state_t;

    localparam sdram_state_t SDRAM_RESET_STATE = '{
        phase: SDRAM_POWERUP, after_wait: SDRAM_POWERUP, count: '0, refresh_age: '0,
        init_refreshes: '0, initialized: 1'b0, write: 1'b0, address: '0,
        write_data: '0, read_data: '0
    };

    // Device byte address mapping: bank a[25:24], row a[23:11], column a[10:1].
    function automatic logic [1:0] sdram_bank(input logic [SDRAM_ADDRESS_BITS-1:0] address);
        return address[25:24];
    endfunction

    function automatic logic [12:0] sdram_row(input logic [SDRAM_ADDRESS_BITS-1:0] address);
        return address[23:11];
    endfunction

    function automatic logic [9:0] sdram_column(input logic [SDRAM_ADDRESS_BITS-1:0] address);
        return address[10:1];
    endfunction
endpackage
