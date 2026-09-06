`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Byte-domain framing only; the dispatcher owns command length/status replies.
module n2m_uart_packet_rx #(
    parameter integer CLOCK_HZ = 50000000
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic rx_valid,
    input var logic [7:0] rx_data,
    input var logic rx_error,
    output logic request_valid,
    output n2m_interfaces_pkg::packet_header_t request_header,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] request_bytes,
    input var logic request_done,
    input var logic packet_read,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] packet_address,
    output logic [7:0] packet_data,
    output logic packet_data_valid
);
    import n2m_interfaces_pkg::*;
    import n2m_uart_pkg::*;
    localparam integer TIMEOUT_CYCLES = (CLOCK_HZ / 1000) * WIRE_FRAME_TIMEOUT_MS;
    localparam integer TIMER_BITS = $clog2(TIMEOUT_CYCLES + 1);
    typedef enum logic [2:0] { RECEIVE, FETCH, DECODE, INSERT_ZERO, CHECK, HOLD } state_t;
    state_t state;
    state_t state_next;
    logic [UART_ADDRESS_BITS-1:0] encoded_count;
    logic [UART_ADDRESS_BITS-1:0] encoded_count_next;
    logic [UART_ADDRESS_BITS-1:0] encoded_index;
    logic [UART_ADDRESS_BITS-1:0] encoded_index_next;
    logic [UART_ADDRESS_BITS-1:0] decoded_count;
    logic [UART_ADDRESS_BITS-1:0] decoded_count_next;
    logic [TIMER_BITS-1:0] idle_count;
    logic [TIMER_BITS-1:0] idle_count_next;
    logic discard_input;
    logic discard_input_next;
    logic need_code;
    logic need_code_next;
    logic insert_between;
    logic insert_between_next;
    logic [7:0] remaining;
    logic [7:0] remaining_next;
    logic [15:0] crc;
    logic [15:0] crc_next;
    logic [15:0] tail;
    logic [15:0] tail_next;
    packet_header_t header;
    packet_header_t header_next;
    logic encoded_write;
    logic encoded_read;
    logic [7:0] encoded_data;
    logic encoded_valid;
    logic decoded_write;
    logic emit_byte;
    logic [7:0] emitted_data;
    logic more_encoded;
    logic decoded_read;

    assign request_valid = state == HOLD && !reset_sys;
    assign request_header = header;
    assign request_bytes = decoded_count;
    assign more_encoded = encoded_index + 1'b1 < encoded_count;
    assign encoded_read = state == FETCH;
    assign encoded_write = state == RECEIVE && rx_valid && !rx_error && rx_data != 0 &&
                           !discard_input && encoded_count < UART_ENCODED_MAX;
    assign decoded_write = emit_byte && decoded_count < UART_RAW_MAX;
    assign decoded_read = request_valid && packet_read;

    n2m_uart_packet_store stores (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .encoded_write(encoded_write), .encoded_write_address(encoded_count),
        .encoded_write_data(rx_data), .encoded_read(encoded_read),
        .encoded_read_address(encoded_index), .encoded_read_data(encoded_data),
        .encoded_read_valid(encoded_valid), .decoded_write(decoded_write),
        .decoded_write_address(decoded_count), .decoded_write_data(emitted_data),
        .decoded_read(decoded_read), .decoded_read_address(packet_address),
        .decoded_read_data(packet_data), .decoded_read_valid(packet_data_valid)
    );

    always_comb begin
        state_next = state;
        encoded_count_next = encoded_count;
        encoded_index_next = encoded_index;
        decoded_count_next = decoded_count;
        idle_count_next = idle_count;
        discard_input_next = discard_input;
        need_code_next = need_code;
        insert_between_next = insert_between;
        remaining_next = remaining;
        crc_next = crc;
        tail_next = tail;
        header_next = header;
        emit_byte = 1'b0;
        emitted_data = 8'b0;

        // Track a busy frame through return to idle; its suffix cannot become
        // a fresh request merely because reply transmission has completed.
        if (state != RECEIVE && rx_valid)
            discard_input_next = rx_data != 0;

        case (state)
            RECEIVE: begin
                if (rx_valid) begin
                    idle_count_next = '0;
                    if (rx_data == 0) begin
                        discard_input_next = 1'b0;
                        if (!discard_input && encoded_count != 0) begin
                            encoded_index_next = '0;
                            decoded_count_next = '0;
                            need_code_next = 1'b1;
                            remaining_next = '0;
                            insert_between_next = 1'b0;
                            header_next = '0;
                            crc_next = WIRE_CRC_INIT;
                            tail_next = '0;
                            state_next = FETCH;
                        end else encoded_count_next = '0;
                    end else if (!discard_input) begin
                        if (encoded_count < UART_ENCODED_MAX)
                            encoded_count_next = encoded_count + 1'b1;
                        else begin
                            discard_input_next = 1'b1;
                            encoded_count_next = '0;
                        end
                    end
                end else if (encoded_count != 0 || discard_input) begin
                    if (idle_count == TIMEOUT_CYCLES - 1) begin
                        idle_count_next = '0;
                        encoded_count_next = '0;
                        discard_input_next = 1'b0;
                    end else idle_count_next = idle_count + 1'b1;
                end
            end
            FETCH: state_next = DECODE;
            DECODE: begin
                encoded_index_next = encoded_index + 1'b1;
                if (need_code) begin
                    // The code's nonzero run must fit before the delimiter.
                    if (encoded_data == 0 ||
                        {1'b0, encoded_data} > encoded_count - encoded_index) begin
                        state_next = RECEIVE;
                        encoded_count_next = '0;
                    end else begin
                        remaining_next = encoded_data - 1'b1;
                        insert_between_next = encoded_data != 8'hff;
                        need_code_next = encoded_data == 1;
                        if (!more_encoded) state_next = CHECK;
                        else if (encoded_data == 1) state_next = INSERT_ZERO;
                        else state_next = FETCH;
                    end
                end else begin
                    emit_byte = 1'b1;
                    emitted_data = encoded_data;
                    remaining_next = remaining - 1'b1;
                    if (remaining == 1) begin
                        need_code_next = 1'b1;
                        if (!more_encoded) state_next = CHECK;
                        else if (insert_between) state_next = INSERT_ZERO;
                        else state_next = FETCH;
                    end else state_next = FETCH;
                end
            end
            INSERT_ZERO: begin
                emit_byte = 1'b1;
                emitted_data = 8'b0;
                state_next = FETCH;
            end
            CHECK: begin
                if (decoded_count >= PACKET_HEADER_BYTES + 2 && crc == tail &&
                    header.kind == WIRE_REQUEST && header.status == STATUS_OK)
                    state_next = HOLD;
                else begin
                    state_next = RECEIVE;
                    encoded_count_next = '0;
                end
            end
            HOLD: begin
                // Done means response completion, not merely command acceptance.
                if (request_done) begin
                    state_next = RECEIVE;
                    encoded_count_next = '0;
                    idle_count_next = '0;
                end
            end
            default: state_next = RECEIVE;
        endcase

        if (emit_byte) begin
            if (decoded_count >= UART_RAW_MAX) begin
                state_next = RECEIVE;
                encoded_count_next = '0;
            end else begin
                if (decoded_count < PACKET_HEADER_BYTES)
                    header_next[8 * decoded_count +: 8] = emitted_data;
                // Delay two bytes so the received little-endian CRC itself
                // never enters the header/payload CRC accumulator.
                if (decoded_count >= 2) crc_next = crc16_byte(crc, tail[7:0]);
                tail_next = {emitted_data, tail[15:8]};
                decoded_count_next = decoded_count + 1'b1;
            end
        end
        // A bad UART stop bit invalidates its entire in-flight frame. Keep a
        // previously delimited request intact while dropping this busy input.
        if (rx_error) begin
            discard_input_next = 1'b1;
            if (state == RECEIVE) begin
                state_next = RECEIVE;
                encoded_count_next = '0;
                idle_count_next = '0;
            end
        end
    end

    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, RECEIVE)
    `DFF_ARST_VAL(encoded_count, encoded_count_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(encoded_index, encoded_index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(decoded_count, decoded_count_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(idle_count, idle_count_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(discard_input, discard_input_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(need_code, need_code_next, clk_sys, reset_sys, 1'b1)
    `DFF_ARST_VAL(insert_between, insert_between_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(remaining, remaining_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(crc, crc_next, clk_sys, reset_sys, WIRE_CRC_INIT)
    `DFF_ARST_VAL(tail, tail_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(header, header_next, clk_sys, reset_sys, '0)

    `N2M_ASSERT_NO_RST(UART_TIMEOUT_CONFIGURATION, clk_sys, CLOCK_HZ >= 1000)
    `N2M_ASSERT(UART_ENCODED_SERVICE, clk_sys, reset_sys, state == DECODE |-> encoded_valid)
    `N2M_ASSERT(UART_PACKET_READ_RANGE, clk_sys, reset_sys,
        decoded_read |-> packet_address < decoded_count)
    `N2M_ASSERT(UART_REQUEST_DONE, clk_sys, reset_sys, request_done |-> request_valid)
    `N2M_ASSERT_KNOWN(UART_RX_CONTROLS, clk_sys, reset_sys,
        ({rx_valid, rx_error, request_done, packet_read, state}))
    `N2M_ASSERT_STABLE_WHEN(UART_REQUEST_HELD, clk_sys, reset_sys,
        request_valid && !request_done, ({header, decoded_count}))
endmodule
`default_nettype wire
