`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Copy engine: moves a 16 KiB window bank or a 32 KiB image from SDRAM into
// the ROM store through its host port (port A). Contract:
// wiki/src/rtl/cartridge/MAS_loader_profile.md#select-register and
// #copy-engine-and-rom-store-port-ownership.
// A swap reads the catalogue entry, pauses the core through the core control
// owner, clears image_valid, copies the image while accumulating CRC-32 over
// the bytes written, compares, publishes the profile and requests a core
// reset, then releases its pause. A fill copies one bank into the upper half
// while the core runs. One line is in flight at a time; the next line is
// requested while the previous one is written, so the copy is SDRAM-bound.
module n2m_loader_engine (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic start,
    input var logic start_swap,
    input var logic [6:0] start_index,
    output logic busy,
    output logic done,
    output logic swap_job,
    output logic result_write,
    output logic [7:0] result_value,
    // Storage arbiter client: reads only.
    output logic sdram_valid,
    output logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] sdram_address,
    input var logic sdram_ready,
    input var logic sdram_response_valid,
    input var logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] sdram_response_data,
    // ROM store host port through the port arbiter.
    output logic rom_write,
    output logic [14:0] rom_address,
    output logic [7:0] rom_wdata,
    // Core control owner: pause level and reset request handshake.
    output logic pause_hold,
    output logic reset_request,
    input var logic reset_accept,
    input var logic reset_done,
    input var logic paused,
    input var logic release_fault_hold,
    // Image validity, owned by the endpoint's command owner.
    input var logic image_valid,
    output logic image_invalidate,
    output logic image_publish,
    output logic [7:0] image_profile
);
    localparam integer LINE_BYTES = 32'(n2m_interfaces_pkg::SDRAM_LINE_BYTES);
    localparam integer ADDRESS_BITS = 32'(n2m_interfaces_pkg::SDRAM_ADDRESS_BITS);
    localparam integer SWAP_LINES = 32'(n2m_interfaces_pkg::LIBRARY_SLOT_BYTES) / LINE_BYTES;
    localparam integer FILL_LINES = 32'(n2m_interfaces_pkg::LIBRARY_WINDOW_BYTES) / LINE_BYTES;
    typedef enum logic [3:0] {
        IDLE, CAT_REQ, CAT_WAIT, CHECK, PAUSE, INVALIDATE, COPY, COMPARE, PUBLISH,
        RESET_REQ, RESET_WAIT, RELEASE, DONE
    } state_t;
    typedef enum logic [1:0] { FETCH_REQ, FETCH_WAIT, FETCH_DONE } fetch_t;
    state_t state, state_next;
    fetch_t fetch, fetch_next;
    logic [6:0] index, index_next;
    logic cat_second, cat_second_next;
    n2m_interfaces_pkg::catalogue_entry_t entry, entry_next;
    logic [ADDRESS_BITS-1:0] line_address, line_address_next;
    logic [11:0] lines_left, lines_left_next;
    logic [LINE_BYTES*8-1:0] buffer, buffer_next, write_line, write_line_next;
    logic buffer_full, buffer_full_next, writing, writing_next;
    logic [3:0] byte_index, byte_index_next;
    logic [14:0] write_offset, write_offset_next;
    logic [31:0] crc, crc_next;
    logic fault_hold, fault_hold_next;
    logic entry_ok, crc_match;
    logic [7:0] result_next;
    logic result_write_next;

    assign busy = state != IDLE;
    assign done = state == DONE;
    assign sdram_valid = (state == CAT_REQ || (state == COPY && fetch == FETCH_REQ)) && !reset_sys;
    assign sdram_address = line_address;
    assign rom_write = state == COPY && writing && !reset_sys;
    assign rom_address = write_offset;
    assign rom_wdata = write_line[byte_index*8 +: 8];
    assign pause_hold = fault_hold || (state == PAUSE || state == INVALIDATE || (state == COPY && swap_job) ||
        state == COMPARE || state == PUBLISH || state == RESET_REQ || state == RESET_WAIT);
    assign reset_request = state == RESET_REQ && !reset_sys;
    assign image_invalidate = state == INVALIDATE && !reset_sys;
    assign image_publish = state == PUBLISH && !reset_sys;
    assign image_profile = entry.profile;
    assign entry_ok = entry.valid == n2m_interfaces_pkg::LIBRARY_CATALOGUE_VALID &&
        32'(entry.length) == 32'(n2m_interfaces_pkg::LIBRARY_SLOT_BYTES) &&
        (entry.profile == n2m_interfaces_pkg::PROFILE_DIRECT_ID || entry.profile == n2m_interfaces_pkg::PROFILE_LOADER_ID);
    assign crc_match = (crc ^ n2m_interfaces_pkg::WIRE_CRC32_INIT) == entry.crc32;

    always_comb begin
        state_next = state;
        fetch_next = fetch;
        index_next = index;
        cat_second_next = cat_second;
        entry_next = entry;
        line_address_next = line_address;
        lines_left_next = lines_left;
        buffer_next = buffer;
        buffer_full_next = buffer_full;
        write_line_next = write_line;
        writing_next = writing;
        byte_index_next = byte_index;
        write_offset_next = write_offset;
        crc_next = crc;
        fault_hold_next = fault_hold && !release_fault_hold;
        result_next = result_value;
        result_write_next = 1'b0;
        case (state)
            IDLE: if (start) begin
                // A hold from an earlier CRC mismatch stays until a valid image
                // is published; the catalogue check must not let the core run.
                index_next = start_index;
                crc_next = n2m_interfaces_pkg::WIRE_CRC32_INIT;
                fetch_next = FETCH_REQ;
                buffer_full_next = 1'b0;
                writing_next = 1'b0;
                cat_second_next = 1'b0;
                if (start_swap) begin
                    line_address_next = ADDRESS_BITS'(n2m_interfaces_pkg::LIBRARY_CATALOGUE_ADDRESS) +
                        ADDRESS_BITS'({start_index, 5'd0});
                    state_next = CAT_REQ;
                end else begin
                    line_address_next = ADDRESS_BITS'({start_index[5:0], 14'd0});
                    lines_left_next = 12'(FILL_LINES);
                    write_offset_next = 15'h4000;
                    state_next = COPY;
                end
            end
            // Two catalogue lines; the entry record is the low line first.
            CAT_REQ: if (sdram_ready) begin
                line_address_next = line_address + ADDRESS_BITS'(LINE_BYTES);
                state_next = CAT_WAIT;
            end
            CAT_WAIT: if (sdram_response_valid) begin
                if (cat_second) begin
                    entry_next[255:128] = sdram_response_data;
                    state_next = CHECK;
                end else begin
                    entry_next[127:0] = sdram_response_data;
                    cat_second_next = 1'b1;
                    state_next = CAT_REQ;
                end
            end
            CHECK: begin
                if (entry_ok) state_next = PAUSE;
                else begin
                    result_next = n2m_interfaces_pkg::LIBRARY_RESULT_INVALID_SLOT;
                    result_write_next = 1'b1;
                    state_next = DONE;
                end
            end
            PAUSE: if (paused) state_next = INVALIDATE;
            INVALIDATE: begin
                line_address_next = ADDRESS_BITS'({index, 15'd0});
                lines_left_next = 12'(SWAP_LINES);
                write_offset_next = 15'd0;
                state_next = COPY;
            end
            COPY: begin
                case (fetch)
                    FETCH_REQ: if (sdram_ready) begin
                        line_address_next = line_address + ADDRESS_BITS'(LINE_BYTES);
                        lines_left_next = lines_left - 12'd1;
                        fetch_next = FETCH_WAIT;
                    end
                    FETCH_WAIT: if (sdram_response_valid) begin
                        buffer_next = sdram_response_data;
                        buffer_full_next = 1'b1;
                        fetch_next = lines_left == 12'd0 ? FETCH_DONE : FETCH_REQ;
                    end
                    default: begin end
                endcase
                if (writing) begin
                    crc_next = n2m_uart_pkg::crc32_byte(crc, rom_wdata);
                    byte_index_next = byte_index + 4'd1;
                    write_offset_next = write_offset + 15'd1;
                    if (byte_index == 4'd15) writing_next = 1'b0;
                end else if (buffer_full) begin
                    write_line_next = buffer;
                    buffer_full_next = 1'b0;
                    byte_index_next = 4'd0;
                    writing_next = 1'b1;
                end
                if (fetch == FETCH_DONE && !writing && !buffer_full)
                    state_next = swap_job ? COMPARE : DONE;
            end
            COMPARE: begin
                if (crc_match) state_next = PUBLISH;
                else begin
                    result_next = n2m_interfaces_pkg::LIBRARY_RESULT_CRC_MISMATCH;
                    result_write_next = 1'b1;
                    fault_hold_next = 1'b1;
                    state_next = DONE;
                end
            end
            PUBLISH: begin
                result_next = n2m_interfaces_pkg::LIBRARY_RESULT_OK;
                result_write_next = 1'b1;
                fault_hold_next = 1'b0;
                state_next = RESET_REQ;
            end
            RESET_REQ: if (reset_accept) state_next = RESET_WAIT;
            RESET_WAIT: if (reset_done) state_next = RELEASE;
            RELEASE: state_next = DONE;
            DONE: state_next = IDLE;
            default: state_next = IDLE;
        endcase
    end
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(fetch, fetch_next, clk_sys, reset_sys, FETCH_DONE)
    `DFF_ARST_VAL(index, index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(swap_job, start && state == IDLE ? start_swap : swap_job, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(cat_second, cat_second_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(entry, entry_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(line_address, line_address_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(lines_left, lines_left_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(buffer, buffer_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(buffer_full, buffer_full_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(write_line, write_line_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(writing, writing_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(byte_index, byte_index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(write_offset, write_offset_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(crc, crc_next, clk_sys, reset_sys, n2m_interfaces_pkg::WIRE_CRC32_INIT)
    `DFF_ARST_VAL(fault_hold, fault_hold_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(result_value, result_next, clk_sys, reset_sys, n2m_interfaces_pkg::LIBRARY_RESULT_NONE)
    `DFF_ARST_VAL(result_write, result_write_next, clk_sys, reset_sys, 1'b0)

    `N2M_ASSERT(LOADER_ENGINE_START_IDLE, clk_sys, reset_sys, start |-> !busy)
    `N2M_ASSERT(LOADER_SWAP_PAUSED, clk_sys, reset_sys, rom_write && swap_job |-> paused)
    `N2M_ASSERT(LOADER_FILL_UPPER_ONLY, clk_sys, reset_sys, rom_write && !swap_job |-> rom_address[14])
    `N2M_ASSERT(LOADER_IMAGE_INVALID_BEFORE_WRITE, clk_sys, reset_sys, rom_write && swap_job |-> !image_valid)
    `N2M_ASSERT(LOADER_VALID_IMPLIES_CRC, clk_sys, reset_sys, image_publish |-> crc_match)
    // One line in flight: a response never lands on a buffer still waiting.
    `N2M_ASSERT(LOADER_ENGINE_BUFFER_FREE, clk_sys, reset_sys,
        sdram_response_valid && state == COPY |-> fetch == FETCH_WAIT && !buffer_full)
    `N2M_ASSERT(LOADER_ENGINE_RESPONSE_EXPECTED, clk_sys, reset_sys,
        sdram_response_valid |-> state == CAT_WAIT || (state == COPY && fetch == FETCH_WAIT))
endmodule
`default_nettype wire
