`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Single-clock storage primitive. Contract: memory/MAS_memory.md.
// Both read ports return the pre-write value on a same-edge address collision.
module n2m_memory_ram #(
    parameter integer DEPTH = 8192,
    parameter integer ADDRESS_BITS = $clog2(DEPTH),
    parameter integer DATA_BITS = 8
) (
    input var logic clk_sys,
    input var logic reset,
    input var logic a_read,
    input var logic a_write,
    input var logic [ADDRESS_BITS-1:0] a_address,
    input var logic [DATA_BITS-1:0] a_wdata,
    output logic [DATA_BITS-1:0] a_rdata,
    output logic a_valid,
    input var logic b_read,
    input var logic [ADDRESS_BITS-1:0] b_address,
    output logic [DATA_BITS-1:0] b_rdata,
    output logic b_valid
);
    (* ramstyle = "M9K" *) logic [DATA_BITS-1:0] storage [0:DEPTH-1];
    logic a_read_enable, b_read_enable, write_enable;
    logic a_valid_register, b_valid_register;
    assign a_read_enable = a_read && !reset;
    assign b_read_enable = b_read && !reset;
    assign write_enable = a_write && !reset;
    assign a_valid = a_valid_register && !reset;
    assign b_valid = b_valid_register && !reset;

    // The array has no reset. Its owner initializes contents by ordinary writes.
    // Nonblocking read/write semantics select old data; no no_rw_check waiver.
    `DFF_EN(storage[a_address], a_wdata, clk_sys, write_enable)
    `DFF_EN(a_rdata, storage[a_address], clk_sys, a_read_enable)
    `DFF_EN(b_rdata, storage[b_address], clk_sys, b_read_enable)
    `DFF_ARST_VAL(a_valid_register, a_read_enable, clk_sys, reset, 1'b0)
    `DFF_ARST_VAL(b_valid_register, b_read_enable, clk_sys, reset, 1'b0)

    `N2M_ASSERT(MEMORY_RAM_A_RANGE, clk_sys, reset,
        !(a_read || a_write) || int'(a_address) < DEPTH)
    `N2M_ASSERT(MEMORY_RAM_B_RANGE, clk_sys, reset,
        !b_read || int'(b_address) < DEPTH)
    `N2M_ASSERT(MEMORY_RAM_A_KNOWN, clk_sys, reset,
        !(a_read || a_write) || !$isunknown(a_address))
    `N2M_ASSERT(MEMORY_RAM_B_KNOWN, clk_sys, reset,
        !b_read || !$isunknown(b_address))
    `N2M_ASSERT(MEMORY_RAM_WRITE_KNOWN, clk_sys, reset,
        !a_write || !$isunknown(a_wdata))
endmodule
