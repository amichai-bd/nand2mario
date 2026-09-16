`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// ROM store host port (port A) arbiter between the UART load owner and the
// copy engine. Contract:
// wiki/src/rtl/cartridge/MAS_loader_profile.md#copy-engine-and-rom-store-port-ownership.
// The engine owns the port while it copies; the UART load owner owns it in a
// host load session and keeps it for its readback otherwise. The endpoint and
// the loader never let both own the port on one edge, which the named
// assertions check; the engine never reads.
module n2m_rom_port_arbiter (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic uart_owns,
    input var logic uart_write,
    input var logic uart_read,
    input var logic [15:0] uart_address,
    input var logic [7:0] uart_wdata,
    input var logic engine_owns,
    input var logic engine_write,
    input var logic [14:0] engine_address,
    input var logic [7:0] engine_wdata,
    output logic host_write,
    output logic host_read,
    output logic [31:0] host_offset,
    output logic [7:0] host_wdata
);
    assign host_write = engine_owns ? engine_write : uart_write;
    assign host_read = engine_owns ? 1'b0 : uart_read;
    // The engine copies 32 KiB images and 16 KiB windows into the low half
    // of the store; the UART load owner addresses the whole store.
    assign host_offset = {16'd0, engine_owns ? {1'b0, engine_address} : uart_address};
    assign host_wdata = engine_owns ? engine_wdata : uart_wdata;
    `N2M_ASSERT(LOADER_PORT_EXCLUSIVE, clk_sys, reset_sys, !(engine_owns && uart_owns))
    `N2M_ASSERT(LOADER_FILL_HOST_PORT, clk_sys, reset_sys,
        !engine_write || (engine_owns && !uart_write && !uart_read))
endmodule
`default_nettype wire
