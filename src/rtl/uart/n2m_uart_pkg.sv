`timescale 1ns/1ps
package n2m_uart_pkg;
    localparam integer UART_RAW_MAX = n2m_interfaces_pkg::PACKET_HEADER_BYTES + n2m_interfaces_pkg::WIRE_MAX_PAYLOAD + 2;
    localparam integer UART_ENCODED_MAX = UART_RAW_MAX + UART_RAW_MAX / 254 + 1;
    localparam integer UART_ADDRESS_BITS = $clog2(UART_ENCODED_MAX);
    typedef enum logic [1:0] {
        UART_LOAD_BEGIN, UART_LOAD_WRITE, UART_LOAD_END, UART_LOAD_READ
    } uart_load_operation_t;

    function automatic logic [15:0] crc16_byte(
        input logic [15:0] previous,
        input logic [7:0] value
    );
        logic [15:0] result;
        integer bit_index;
        result = previous ^ {value, 8'b0};
        for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
            result = result[15] ? (result << 1) ^ n2m_interfaces_pkg::WIRE_CRC_POLY : result << 1;
        return result;
    endfunction

    function automatic logic [31:0] crc32_byte(
        input logic [31:0] previous,
        input logic [7:0] value
    );
        logic [31:0] result;
        integer bit_index;
        result = previous ^ {24'b0, value};
        for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
            result = result[0] ? (result >> 1) ^ n2m_interfaces_pkg::WIRE_CRC32_POLY : result >> 1;
        return result;
    endfunction
endpackage
