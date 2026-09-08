`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Bounded ROM/presence service. Command validation and core initialization are
// separate owners; success here never starts the CPU or publishes image_valid.
module n2m_uart_load #(
    parameter bit SIM_PRELOAD = 0
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic start,
    input var n2m_uart_pkg::uart_load_operation_t operation,
    input var logic [31:0] offset,
    input var logic [15:0] count,
    input var logic [31:0] expected_crc,
    output logic busy,
    output logic done,
    output logic [7:0] status,
    input var logic input_valid,
    input var logic [7:0] input_data,
    output logic input_ready,
    output logic output_valid,
    output logic [7:0] output_data,
    input var logic output_ready,
    output logic rom_write,
    output logic rom_read,
    output logic [$clog2(n2m_interfaces_pkg::PROFILE_ROM_BYTES)-1:0] rom_address,
    output logic [7:0] rom_write_data,
    input var logic [7:0] rom_read_data,
    input var logic rom_read_valid
);
    localparam integer ADDRESS_BITS = $clog2(n2m_interfaces_pkg::PROFILE_ROM_BYTES);
    typedef enum logic [3:0] {
        IDLE, CLEAR, WRITE_BYTES, SCAN_FETCH, SCAN_USE,
        READ_FETCH, READ_USE, READ_SEND, COMPLETE
    } state_t;
    state_t state, state_next;
    logic [ADDRESS_BITS-1:0] address, address_next;
    logic [15:0] remaining, remaining_next;
    logic [31:0] crc, crc_next, image_crc, image_crc_next;
    logic missing, missing_next, cleared, cleared_next;
    logic [7:0] held_data, held_data_next, status_next;
    logic presence_write, presence_read, presence_value, presence_valid;
    logic [31:0] updated_crc;
    logic adopt_preload;
`ifdef SYNTHESIS
    assign adopt_preload = 1'b0;
`else
    // Simulation configuration lifetime, deliberately not reset-owned state.
    // The real command/CRC/core-reset owners establish all loaded metadata.
    logic preload_available;
    logic [31:0] preload_crc [0:0];
    initial begin
        preload_available = SIM_PRELOAD;
        if (SIM_PRELOAD) $readmemh("preload-crc.hex", preload_crc);
    end
    always @(posedge clk_sys) begin
        if (!reset_sys && start && operation == n2m_uart_pkg::UART_LOAD_BEGIN)
            preload_available <= 1'b0;
    end
    assign adopt_preload = SIM_PRELOAD && preload_available;
    `N2M_ASSERT(UART_PRELOAD_CRC, clk_sys, reset_sys,
        !(start && operation == n2m_uart_pkg::UART_LOAD_BEGIN && adopt_preload) ||
        (!$isunknown(preload_crc[0]) && expected_crc == preload_crc[0]))
