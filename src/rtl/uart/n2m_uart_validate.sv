`timescale 1ns/1ps
`default_nettype none
// Ordered structural/value/state checks before any command effect.
module n2m_uart_validate (
    input var n2m_interfaces_pkg::packet_header_t header,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] packet_bytes,
    input var logic [n2m_uart_pkg::UART_ARGUMENT_BYTES*8-1:0] arguments,
    input var logic [7:0] forced_status,
    input var logic [7:0] endpoint_state,
    input var logic image_valid,
    input var logic snapshot_valid,
    input var logic host_address_valid,
    input var logic sdram_ready,
    input var logic swap_busy,
    input var logic host_loading,
    // Session profile the command owner holds: the LOAD_WRITE and READ_ROM
    // ranges are bounded by that profile's image length.
    input var logic [7:0] profile,
    output logic [7:0] status,
    output logic [15:0] response_length
);
    logic command_known, length_valid, value_valid, state_valid;
    logic no_frame;
    logic [32:0] range_end;
    logic [32:0] session_bytes;
    n2m_interfaces_pkg::write_host_t write_fields;
    n2m_interfaces_pkg::load_begin_t begin_fields;
    n2m_interfaces_pkg::read_range_t range_fields;
    n2m_interfaces_pkg::peek_range_t peek_fields;
    logic [32:0] peek_end;
    n2m_interfaces_pkg::sdram_write_t sdram_write_fields;
    n2m_interfaces_pkg::sdram_read_t sdram_read_fields;
    logic [15:0] sdram_write_bytes;
    logic [7:0] sdram_write_lines;
    logic [32:0] sdram_end;
    assign write_fields = arguments[n2m_interfaces_pkg::WRITE_HOST_BYTES*8-1:0];
    assign begin_fields = arguments[n2m_interfaces_pkg::LOAD_BEGIN_BYTES*8-1:0];
    assign sdram_write_fields = arguments[n2m_interfaces_pkg::SDRAM_WRITE_BYTES*8-1:0];
    assign sdram_read_fields = arguments[n2m_interfaces_pkg::SDRAM_READ_BYTES*8-1:0];
    assign range_fields = arguments[n2m_interfaces_pkg::READ_RANGE_BYTES*8-1:0];
    assign peek_fields = arguments[n2m_interfaces_pkg::PEEK_RANGE_BYTES*8-1:0];
    always_comb begin
        command_known = 1;
        length_valid = header.length == 0;
        value_valid = 1;
        state_valid = 1;
        no_frame = 0;
        response_length = 0;
        range_end = {1'b0, range_fields.offset} + {17'b0, range_fields.count};
        session_bytes = profile == n2m_interfaces_pkg::PROFILE_MBC1_ID
            ? 33'(n2m_interfaces_pkg::MBC1_ROM_BYTES) : 33'(n2m_interfaces_pkg::PROFILE_ROM_BYTES);
        peek_end = {1'b0, peek_fields.offset} + {17'b0, peek_fields.count};
        // SDRAM_WRITE carries its line count in the payload length: 4 + 16 n.
        sdram_write_bytes = header.length - 16'(n2m_interfaces_pkg::SDRAM_WRITE_BYTES);
        sdram_write_lines = sdram_write_bytes[11:4];
        sdram_end = header.command == n2m_interfaces_pkg::COMMAND_SDRAM_WRITE
            ? {1'b0, sdram_write_fields.address} + ({25'b0, sdram_write_lines} << 4)
            : {1'b0, sdram_read_fields.address} + ({25'b0, sdram_read_fields.count} << 4);
        case (header.command)
            n2m_interfaces_pkg::COMMAND_PING: response_length = 16'(n2m_interfaces_pkg::WORD_BYTES);
            n2m_interfaces_pkg::COMMAND_READ_HOST: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::READ_HOST_BYTES;
                value_valid = host_address_valid;
                response_length = 16'(n2m_interfaces_pkg::WORD_BYTES);
            end
            n2m_interfaces_pkg::COMMAND_RESET: state_valid = endpoint_state != n2m_interfaces_pkg::STATE_LOADING && image_valid;
            n2m_interfaces_pkg::COMMAND_RUN: state_valid = endpoint_state == n2m_interfaces_pkg::STATE_PAUSED && image_valid;
            n2m_interfaces_pkg::COMMAND_HALT: begin
                state_valid = endpoint_state != n2m_interfaces_pkg::STATE_LOADING;
                response_length = 16'(n2m_interfaces_pkg::DOT_BYTES);
            end
            n2m_interfaces_pkg::COMMAND_STEP: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::WORD_BYTES;
                value_valid = arguments[31:0] != 0 && arguments[31:0] <= n2m_interfaces_pkg::WIRE_STEP_MAX_DOTS;
                state_valid = endpoint_state == n2m_interfaces_pkg::STATE_PAUSED && image_valid;
                response_length = 16'(n2m_interfaces_pkg::DOT_BYTES);
            end
            n2m_interfaces_pkg::COMMAND_RUN_DOTS: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::WORD_BYTES;
                value_valid = arguments[31:0] != 0 && arguments[31:0] <= n2m_interfaces_pkg::WIRE_RUN_DOTS_MAX;
                state_valid = endpoint_state == n2m_interfaces_pkg::STATE_PAUSED && image_valid;
                response_length = 16'(n2m_interfaces_pkg::RUN_DOTS_BYTES);
            end
            n2m_interfaces_pkg::COMMAND_LOAD_BEGIN: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::LOAD_BEGIN_BYTES;
                value_valid = ((begin_fields.profile == n2m_interfaces_pkg::PROFILE_DIRECT_ID ||
                    begin_fields.profile == n2m_interfaces_pkg::PROFILE_LOADER_ID) &&
                    begin_fields.size == n2m_interfaces_pkg::PROFILE_ROM_BYTES) ||
                    (begin_fields.profile == n2m_interfaces_pkg::PROFILE_MBC1_ID &&
                    begin_fields.size == n2m_interfaces_pkg::MBC1_ROM_BYTES);
                // A swap in progress owns the ROM store; the host retries.
                state_valid = !swap_busy;
            end
            n2m_interfaces_pkg::COMMAND_LOAD_WRITE: begin
                length_valid = 32'(header.length) > n2m_interfaces_pkg::OFFSET_BYTES;
                range_end = {1'b0, arguments[31:0]} + (33'(header.length) - 33'(n2m_interfaces_pkg::OFFSET_BYTES));
                value_valid = range_end <= session_bytes;
                // LOADING also covers a swap or an engine-invalidated image;
                // only the open host session may write or end a load.
                state_valid = host_loading;
            end
            n2m_interfaces_pkg::COMMAND_LOAD_END: state_valid = host_loading;
            n2m_interfaces_pkg::COMMAND_READ_ROM, n2m_interfaces_pkg::COMMAND_READ_FRAME: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::READ_RANGE_BYTES;
                value_valid = range_fields.count != 0 && range_fields.count <= n2m_interfaces_pkg::WIRE_MAX_PAYLOAD &&
                    range_end <= (header.command == n2m_interfaces_pkg::COMMAND_READ_ROM ? session_bytes : 33'(n2m_interfaces_pkg::FRAME_BYTES));
                response_length = range_fields.count;
                if (header.command == n2m_interfaces_pkg::COMMAND_READ_ROM)
                    state_valid = endpoint_state == n2m_interfaces_pkg::STATE_PAUSED || endpoint_state == n2m_interfaces_pkg::STATE_LOADING;
                else no_frame = !snapshot_valid;
            end
            n2m_interfaces_pkg::COMMAND_WRITE_HOST: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::WRITE_HOST_BYTES;
                value_valid = (write_fields.address == n2m_interfaces_pkg::HOST_REG_INPUT &&
                    (write_fields.value & ~n2m_interfaces_pkg::HOST_WRITE_MASK_INPUT) == 0) ||
                    (write_fields.address == n2m_interfaces_pkg::HOST_REG_INPUT_SOURCE &&
                    (write_fields.value & ~n2m_interfaces_pkg::HOST_WRITE_MASK_INPUT_SOURCE) == 0) ||
                    (write_fields.address == n2m_interfaces_pkg::HOST_REG_LIBRARY_CONTROL &&
                    (write_fields.value & ~n2m_interfaces_pkg::HOST_WRITE_MASK_LIBRARY_CONTROL) == 0);
                state_valid = endpoint_state != n2m_interfaces_pkg::STATE_LOADING;
                response_length = 16'(n2m_interfaces_pkg::DOT_BYTES);
            end
            n2m_interfaces_pkg::COMMAND_INPUT: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::INPUT_BYTES;
                state_valid = endpoint_state != n2m_interfaces_pkg::STATE_LOADING;
                response_length = 16'(n2m_interfaces_pkg::DOT_BYTES);
            end
            // Host peek is read-only and served only while the core is paused.
            // Unknown stores and out-of-range requests are rejected here,
            // before any product command reaches a store.
            n2m_interfaces_pkg::COMMAND_PEEK: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::PEEK_RANGE_BYTES;
                value_valid = n2m_memory_pkg::peek_known(peek_fields.store) &&
                    peek_fields.count != 0 && peek_fields.count <= n2m_interfaces_pkg::WIRE_MAX_PAYLOAD &&
                    peek_end <= {1'b0, n2m_memory_pkg::peek_bytes(peek_fields.store)};
                state_valid = endpoint_state == n2m_interfaces_pkg::STATE_PAUSED;
                response_length = peek_fields.count;
            end
            n2m_interfaces_pkg::COMMAND_SNAPSHOT: begin
                state_valid = endpoint_state != n2m_interfaces_pkg::STATE_LOADING;
                response_length = 16'(n2m_interfaces_pkg::SNAPSHOT_BYTES);
            end
            // SDRAM lines are accepted in every endpoint state; a misaligned or
            // out-of-device range, or an uninitialized SDRAM, is BAD_VALUE. A
            // write payload that is not the address plus 1-15 whole lines is
            // BAD_LENGTH; sixteen lines already exceed the payload limit.
            n2m_interfaces_pkg::COMMAND_SDRAM_WRITE: begin
                length_valid = 32'(header.length) > n2m_interfaces_pkg::SDRAM_WRITE_BYTES &&
                    sdram_write_bytes[3:0] == 4'd0 &&
                    sdram_write_lines <= n2m_interfaces_pkg::SDRAM_WRITE_MAX_LINES;
                value_valid = sdram_ready && sdram_write_fields.address[3:0] == 4'd0 &&
                    sdram_end <= {1'b0, n2m_interfaces_pkg::SDRAM_BYTES};
            end
            n2m_interfaces_pkg::COMMAND_SDRAM_READ: begin
                length_valid = 32'(header.length) == n2m_interfaces_pkg::SDRAM_READ_BYTES;
                value_valid = sdram_ready && sdram_read_fields.address[3:0] == 4'd0 &&
                    sdram_read_fields.count != 8'd0 && sdram_read_fields.count <= n2m_interfaces_pkg::SDRAM_READ_MAX_LINES &&
                    sdram_end <= {1'b0, n2m_interfaces_pkg::SDRAM_BYTES};
                response_length = 16'({4'd0, sdram_read_fields.count, 4'd0});
            end
            default: command_known = 0;
        endcase
        status = n2m_interfaces_pkg::STATUS_OK;
        if (forced_status != n2m_interfaces_pkg::STATUS_OK) status = forced_status;
        else if (header.version != n2m_interfaces_pkg::WIRE_VERSION) status = n2m_interfaces_pkg::STATUS_BAD_VERSION;
        else if (header.length > n2m_interfaces_pkg::WIRE_MAX_PAYLOAD ||
            32'(packet_bytes) != n2m_interfaces_pkg::PACKET_HEADER_BYTES + 32'(header.length) + 2) status = n2m_interfaces_pkg::STATUS_BAD_LENGTH;
        else if (!command_known) status = n2m_interfaces_pkg::STATUS_BAD_COMMAND;
        else if (!length_valid) status = n2m_interfaces_pkg::STATUS_BAD_LENGTH;
        else if (!value_valid) status = n2m_interfaces_pkg::STATUS_BAD_VALUE;
        else if (!state_valid) status = n2m_interfaces_pkg::STATUS_BAD_STATE;
        else if (no_frame) status = n2m_interfaces_pkg::STATUS_NO_FRAME;
        if (status != n2m_interfaces_pkg::STATUS_OK) response_length = 0;
    end
endmodule
`default_nettype wire
