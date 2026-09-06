`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// CPU dispatch before external policy/arbitration. bus_commit is the CPU's
// accepted T4 pulse, not a request to stretch or retry an emulated cycle.
module n2m_memory_cpu_port (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic init_done,
    input var logic request_valid,
    input var logic [15:0] address,
    input var logic write_enable,
    input var logic [7:0] write_data,
    input var logic bus_commit,
    output logic [7:0] read_data,
    output logic response_valid,
    output logic contract_fault,
    output logic storage_read,
    output logic storage_write,
    output n2m_memory_pkg::memory_store_t storage_store,
    output logic [14:0] storage_offset,
    output logic [7:0] storage_wdata,
    input var logic [7:0] storage_rdata,
    input var logic storage_valid,
    output logic owner_prepare,
    output logic owner_commit,
    output n2m_memory_pkg::memory_destination_t owner_destination,
    output logic [15:0] owner_address,
    output logic owner_write,
    output logic [7:0] owner_wdata,
    input var logic [7:0] owner_rdata,
    input var logic owner_valid,
    input var logic owner_service_available
);
    import n2m_memory_pkg::*;
    logic reset, active, direct, committed, service_available;
    logic prepared_read;
    logic [15:0] prepared_address;
    logic fault_now;

    n2m_memory_decode decode (
        .address(address), .destination(owner_destination),
        .store(storage_store), .offset(storage_offset)
    );
    assign reset = reset_sys || core_reset;
    assign active = !reset && !contract_fault && init_done && request_valid;
    assign direct = owner_destination == MEMORY_DIRECT;
    assign service_available = direct || owner_service_available;
    assign committed = active && bus_commit && service_available && (write_enable || response_valid);
    assign storage_read = active && direct && !write_enable;
    assign storage_write = committed && direct && write_enable;
    assign storage_wdata = write_data;
    assign owner_prepare = active && !direct;
    assign owner_commit = committed && !direct;
    assign owner_address = address;
    assign owner_write = write_enable;
    assign owner_wdata = write_data;

    // Raw store validity belongs to the previous enabled read. Compare the
    // complete CPU address before exposing it to a newly prepared request.
    `DFF_ARST_VAL(prepared_read, storage_read, clk_sys, reset, 1'b0)
    `DFF_EN(prepared_address, address, clk_sys, storage_read)
    assign response_valid = active && !write_enable && (direct
        ? (prepared_read && prepared_address == address && storage_valid)
        : (owner_service_available && owner_valid));
    assign read_data = direct ? storage_rdata : owner_rdata;

    // CPU already cancels missing-read completion. A commit seen here without
    // bounded service is an integration violation, never an automatic replay.
    // Writes have a fixed service guarantee, not a read-response handshake.
    assign fault_now = bus_commit && (!active || (!write_enable && !response_valid)
        || (!direct && !owner_service_available));
    `DFF_ARST_VAL(contract_fault, contract_fault || fault_now, clk_sys, reset, 1'b0)
    `N2M_ASSERT(MEMORY_COMMIT_ACTIVE, clk_sys, reset, !bus_commit || active)
    `N2M_ASSERT(MEMORY_COMMIT_READ_SERVICE, clk_sys, reset,
        !(bus_commit && !write_enable) || response_valid)
    `N2M_ASSERT(MEMORY_COMMIT_OWNER_SERVICE, clk_sys, reset,
        !(bus_commit && active && !direct) || owner_service_available)
    `N2M_ASSERT_KNOWN(MEMORY_CPU_CONTROLS, clk_sys, reset,
        {init_done, request_valid, bus_commit})
    `N2M_ASSERT(MEMORY_CPU_REQUEST_KNOWN, clk_sys, reset,
        !request_valid || !$isunknown({address, write_enable, write_data}))
endmodule
