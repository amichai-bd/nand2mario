`timescale 1ns/1ps
`default_nettype none

// One presence bit per ROM byte. The load owner explicitly sweeps zero and
// marks accepted writes; resetting transport does not initialize this RAM.
module n2m_uart_presence_store (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic write_enable,
    input var logic [$clog2(n2m_interfaces_pkg::PROFILE_ROM_BYTES)-1:0] write_address,
    input var logic write_present,
    input var logic read_enable,
    input var logic [$clog2(n2m_interfaces_pkg::PROFILE_ROM_BYTES)-1:0] read_address,
    output logic read_present,
    output logic read_valid
);
    logic unused_data;
    logic unused_valid;
    n2m_intel_ram #(
        .DEPTH(n2m_interfaces_pkg::PROFILE_ROM_BYTES), .DATA_BITS(1),
        .ADDRESS_BITS($clog2(n2m_interfaces_pkg::PROFILE_ROM_BYTES))
    ) u_presence (
        .clk_a(clk_sys), .clk_b(clk_sys),
        .reset_a(reset_sys), .reset_b(reset_sys),
        .a_read(1'b0), .a_write(write_enable), .a_address(write_address),
        .a_wdata(write_present), .a_byte_enable(1'b1),
        .a_rdata(unused_data), .a_valid(unused_valid),
        .b_read(read_enable), .b_address(read_address),
        .b_rdata(read_present), .b_valid(read_valid)
    );
endmodule
`default_nettype wire
