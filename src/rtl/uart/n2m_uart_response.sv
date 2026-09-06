`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Writes a complete raw reply into the exchange's existing staging bank.
module n2m_uart_response (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic start,
    input var logic [31:0] sequence_token,
    input var logic [7:0] command,
    input var logic [7:0] status,
    input var logic [15:0] payload_bytes,
    output logic busy,
    input var logic payload_valid,
    input var logic [7:0] payload_data,
    output logic payload_ready,
    output logic response_write,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] response_address,
    output logic [7:0] response_data,
    output logic done,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] response_bytes
);
    import n2m_interfaces_pkg::*;
    import n2m_uart_pkg::*;
    typedef enum logic [2:0] { IDLE, HEADER, PAYLOAD, CRC_LOW, CRC_HIGH, COMPLETE } state_t;
    state_t state, state_next;
    packet_header_t header, new_header;
    logic [UART_ADDRESS_BITS-1:0] index, index_next;
    logic [15:0] crc, crc_next;
    assign new_header = {payload_bytes, status, command, sequence_token, WIRE_RESPONSE, WIRE_VERSION};
    assign busy = state != IDLE;
    assign done = state == COMPLETE;
    assign payload_ready = state == PAYLOAD;
    assign response_write = state == HEADER || (state == PAYLOAD && payload_valid)
        || state == CRC_LOW || state == CRC_HIGH;
    assign response_address = index;
    assign response_bytes = UART_ADDRESS_BITS'(PACKET_HEADER_BYTES + header.length + 2);
    always_comb begin
        case (state)
            HEADER: response_data = 8'(header >> (index * 8));
            PAYLOAD: response_data = payload_data;
            CRC_LOW: response_data = crc[7:0];
            CRC_HIGH: response_data = crc[15:8];
            default: response_data = '0;
        endcase
    end
    always_comb begin
        state_next = state;
        index_next = index;
        crc_next = crc;
        case (state)
            IDLE: if (start) begin
                state_next = HEADER;
                index_next = '0;
                crc_next = WIRE_CRC_INIT;
            end
            HEADER: begin
                index_next = index + 1'b1;
                crc_next = crc16_byte(crc, response_data);
                if (index == PACKET_HEADER_BYTES - 1)
                    state_next = header.length == 0 ? CRC_LOW : PAYLOAD;
            end
            PAYLOAD: if (payload_valid) begin
                index_next = index + 1'b1;
                crc_next = crc16_byte(crc, payload_data);
                if (index + 1'b1 == PACKET_HEADER_BYTES + header.length)
                    state_next = CRC_LOW;
            end
            CRC_LOW: begin
                index_next = index + 1'b1;
                state_next = CRC_HIGH;
            end
            CRC_HIGH: state_next = COMPLETE;
            COMPLETE: state_next = IDLE;
            default: state_next = IDLE;
        endcase
    end
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(index, index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(crc, crc_next, clk_sys, reset_sys, WIRE_CRC_INIT)
    `DFF_ARST_VAL(header, start ? new_header : header, clk_sys, reset_sys, '0)
    `N2M_ASSERT(UART_RESPONSE_START_IDLE, clk_sys, reset_sys, start |-> !busy)
    `N2M_ASSERT(UART_RESPONSE_LENGTH, clk_sys, reset_sys,
        start |-> payload_bytes <= WIRE_MAX_PAYLOAD && (status == STATUS_OK || payload_bytes == 0))
    `N2M_ASSERT(UART_RESPONSE_WRITE_RANGE, clk_sys, reset_sys,
        response_write |-> response_address < response_bytes)
    `N2M_ASSERT_KNOWN(UART_RESPONSE_CONTROLS, clk_sys, reset_sys, ({start, payload_valid, state}))
    `N2M_ASSERT(UART_RESPONSE_BYTE_KNOWN, clk_sys, reset_sys,
        response_write |-> !$isunknown(response_data))
    `N2M_ASSERT_STABLE_WHEN(UART_RESPONSE_PAYLOAD_HELD, clk_sys, reset_sys,
        payload_valid && !payload_ready, ({payload_valid, payload_data}))
endmodule
`default_nettype wire
