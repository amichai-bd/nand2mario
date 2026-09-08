`timescale 1ns/1ps
`default_nettype none

// One in-flight request only. Completed exchange caches are separate owners.
module n2m_uart_packet_store (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic encoded_write,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] encoded_write_address,
    input var logic [7:0] encoded_write_data,
    input var logic encoded_read,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] encoded_read_address,
    output logic [7:0] encoded_read_data,
    output logic encoded_read_valid,
    input var logic decoded_write,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] decoded_write_address,
    input var logic [7:0] decoded_write_data,
    input var logic decoded_read,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] decoded_read_address,
    output logic [7:0] decoded_read_data,
    output logic decoded_read_valid
);
    logic [7:0] encoded_unused_data;
    logic encoded_unused_valid;
    logic [7:0] decoded_unused_data;
    logic decoded_unused_valid;

    n2m_intel_ram #(
        .DEPTH(n2m_uart_pkg::UART_ENCODED_MAX), .DATA_BITS(8),
        .ADDRESS_BITS(n2m_uart_pkg::UART_ADDRESS_BITS)
    ) encoded (
        .clk_a(clk_sys), .clk_b(clk_sys),
        .reset_a(reset_sys), .reset_b(reset_sys),
        .a_read(1'b0), .a_write(encoded_write),
        .a_address(encoded_write_address), .a_wdata(encoded_write_data),
        .a_byte_enable(1'b1), .a_rdata(encoded_unused_data),
        .a_valid(encoded_unused_valid),
        .b_read(encoded_read), .b_address(encoded_read_address),
        .b_rdata(encoded_read_data), .b_valid(encoded_read_valid)
    );
    n2m_intel_ram #(
        .DEPTH(n2m_uart_pkg::UART_RAW_MAX), .DATA_BITS(8),
        .ADDRESS_BITS(n2m_uart_pkg::UART_ADDRESS_BITS)
    ) decoded (
        .clk_a(clk_sys), .clk_b(clk_sys),
        .reset_a(reset_sys), .reset_b(reset_sys),
        .a_read(1'b0), .a_write(decoded_write),
        .a_address(decoded_write_address), .a_wdata(decoded_write_data),
        .a_byte_enable(1'b1), .a_rdata(decoded_unused_data),
        .a_valid(decoded_unused_valid),
        .b_read(decoded_read), .b_address(decoded_read_address),
        .b_rdata(decoded_read_data), .b_valid(decoded_read_valid)
    );
endmodule
`default_nettype wire
