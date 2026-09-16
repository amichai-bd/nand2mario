`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Host SDRAM line service: an SDRAM_WRITE or SDRAM_READ of 1-15 consecutive
// lines through the single line request interface of the storage owner
// (wiki/src/rtl/storage/MAS_sdram.md). Write bytes stream in from the packet
// store, one line at a time; read bytes stream out through the reply path.
// Command validation is a separate owner; every request here is line aligned,
// inside the device and issued only while the controller reports initialized.
module n2m_uart_sdram (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic start,
    input var logic write,
    input var logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] address,
    input var logic [3:0] line_count,
    // Write bytes in line order, byte 0 of each line first; ready only while
    // a line is being filled, never while a request waits for the controller.
    input var logic input_valid,
    input var logic [7:0] input_data,
    output logic input_ready,
    output logic busy,
    output logic done,
    // Read bytes stream in line order, byte 0 of each line first.
    output logic output_valid,
    output logic [7:0] output_data,
    input var logic output_ready,
    output logic sdram_request_valid,
    output logic sdram_request_write,
    output logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] sdram_request_address,
    output logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] sdram_request_data,
    input var logic sdram_request_ready,
    input var logic sdram_response_valid,
    input var logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] sdram_response_data
);
    localparam integer LINE_BYTES = 32'(n2m_interfaces_pkg::SDRAM_LINE_BYTES);
    typedef enum logic [2:0] { IDLE, FILL, REQUEST, RESPONSE, STREAM, COMPLETE } state_t;
    state_t state, state_next;
    logic write_held, write_held_next;
    logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] line_address, line_address_next;
    logic [3:0] lines_left, lines_left_next;
    logic [3:0] byte_index, byte_index_next;
    logic [LINE_BYTES*8-1:0] line, line_next;

    assign busy = state != IDLE;
    assign done = state == COMPLETE;
    assign input_ready = state == FILL && !reset_sys;
    assign output_valid = state == STREAM && !reset_sys;
    assign output_data = line[byte_index*8 +: 8];
    // The request is held stable from REQUEST until the accepting edge.
    assign sdram_request_valid = state == REQUEST && !reset_sys;
    assign sdram_request_write = write_held;
    assign sdram_request_address = line_address;
    assign sdram_request_data = line;

    always_comb begin
        state_next = state;
        write_held_next = write_held;
        line_address_next = line_address;
        lines_left_next = lines_left;
        byte_index_next = byte_index;
        line_next = line;
        case (state)
            IDLE: if (start) begin
                write_held_next = write;
                line_address_next = address;
                lines_left_next = line_count;
                byte_index_next = '0;
                state_next = write ? FILL : REQUEST;
            end
            FILL: if (input_valid) begin
                line_next[byte_index*8 +: 8] = input_data;
                byte_index_next = byte_index + 4'd1;
                if (byte_index == 4'd15) state_next = REQUEST;
            end
            // A write is complete at acceptance: the controller stays not-ready
            // until the line is in the device, so no later request overtakes it.
            REQUEST: if (sdram_request_ready) begin
                if (write_held) begin
                    lines_left_next = lines_left - 4'd1;
                    line_address_next = line_address + n2m_interfaces_pkg::SDRAM_ADDRESS_BITS'(LINE_BYTES);
                    state_next = lines_left == 4'd1 ? COMPLETE : FILL;
                end else state_next = RESPONSE;
            end
            RESPONSE: if (sdram_response_valid) begin
                line_next = sdram_response_data;
                byte_index_next = '0;
                state_next = STREAM;
            end
            STREAM: if (output_ready) begin
                byte_index_next = byte_index + 4'd1;
                if (byte_index == 4'd15) begin
                    lines_left_next = lines_left - 4'd1;
                    line_address_next = line_address + n2m_interfaces_pkg::SDRAM_ADDRESS_BITS'(LINE_BYTES);
                    state_next = lines_left == 4'd1 ? COMPLETE : REQUEST;
                end
            end
            COMPLETE: state_next = IDLE;
            default: state_next = IDLE;
        endcase
    end
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(write_held, write_held_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(line_address, line_address_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(lines_left, lines_left_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(byte_index, byte_index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(line, line_next, clk_sys, reset_sys, '0)

    `N2M_ASSERT(UART_SDRAM_ALIGNED, clk_sys, reset_sys, !start || address[3:0] == 4'd0)
    `N2M_ASSERT(UART_SDRAM_COUNT, clk_sys, reset_sys, !start || line_count != 4'd0)
    `N2M_ASSERT(UART_SDRAM_SINGLE_START, clk_sys, reset_sys, !start || state == IDLE)
    `N2M_ASSERT(UART_SDRAM_INPUT_EXPECTED, clk_sys, reset_sys, !input_valid || state == FILL)
    `N2M_ASSERT(UART_SDRAM_RESPONSE_EXPECTED, clk_sys, reset_sys,
        !sdram_response_valid || state == RESPONSE)
endmodule
`default_nettype wire