`endif

    assign busy = state != IDLE;
    assign done = state == COMPLETE;
    assign input_ready = state == WRITE_BYTES && !reset_sys;
    assign output_valid = state == READ_SEND && !reset_sys;
    assign output_data = held_data;
    assign rom_write = input_ready && input_valid;
    assign rom_read = (state == SCAN_FETCH || state == READ_FETCH) && !reset_sys;
    assign rom_address = address;
    assign rom_write_data = input_data;
    assign presence_write = (state == CLEAR || rom_write) && !reset_sys;
    assign presence_read = state == SCAN_FETCH && !reset_sys;
    assign updated_crc = n2m_uart_pkg::crc32_byte(crc, rom_read_data);
    n2m_uart_presence_store u_presence (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .write_enable(presence_write), .write_address(address),
        .write_present(state != CLEAR), .read_enable(presence_read),
        .read_address(address), .read_present(presence_value),
        .read_valid(presence_valid)
    );
    always_comb begin
        state_next = state;
        address_next = address;
        remaining_next = remaining;
        crc_next = crc;
        image_crc_next = image_crc;
        missing_next = missing;
        cleared_next = cleared;
        held_data_next = held_data;
        status_next = status;
        case (state)
            IDLE: if (start) begin
                status_next = n2m_interfaces_pkg::STATUS_OK;
                address_next = offset[ADDRESS_BITS-1:0];
                remaining_next = count;
                case (operation)
                    n2m_uart_pkg::UART_LOAD_BEGIN: begin
                        image_crc_next = expected_crc;
                        address_next = '0;
                        cleared_next = 0;
                        state_next = CLEAR;
                        if (adopt_preload) begin
                            cleared_next = 1;
                            state_next = COMPLETE;
                        end
                    end
                    n2m_uart_pkg::UART_LOAD_WRITE: state_next = WRITE_BYTES;
                    n2m_uart_pkg::UART_LOAD_END: begin
                        address_next = '0;
                        crc_next = n2m_interfaces_pkg::WIRE_CRC32_INIT;
                        missing_next = 0;
                        state_next = SCAN_FETCH;
                    end
                    n2m_uart_pkg::UART_LOAD_READ: state_next = READ_FETCH;
                    default: state_next = IDLE;
                endcase
            end
            CLEAR: begin
                address_next = address + 1'b1;
                if (address == n2m_interfaces_pkg::PROFILE_ROM_BYTES - 1) begin
                    cleared_next = 1;
                    state_next = COMPLETE;
                end
            end
            WRITE_BYTES: if (input_valid) begin
                address_next = address + 1'b1;
                remaining_next = remaining - 1'b1;
                if (remaining == 1) state_next = COMPLETE;
            end
            SCAN_FETCH: state_next = SCAN_USE;
            SCAN_USE: begin
                missing_next = missing || !presence_value;
                crc_next = updated_crc;
                address_next = address + 1'b1;
                if (address == n2m_interfaces_pkg::PROFILE_ROM_BYTES - 1) begin
                    status_next = missing_next || (updated_crc ^ n2m_interfaces_pkg::WIRE_CRC32_INIT) != image_crc
                        ? n2m_interfaces_pkg::STATUS_BAD_IMAGE : n2m_interfaces_pkg::STATUS_OK;
                    state_next = COMPLETE;
                end else state_next = SCAN_FETCH;
            end
            READ_FETCH: state_next = READ_USE;
            READ_USE: begin
                held_data_next = rom_read_data;
                state_next = READ_SEND;
            end
            READ_SEND: if (output_ready) begin
                address_next = address + 1'b1;
                remaining_next = remaining - 1'b1;
                state_next = remaining == 1 ? COMPLETE : READ_FETCH;
            end
            COMPLETE: state_next = IDLE;
            default: state_next = IDLE;
        endcase
    end
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(address, address_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(remaining, remaining_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(crc, crc_next, clk_sys, reset_sys, n2m_interfaces_pkg::WIRE_CRC32_INIT)
    `DFF_ARST_VAL(image_crc, image_crc_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(missing, missing_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(cleared, cleared_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(held_data, held_data_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(status, status_next, clk_sys, reset_sys, n2m_interfaces_pkg::STATUS_OK)
    `N2M_ASSERT(UART_LOAD_START_IDLE, clk_sys, reset_sys, start |-> !busy)
    `N2M_ASSERT(UART_LOAD_RANGE, clk_sys, reset_sys,
        start && (operation == n2m_uart_pkg::UART_LOAD_WRITE || operation == n2m_uart_pkg::UART_LOAD_READ) |->
        count != 0 && count <= n2m_interfaces_pkg::WIRE_MAX_PAYLOAD && ({1'b0, offset} + {17'b0, count}) <= n2m_interfaces_pkg::PROFILE_ROM_BYTES)
    `N2M_ASSERT(UART_LOAD_CLEAR_REQUIRED, clk_sys, reset_sys,
        start && (operation == n2m_uart_pkg::UART_LOAD_WRITE || operation == n2m_uart_pkg::UART_LOAD_END) |-> cleared)
    `N2M_ASSERT(UART_LOAD_ROM_SERVICE, clk_sys, reset_sys,
        state == SCAN_USE || state == READ_USE |-> rom_read_valid)
    `N2M_ASSERT(UART_LOAD_PRESENCE_SERVICE, clk_sys, reset_sys,
        state == SCAN_USE |-> presence_valid)
    `N2M_ASSERT_KNOWN(UART_LOAD_CONTROLS, clk_sys, reset_sys,
        ({start, operation, input_valid, output_ready, state}))
    `N2M_ASSERT_STABLE_WHEN(UART_LOAD_INPUT_HELD, clk_sys, reset_sys,
        input_valid && !input_ready, ({input_valid, input_data}))
    `N2M_ASSERT_STABLE_WHEN(UART_LOAD_OUTPUT_HELD, clk_sys, reset_sys,
        output_valid && !output_ready, ({output_valid, output_data}))
endmodule
`default_nettype wire
