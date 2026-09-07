`timescale 1ns/1ps
`default_nettype none
// Ordered structural/value/state checks before any command effect.
module n2m_uart_validate (
    input var n2m_interfaces_pkg::packet_header_t header,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] packet_bytes,
    input var logic [n2m_interfaces_pkg::LOAD_BEGIN_BYTES*8-1:0] arguments,
    input var logic [7:0] forced_status,
    input var logic [7:0] endpoint_state,
    input var logic image_valid,
    input var logic snapshot_valid,
    input var logic host_address_valid,
    output logic [7:0] status,
    output logic [15:0] response_length
);
    import n2m_interfaces_pkg::*;
    logic command_known, length_valid, value_valid, state_valid;
    logic no_frame;
    logic [32:0] range_end;
    write_host_t write_fields;
    load_begin_t begin_fields;
    read_range_t range_fields;
    assign write_fields = arguments[WRITE_HOST_BYTES*8-1:0];
    assign begin_fields = arguments;
    assign range_fields = arguments[READ_RANGE_BYTES*8-1:0];
    always_comb begin
        command_known = 1;
        length_valid = header.length == 0;
        value_valid = 1;
        state_valid = 1;
        no_frame = 0;
        response_length = 0;
        range_end = {1'b0, range_fields.offset} + {17'b0, range_fields.count};
        case (header.command)
            COMMAND_PING: response_length = 16'(WORD_BYTES);
            COMMAND_READ_HOST: begin
                length_valid = header.length == READ_HOST_BYTES;
                value_valid = host_address_valid;
                response_length = 16'(WORD_BYTES);
            end
            COMMAND_RESET: state_valid = endpoint_state != STATE_LOADING && image_valid;
            COMMAND_RUN: state_valid = endpoint_state == STATE_PAUSED && image_valid;
            COMMAND_HALT: begin
                state_valid = endpoint_state != STATE_LOADING;
                response_length = 16'(DOT_BYTES);
            end
            COMMAND_STEP: begin
                length_valid = header.length == WORD_BYTES;
                value_valid = arguments[31:0] != 0 && arguments[31:0] <= WIRE_STEP_MAX_DOTS;
                state_valid = endpoint_state == STATE_PAUSED && image_valid;
                response_length = 16'(DOT_BYTES);
            end
            COMMAND_LOAD_BEGIN: begin
                length_valid = header.length == LOAD_BEGIN_BYTES;
                value_valid = begin_fields.profile == PROFILE_DIRECT_ID && begin_fields.size == PROFILE_ROM_BYTES;
            end
            COMMAND_LOAD_WRITE: begin
                length_valid = header.length > OFFSET_BYTES;
                range_end = {1'b0, arguments[31:0]} + (33'(header.length) - 33'(OFFSET_BYTES));
                value_valid = range_end <= PROFILE_ROM_BYTES;
                state_valid = endpoint_state == STATE_LOADING;
            end
            COMMAND_LOAD_END: state_valid = endpoint_state == STATE_LOADING;
            COMMAND_READ_ROM, COMMAND_READ_FRAME: begin
                length_valid = header.length == READ_RANGE_BYTES;
                value_valid = range_fields.count != 0 && range_fields.count <= WIRE_MAX_PAYLOAD &&
                    range_end <= (header.command == COMMAND_READ_ROM ? PROFILE_ROM_BYTES : 32'(FRAME_BYTES));
                response_length = range_fields.count;
                if (header.command == COMMAND_READ_ROM)
                    state_valid = endpoint_state == STATE_PAUSED || endpoint_state == STATE_LOADING;
                else no_frame = !snapshot_valid;
            end
            COMMAND_WRITE_HOST: begin
                length_valid = header.length == WRITE_HOST_BYTES;
                value_valid = (write_fields.address == HOST_REG_INPUT &&
                    (write_fields.value & ~HOST_WRITE_MASK_INPUT) == 0) ||
                    (write_fields.address == HOST_REG_INPUT_SOURCE &&
                    (write_fields.value & ~HOST_WRITE_MASK_INPUT_SOURCE) == 0);
                state_valid = endpoint_state != STATE_LOADING;
                response_length = 16'(DOT_BYTES);
            end
            COMMAND_INPUT: begin
                length_valid = header.length == INPUT_BYTES;
                state_valid = endpoint_state != STATE_LOADING;
                response_length = 16'(DOT_BYTES);
            end
            COMMAND_SNAPSHOT: begin
                state_valid = endpoint_state != STATE_LOADING;
                response_length = 16'(SNAPSHOT_BYTES);
            end
            default: command_known = 0;
        endcase
        status = STATUS_OK;
        if (forced_status != STATUS_OK) status = forced_status;
        else if (header.version != WIRE_VERSION) status = STATUS_BAD_VERSION;
        else if (header.length > WIRE_MAX_PAYLOAD ||
            32'(packet_bytes) != PACKET_HEADER_BYTES + 32'(header.length) + 2) status = STATUS_BAD_LENGTH;
        else if (!command_known) status = STATUS_BAD_COMMAND;
        else if (!length_valid) status = STATUS_BAD_LENGTH;
        else if (!value_valid) status = STATUS_BAD_VALUE;
        else if (!state_valid) status = STATUS_BAD_STATE;
        else if (no_frame) status = STATUS_NO_FRAME;
        if (status != STATUS_OK) response_length = 0;
    end
endmodule
`default_nettype wire
