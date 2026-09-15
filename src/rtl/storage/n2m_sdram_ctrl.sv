// SPDX-License-Identifier: MIT
// License text: LICENSE-sdram-controller.txt beside this file.
// Ported from bui-bui src/rtl/mafia/sdram/mafia_sdram_ctrl.sv (MIT, adapted
// from FPGA-MAFIA); see wiki/tools/provenance.md. Contract:
// wiki/src/rtl/storage/MAS_sdram.md.
//
// One requester, one outstanding 16-byte line, fixed 25 MHz, CL2, sequential
// eight-beat bursts, explicit precharge after every access. Every register is
// in clk_sys; DRAM_CLK is the inverted system clock driven to the pin, so the
// device samples commands 20 ns after they change and read data launched at
// the device edge is captured at the following clk_sys edge.
`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

module n2m_sdram_ctrl #(
    // Default from the contract; a fixture lowers it only to prove the device
    // model's refresh deadline check.
    parameter int REFRESH_INTERVAL = n2m_sdram_pkg::SDRAM_REFRESH_INTERVAL
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic request_valid,
    input var logic request_write,
    input var logic [n2m_sdram_pkg::SDRAM_ADDRESS_BITS-1:0] request_address,
    input var logic [n2m_sdram_pkg::SDRAM_LINE_BITS-1:0] request_data,
    output logic request_ready,
    output logic response_valid,
    output logic [n2m_sdram_pkg::SDRAM_LINE_BITS-1:0] response_data,
    output logic idle,
    output logic initialized,
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
    import n2m_sdram_pkg::*;

    sdram_state_t state, state_next;
    sdram_command_t command;
    logic accept;
    logic drive_data;
    logic [15:0] write_beat;

    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, SDRAM_RESET_STATE)

    assign idle = !reset_sys && state.phase == SDRAM_IDLE;
    assign initialized = !reset_sys && state.initialized;
    assign request_ready = idle && int'(state.refresh_age) < REFRESH_INTERVAL;
    assign accept = request_valid && request_ready;
    assign response_valid = !reset_sys && state.phase == SDRAM_COMPLETE && !state.write;
    assign response_data = state.read_data;

    assign DRAM_CLK = ~clk_sys;
    assign DRAM_CKE = !reset_sys;
    assign DRAM_CS_N = reset_sys;
    assign {DRAM_RAS_N, DRAM_CAS_N, DRAM_WE_N} = command;
    assign DRAM_DQML = !state.initialized;
    assign DRAM_DQMH = !state.initialized;
    assign DRAM_DQ = drive_data && !reset_sys ? write_beat : 16'hzzzz;

    always_comb begin
        state_next = state;
        command = SDRAM_NOP_CMD;
        DRAM_ADDR = '0;
        DRAM_BA = sdram_bank(state.address);
        drive_data = 1'b0;
        write_beat = '0;
        // Age counts clocks since the last AUTO REFRESH once initialized and
        // saturates rather than wrapping.
        if (state.initialized && state.refresh_age != 8'hff)
            state_next.refresh_age = state.refresh_age + 8'd1;

        case (state.phase)
            SDRAM_POWERUP: begin
                // 5000 NOP clocks after reset release, then the first command.
                if (int'(state.count) == SDRAM_POWERUP_CLOCKS) begin
                    state_next.count = '0;
                    state_next.phase = SDRAM_INIT_PRECHARGE;
                end else state_next.count = state.count + 13'd1;
            end
            SDRAM_INIT_PRECHARGE, SDRAM_PRECHARGE: begin
                command = SDRAM_PRECHARGE_CMD;
                DRAM_ADDR[10] = 1'b1;
                state_next.count = 13'(SDRAM_TRP - 1);
                state_next.phase = SDRAM_WAIT;
                state_next.after_wait = state.initialized ? SDRAM_COMPLETE : SDRAM_INIT_REFRESH;
            end
            SDRAM_INIT_REFRESH, SDRAM_REFRESH: begin
                command = SDRAM_REFRESH_CMD;
                state_next.refresh_age = '0;
                state_next.count = 13'(SDRAM_TRC - 1);
                state_next.phase = SDRAM_WAIT;
                state_next.after_wait = SDRAM_IDLE;
                if (!state.initialized) begin
                    state_next.init_refreshes = state.init_refreshes + 4'd1;
                    state_next.after_wait = state.init_refreshes == 4'd7 ? SDRAM_MODE : SDRAM_INIT_REFRESH;
                end
            end
            SDRAM_MODE: begin
                command = SDRAM_MODE_CMD;
                DRAM_ADDR = SDRAM_MODE_VALUE;
                DRAM_BA = '0;
                state_next.count = 13'(SDRAM_TMRD - 1);
                state_next.phase = SDRAM_WAIT;
                state_next.after_wait = SDRAM_IDLE;
                state_next.initialized = 1'b1;
                state_next.refresh_age = '0;
            end
            SDRAM_WAIT: begin
                if (state.count == '0) state_next.phase = state.after_wait;
                else state_next.count = state.count - 13'd1;
            end
            SDRAM_IDLE: begin
                state_next.count = '0;
                // A due refresh wins over a request presented on the same edge.
                if (!request_ready) state_next.phase = SDRAM_REFRESH;
                else if (request_valid) begin
                    state_next.address = request_address;
                    state_next.write = request_write;
                    state_next.write_data = request_data;
                    state_next.phase = SDRAM_ACTIVATE;
                end
            end
            SDRAM_ACTIVATE: begin
                command = SDRAM_ACTIVATE_CMD;
                DRAM_ADDR = sdram_row(state.address);
                state_next.phase = SDRAM_WAIT;
                state_next.after_wait = state.write ? SDRAM_WRITE : SDRAM_READ;
                state_next.count = 13'(SDRAM_TRCD - 1);
            end
            SDRAM_READ: begin
                DRAM_ADDR[9:0] = sdram_column(state.address);
                if (state.count == '0) command = SDRAM_READ_CMD;
                // The device drives beat k after device edge READ+CL-1+k and
                // holds it through edge READ+CL+k (datasheet CAS latency), so
                // beat k is captured at the clk_sys edge ending clock 5+k.
                if (int'(state.count) >= SDRAM_CAS_LATENCY - 1 && int'(state.count) < SDRAM_CAS_LATENCY - 1 + SDRAM_BURST_BEATS)
                    state_next.read_data[(int'(state.count) - (SDRAM_CAS_LATENCY - 1)) * 16 +: 16] = DRAM_DQ;
                if (int'(state.count) == SDRAM_CAS_LATENCY + SDRAM_BURST_BEATS - 1) begin
                    state_next.phase = SDRAM_PRECHARGE;
                    state_next.count = '0;
                end else state_next.count = state.count + 13'd1;
            end
            SDRAM_WRITE: begin
                DRAM_ADDR[9:0] = sdram_column(state.address);
                if (state.count == '0) command = SDRAM_WRITE_CMD;
                drive_data = 1'b1;
                write_beat = state.write_data[int'(state.count) * 16 +: 16];
                if (int'(state.count) == SDRAM_BURST_BEATS - 1) begin
                    state_next.phase = SDRAM_RECOVERY;
                    state_next.count = 13'(SDRAM_TWR - 1);
                end else state_next.count = state.count + 13'd1;
            end
            SDRAM_RECOVERY: begin
                if (state.count == '0) state_next.phase = SDRAM_PRECHARGE;
                else state_next.count = state.count - 13'd1;
            end
            SDRAM_COMPLETE: state_next.phase = SDRAM_IDLE;
            default: state_next = SDRAM_RESET_STATE;
        endcase
    end

    // Acceptance history sampled with the assertions: at the edge ending
    // contract clock k after acceptance, bit k-1 is high. The contract fixes
    // the read response at clock 17 (bit 16) and idle at clock 18 (bit 17).
    logic [17:0] accept_history;
    logic [17:0] read_history;
    `DFF_ARST_VAL(accept_history, {accept_history[16:0], accept}, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(read_history, {read_history[16:0], accept && !request_write}, clk_sys, reset_sys, '0)

    `N2M_ASSERT(SDRAM_LINE_ALIGNED, clk_sys, reset_sys, accept |-> request_address[3:0] == 4'd0)
    `N2M_ASSERT(SDRAM_REQUEST_BEFORE_INIT, clk_sys, reset_sys, request_valid |-> state.initialized)
    `N2M_ASSERT(SDRAM_REQUEST_STABLE, clk_sys, reset_sys,
        $past(request_valid && !request_ready) && request_valid |->
            $stable({request_write, request_address, request_data}))
    `N2M_ASSERT(SDRAM_REFRESH_DEADLINE, clk_sys, reset_sys,
        state.initialized |-> int'(state.refresh_age) <= SDRAM_REFRESH_DEADLINE_CLOCKS)
    `N2M_ASSERT(SDRAM_REFRESH_IDLE_ONLY, clk_sys, reset_sys,
        command == SDRAM_REFRESH_CMD |-> $past(state.phase) == SDRAM_IDLE || !state.initialized)
    `N2M_ASSERT(SDRAM_READ_LATENCY, clk_sys, reset_sys, response_valid == read_history[16])
    `N2M_ASSERT(SDRAM_READY_RETURNS, clk_sys, reset_sys,
        (!accept_history[17] || idle) && (!(|accept_history[16:0]) || !idle))
    `N2M_ASSERT(SDRAM_DQ_EXCLUSIVE, clk_sys, reset_sys, drive_data |-> state.phase == SDRAM_WRITE)
    `N2M_ASSERT(SDRAM_NO_ROW_CROSS, clk_sys, reset_sys,
        (command != SDRAM_ACTIVATE_CMD || DRAM_ADDR == sdram_row(state.address)) &&
        (!(command == SDRAM_READ_CMD || command == SDRAM_WRITE_CMD) ||
            (DRAM_ADDR[9:0] == sdram_column(state.address) && state.address[3:1] == 3'd0)))
    `N2M_ASSERT_KNOWN(SDRAM_KNOWN_PAYLOAD, clk_sys, reset_sys,
        accept ? {request_write, request_address, request_data} : '0)
endmodule
`default_nettype wire
