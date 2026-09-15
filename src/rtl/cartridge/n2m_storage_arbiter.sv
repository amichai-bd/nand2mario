`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Storage arbiter: the copy engine, the host SDRAM bridge and the future boot
// copier share the controller's single line request interface. Contract:
// wiki/src/rtl/cartridge/MAS_loader_profile.md#storage-arbiter.
// A grant is registered (one edge of acceptance latency); the granted request
// is held until the controller accepts it and a read response returns to the
// granted client only, with no added latency. While the engine swaps an image
// the host waits; during a window fill the two alternate. The copier client
// has priority while it is active and is tied off until its slice exists.
module n2m_storage_arbiter (
    input var logic clk_sys,
    input var logic reset_sys,
    // Engine client (fills and swaps).
    input var logic engine_valid,
    input var logic engine_write,
    input var logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] engine_address,
    input var logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] engine_data,
    output logic engine_ready,
    output logic engine_response_valid,
    input var logic swap_busy,
    // Host client (SDRAM_WRITE / SDRAM_READ).
    input var logic host_valid,
    input var logic host_write,
    input var logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] host_address,
    input var logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] host_data,
    output logic host_ready,
    output logic host_response_valid,
    // Boot copier client hook (wiki/src/rtl/storage/MAS_flash_library.md).
    input var logic copier_active,
    input var logic copier_valid,
    input var logic copier_write,
    input var logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] copier_address,
    input var logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] copier_data,
    output logic copier_ready,
    output logic copier_response_valid,
    // Controller side.
    output logic request_valid,
    output logic request_write,
    output logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] request_address,
    output logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] request_data,
    input var logic request_ready,
    input var logic response_valid
);
    typedef enum logic [1:0] { CLIENT_ENGINE, CLIENT_HOST, CLIENT_COPIER } client_t;
    typedef enum logic [1:0] { IDLE, REQUEST, RESPONSE } state_t;
    state_t state, state_next;
    client_t grant, grant_next;
    logic last_engine, last_engine_next;
    logic accepted;

    assign accepted = state == REQUEST && request_ready;
    assign request_valid = state == REQUEST && !reset_sys;
    always_comb begin
        request_write = engine_write;
        request_address = engine_address;
        request_data = engine_data;
        case (grant)
            CLIENT_HOST: begin request_write = host_write; request_address = host_address; request_data = host_data; end
            CLIENT_COPIER: begin request_write = copier_write; request_address = copier_address; request_data = copier_data; end
            default: begin end
        endcase
    end
    assign engine_ready = accepted && grant == CLIENT_ENGINE;
    assign host_ready = accepted && grant == CLIENT_HOST;
    assign copier_ready = accepted && grant == CLIENT_COPIER;
    assign engine_response_valid = state == RESPONSE && response_valid && grant == CLIENT_ENGINE;
    assign host_response_valid = state == RESPONSE && response_valid && grant == CLIENT_HOST;
    assign copier_response_valid = state == RESPONSE && response_valid && grant == CLIENT_COPIER;
    always_comb begin
        state_next = state;
        grant_next = grant;
        last_engine_next = last_engine;
        case (state)
            IDLE: begin
                if (copier_active && copier_valid) begin grant_next = CLIENT_COPIER; state_next = REQUEST; end
                else if (engine_valid && (swap_busy || !host_valid || !last_engine)) begin
                    grant_next = CLIENT_ENGINE; state_next = REQUEST;
                end else if (host_valid && !swap_busy && !copier_active) begin
                    grant_next = CLIENT_HOST; state_next = REQUEST;
                end
            end
            REQUEST: if (request_ready) begin
                last_engine_next = grant == CLIENT_ENGINE;
                state_next = request_write ? IDLE : RESPONSE;
            end
            RESPONSE: if (response_valid) state_next = IDLE;
            default: state_next = IDLE;
        endcase
    end
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(grant, grant_next, clk_sys, reset_sys, CLIENT_ENGINE)
    `DFF_ARST_VAL(last_engine, last_engine_next, clk_sys, reset_sys, 1'b0)
    // A granted client must hold its request until acceptance.
    `N2M_ASSERT(LOADER_ARBITER_HELD, clk_sys, reset_sys,
        state == REQUEST |-> (grant == CLIENT_ENGINE && engine_valid) ||
            (grant == CLIENT_HOST && host_valid) || (grant == CLIENT_COPIER && copier_valid))
    `N2M_ASSERT(LOADER_ARBITER_RESPONSE_EXPECTED, clk_sys, reset_sys,
        response_valid |-> state == RESPONSE)
    `N2M_ASSERT(LOADER_ARBITER_HOST_WAITS, clk_sys, reset_sys,
        !(state == IDLE && swap_busy && grant_next == CLIENT_HOST && state_next == REQUEST))
endmodule
`default_nettype wire
