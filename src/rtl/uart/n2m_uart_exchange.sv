`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Transaction ordering and immediate decoded-request retry identity.
// No core-reset input: a core reset is an ordinary completed command here.
module n2m_uart_exchange (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic request_valid,
    input var n2m_interfaces_pkg::packet_header_t request_header,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] request_bytes,
    output logic request_done,
    output logic packet_read,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] packet_address,
    input var logic [7:0] packet_data,
    input var logic packet_data_valid,
    output logic command_valid,
    output logic [7:0] command_forced_status,
    input var logic command_packet_read,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] command_packet_address,
    input var logic response_write,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] response_address,
    input var logic [7:0] response_data,
    input var logic command_done,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] response_bytes,
    output logic transmit_valid,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] transmit_bytes,
    input var logic transmit_read,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] transmit_address,
    output logic [7:0] transmit_data,
    output logic transmit_data_valid,
    input var logic transmit_done
);
    typedef enum logic [3:0] {
        IDLE, COMPARE_FETCH, COMPARE_USE, EXECUTE,
        COPY_REQUEST_FETCH, COPY_REQUEST_USE,
        COPY_RESPONSE_FETCH, COPY_RESPONSE_USE, TRANSMIT
    } state_t;
    state_t state;
    state_t state_next;
    logic cache_valid;
    logic cache_valid_next;
    logic [31:0] cached_sequence;
    logic [31:0] cached_sequence_next;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] cached_request_bytes;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] cached_request_bytes_next;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] cached_response_bytes;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] cached_response_bytes_next;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] staged_bytes;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] staged_bytes_next;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] index;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] index_next;
    logic replace_cache;
    logic replace_cache_next;
    logic transmit_cached;
    logic transmit_cached_next;
    logic [7:0] forced_status;
    logic [7:0] forced_status_next;
    logic [2:0] write_enable;
    logic [3*n2m_uart_pkg::UART_ADDRESS_BITS-1:0] write_address;
    logic [23:0] write_data;
    logic [2:0] read_enable;
    logic [3*n2m_uart_pkg::UART_ADDRESS_BITS-1:0] read_address;
    logic [23:0] read_data;
    logic [2:0] read_valid;

    assign command_valid = state == EXECUTE && !reset_sys;
    assign command_forced_status = forced_status;
    assign transmit_valid = state == TRANSMIT && !reset_sys;
    assign transmit_bytes = transmit_cached ? cached_response_bytes : staged_bytes;
    assign transmit_data = transmit_cached ? read_data[15:8] : read_data[23:16];
    assign transmit_data_valid = transmit_cached ? read_valid[1] : read_valid[2];
    assign request_done = transmit_valid && transmit_done;

    n2m_uart_exchange_store stores (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .write_enable(write_enable), .write_address(write_address),
        .write_data(write_data), .read_enable(read_enable),
        .read_address(read_address), .read_data(read_data), .read_valid(read_valid)
    );

    always_comb begin
        state_next = state;
        cache_valid_next = cache_valid;
        cached_sequence_next = cached_sequence;
        cached_request_bytes_next = cached_request_bytes;
        cached_response_bytes_next = cached_response_bytes;
        staged_bytes_next = staged_bytes;
        index_next = index;
        replace_cache_next = replace_cache;
        transmit_cached_next = transmit_cached;
        forced_status_next = forced_status;
        write_enable = '0;
        write_address = '0;
        write_data = '0;
        read_enable = '0;
        read_address = '0;
        packet_read = 1'b0;
        packet_address = '0;

        case (state)
            IDLE: begin
                if (request_valid) begin
                    index_next = '0;
                    transmit_cached_next = 1'b0;
                    replace_cache_next = 1'b1;
                    forced_status_next = n2m_interfaces_pkg::STATUS_OK;
                    if (cache_valid && request_header.seq == cached_sequence) begin
                        replace_cache_next = 1'b0;
                        if (request_bytes == cached_request_bytes)
                            state_next = COMPARE_FETCH;
                        else begin
                            forced_status_next = n2m_interfaces_pkg::STATUS_SEQUENCE;
                            state_next = EXECUTE;
                        end
                    end else state_next = EXECUTE;
                end
            end
            COMPARE_FETCH: begin
                packet_read = 1'b1;
                packet_address = index;
                read_enable[0] = 1'b1;
                read_address[0 +: n2m_uart_pkg::UART_ADDRESS_BITS] = index;
                state_next = COMPARE_USE;
            end
            COMPARE_USE: begin
                if (packet_data != read_data[7:0]) begin
                    forced_status_next = n2m_interfaces_pkg::STATUS_SEQUENCE;
                    state_next = EXECUTE;
                end else if (index + 1'b1 == request_bytes) begin
                    transmit_cached_next = 1'b1;
                    state_next = TRANSMIT;
                end else begin
                    index_next = index + 1'b1;
                    state_next = COMPARE_FETCH;
                end
            end
            EXECUTE: begin
                packet_read = command_packet_read;
                packet_address = command_packet_address;
                write_enable[2] = response_write;
                write_address[2*n2m_uart_pkg::UART_ADDRESS_BITS +: n2m_uart_pkg::UART_ADDRESS_BITS] = response_address;
                write_data[23:16] = response_data;
                if (command_done) begin
                    staged_bytes_next = response_bytes;
                    index_next = '0;
                    state_next = replace_cache ? COPY_REQUEST_FETCH : TRANSMIT;
                end
            end
            COPY_REQUEST_FETCH: begin
                packet_read = 1'b1;
                packet_address = index;
                state_next = COPY_REQUEST_USE;
            end
            COPY_REQUEST_USE: begin
                write_enable[0] = 1'b1;
                write_address[0 +: n2m_uart_pkg::UART_ADDRESS_BITS] = index;
                write_data[7:0] = packet_data;
                if (index + 1'b1 == request_bytes) begin
                    index_next = '0;
                    state_next = COPY_RESPONSE_FETCH;
                end else begin
                    index_next = index + 1'b1;
                    state_next = COPY_REQUEST_FETCH;
                end
            end
            COPY_RESPONSE_FETCH: begin
                read_enable[2] = 1'b1;
                read_address[2*n2m_uart_pkg::UART_ADDRESS_BITS +: n2m_uart_pkg::UART_ADDRESS_BITS] = index;
                state_next = COPY_RESPONSE_USE;
            end
            COPY_RESPONSE_USE: begin
                write_enable[1] = 1'b1;
                write_address[n2m_uart_pkg::UART_ADDRESS_BITS +: n2m_uart_pkg::UART_ADDRESS_BITS] = index;
                write_data[15:8] = read_data[23:16];
                if (index + 1'b1 == staged_bytes) begin
                    cache_valid_next = 1'b1;
                    cached_sequence_next = request_header.seq;
                    cached_request_bytes_next = request_bytes;
                    cached_response_bytes_next = staged_bytes;
                    transmit_cached_next = 1'b1;
                    state_next = TRANSMIT;
                end else begin
                    index_next = index + 1'b1;
                    state_next = COPY_RESPONSE_FETCH;
                end
            end
            TRANSMIT: begin
                if (transmit_read) begin
                    if (transmit_cached) begin
                        read_enable[1] = 1'b1;
                        read_address[n2m_uart_pkg::UART_ADDRESS_BITS +: n2m_uart_pkg::UART_ADDRESS_BITS] = transmit_address;
                    end else begin
                        read_enable[2] = 1'b1;
                        read_address[2*n2m_uart_pkg::UART_ADDRESS_BITS +: n2m_uart_pkg::UART_ADDRESS_BITS] = transmit_address;
                    end
                end
                if (transmit_done) state_next = IDLE;
            end
            default: state_next = IDLE;
        endcase
    end

    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(cache_valid, cache_valid_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(cached_sequence, cached_sequence_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(cached_request_bytes, cached_request_bytes_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(cached_response_bytes, cached_response_bytes_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(staged_bytes, staged_bytes_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(index, index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(replace_cache, replace_cache_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(transmit_cached, transmit_cached_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(forced_status, forced_status_next, clk_sys, reset_sys, n2m_interfaces_pkg::STATUS_OK)

    `N2M_ASSERT(UART_EXCHANGE_REQUEST_HELD, clk_sys, reset_sys,
        state != IDLE |-> request_valid)
    `N2M_ASSERT(UART_EXCHANGE_REQUEST_SIZE, clk_sys, reset_sys,
        request_valid |-> request_bytes >= n2m_interfaces_pkg::PACKET_HEADER_BYTES + 2 && request_bytes <= n2m_uart_pkg::UART_RAW_MAX)
    `N2M_ASSERT(UART_EXCHANGE_PACKET_SERVICE, clk_sys, reset_sys,
        state == COMPARE_USE || state == COPY_REQUEST_USE |-> packet_data_valid)
    `N2M_ASSERT(UART_EXCHANGE_COMPARE_SERVICE, clk_sys, reset_sys,
        state == COMPARE_USE |-> read_valid[0])
    `N2M_ASSERT(UART_EXCHANGE_RESPONSE_SERVICE, clk_sys, reset_sys,
        state == COPY_RESPONSE_USE |-> read_valid[2])
    `N2M_ASSERT(UART_EXCHANGE_RESPONSE_WRITE, clk_sys, reset_sys,
        response_write |-> command_valid && response_address < n2m_uart_pkg::UART_RAW_MAX)
    `N2M_ASSERT(UART_EXCHANGE_COMMAND_DONE, clk_sys, reset_sys,
        command_done |-> command_valid && response_bytes >= n2m_interfaces_pkg::PACKET_HEADER_BYTES + 2 && response_bytes <= n2m_uart_pkg::UART_RAW_MAX)
    `N2M_ASSERT(UART_EXCHANGE_TRANSMIT_READ, clk_sys, reset_sys,
        transmit_read |-> transmit_valid && transmit_address < transmit_bytes)
    `N2M_ASSERT(UART_EXCHANGE_TRANSMIT_DONE, clk_sys, reset_sys,
        transmit_done |-> transmit_valid)
    `N2M_ASSERT(UART_EXCHANGE_SEQUENCE_CACHE, clk_sys, reset_sys,
        !replace_cache |-> write_enable[1:0] == 0)
    `N2M_ASSERT_STABLE_WHEN(UART_EXCHANGE_STABLE_REQUEST, clk_sys, reset_sys,
        state != IDLE && !request_done, ({request_header, request_bytes}))
endmodule
`default_nettype wire
