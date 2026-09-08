`timescale 1ns/1ps
`default_nettype none

// Fixed banks: 0 last request, 1 last response, 2 staged current response.
// The exchange controller owns validity and publication, never the RAM array.
module n2m_uart_exchange_store (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic [2:0] write_enable,
    input var logic [3*n2m_uart_pkg::UART_ADDRESS_BITS-1:0] write_address,
    input var logic [23:0] write_data,
    input var logic [2:0] read_enable,
    input var logic [3*n2m_uart_pkg::UART_ADDRESS_BITS-1:0] read_address,
    output logic [23:0] read_data,
    output logic [2:0] read_valid
);
    genvar bank;
    generate for (bank = 0; bank < 3; bank = bank + 1) begin : banks
        logic [7:0] unused_data;
        logic unused_valid;
        n2m_intel_ram #(
            .DEPTH(n2m_uart_pkg::UART_RAW_MAX), .DATA_BITS(8), .ADDRESS_BITS(n2m_uart_pkg::UART_ADDRESS_BITS)
        ) memory (
            .clk_a(clk_sys), .clk_b(clk_sys),
            .reset_a(reset_sys), .reset_b(reset_sys),
            .a_read(1'b0), .a_write(write_enable[bank]),
            .a_address(write_address[bank*n2m_uart_pkg::UART_ADDRESS_BITS +: n2m_uart_pkg::UART_ADDRESS_BITS]),
            .a_wdata(write_data[bank*8 +: 8]),
            .a_byte_enable(1'b1), .a_rdata(unused_data), .a_valid(unused_valid),
            .b_read(read_enable[bank]),
            .b_address(read_address[bank*n2m_uart_pkg::UART_ADDRESS_BITS +: n2m_uart_pkg::UART_ADDRESS_BITS]),
            .b_rdata(read_data[bank*8 +: 8]), .b_valid(read_valid[bank])
        );
    end endgenerate
endmodule
`default_nettype wire
