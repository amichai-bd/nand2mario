`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// COBS scans and then rereads each block through the held raw-response port.
// No private array or second response store is needed.
module n2m_uart_packet_tx (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic transmit_valid,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] transmit_bytes,
    output logic transmit_done,
    output logic transmit_read,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] transmit_address,
    input var logic [7:0] transmit_data,
    input var logic transmit_data_valid,
    output logic byte_valid,
    output logic [7:0] byte_data,
    input var logic byte_ready
);
    import n2m_uart_pkg::*;
    typedef enum logic [3:0] {
        IDLE, BLOCK_START, SCAN_FETCH, SCAN_USE, CODE,
        DATA_FETCH, DATA_USE, DATA_SEND, DELIMITER, DRAIN
    } state_t;
    state_t state, state_next;
    logic [UART_ADDRESS_BITS-1:0] cursor, cursor_next;
    logic [UART_ADDRESS_BITS-1:0] block_start, block_start_next;
    logic [7:0] block_bytes, block_bytes_next;
    logic [7:0] index, index_next;
    logic [7:0] held_data, held_data_next;
    logic more, more_next;
    logic [UART_ADDRESS_BITS-1:0] scan_address;
    assign scan_address = block_start + UART_ADDRESS_BITS'(block_bytes);
    assign transmit_read = state == SCAN_FETCH || state == DATA_FETCH;
    assign transmit_address = state == SCAN_FETCH ? scan_address
        : block_start + UART_ADDRESS_BITS'(index);
    assign byte_valid = state == CODE || state == DATA_SEND || state == DELIMITER;
    assign byte_data = state == CODE ? block_bytes + 8'd1
        : (state == DATA_SEND ? held_data : 8'd0);
    // The serial transmitter's ready means its previous stop cell has ended.
    assign transmit_done = state == DRAIN && byte_ready;

    always_comb begin
        state_next = state;
        cursor_next = cursor;
        block_start_next = block_start;
        block_bytes_next = block_bytes;
        index_next = index;
        held_data_next = held_data;
        more_next = more;
        case (state)
            IDLE: if (transmit_valid) begin
                cursor_next = '0;
                state_next = BLOCK_START;
            end
            BLOCK_START: begin
                block_start_next = cursor;
                block_bytes_next = '0;
                index_next = '0;
                more_next = 1'b0;
                state_next = cursor == transmit_bytes ? CODE : SCAN_FETCH;
            end
            SCAN_FETCH: state_next = SCAN_USE;
            SCAN_USE: begin
                if (transmit_data == 0) begin
                    cursor_next = scan_address + 1'b1;
                    more_next = 1'b1;
                    state_next = CODE;
                end else begin
                    block_bytes_next = block_bytes + 1'b1;
                    if (block_bytes == 253 || scan_address + 1'b1 == transmit_bytes) begin
                        cursor_next = scan_address + 1'b1;
                        more_next = block_bytes == 253;
                        state_next = CODE;
                    end else state_next = SCAN_FETCH;
                end
            end
            CODE: if (byte_ready) begin
                if (block_bytes != 0) state_next = DATA_FETCH;
                else state_next = more ? BLOCK_START : DELIMITER;
            end
            DATA_FETCH: state_next = DATA_USE;
            DATA_USE: begin
                held_data_next = transmit_data;
                state_next = DATA_SEND;
            end
            DATA_SEND: if (byte_ready) begin
                if (index + 1'b1 == block_bytes)
                    state_next = more ? BLOCK_START : DELIMITER;
                else begin
                    index_next = index + 1'b1;
                    state_next = DATA_FETCH;
                end
            end
            DELIMITER: if (byte_ready) state_next = DRAIN;
            DRAIN: if (byte_ready) state_next = IDLE;
            default: state_next = IDLE;
        endcase
    end
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(cursor, cursor_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(block_start, block_start_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(block_bytes, block_bytes_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(index, index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(held_data, held_data_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(more, more_next, clk_sys, reset_sys, 1'b0)
    `N2M_ASSERT(UART_TX_REQUEST_SIZE, clk_sys, reset_sys,
        transmit_valid |-> transmit_bytes >= n2m_interfaces_pkg::PACKET_HEADER_BYTES + 2 && transmit_bytes <= UART_RAW_MAX)
    `N2M_ASSERT(UART_TX_REQUEST_ACTIVE, clk_sys, reset_sys, state != IDLE |-> transmit_valid)
    `N2M_ASSERT(UART_TX_READ_RANGE, clk_sys, reset_sys,
        transmit_read |-> transmit_address < transmit_bytes)
    `N2M_ASSERT(UART_TX_READ_SERVICE, clk_sys, reset_sys,
        state == SCAN_USE || state == DATA_USE |-> transmit_data_valid)
    `N2M_ASSERT(UART_TX_BLOCK_BOUND, clk_sys, reset_sys, block_bytes <= 254)
    `N2M_ASSERT_KNOWN(UART_TX_PACKET_CONTROLS, clk_sys, reset_sys,
        ({transmit_valid, byte_ready, state}))
    `N2M_ASSERT_STABLE_WHEN(UART_TX_PACKET_HELD, clk_sys, reset_sys,
        transmit_valid && !transmit_done, transmit_bytes)
    `N2M_ASSERT_STABLE_WHEN(UART_TX_ENCODED_HELD, clk_sys, reset_sys,
        byte_valid && !byte_ready, ({byte_valid, byte_data}))
endmodule
`default_nettype wire
