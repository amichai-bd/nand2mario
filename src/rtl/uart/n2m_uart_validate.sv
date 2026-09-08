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
    logic command_known, length_valid, value_valid, state_valid;
    logic no_frame;
    logic [32:0] range_end;
    n2m_interfaces_pkg::write_host_t write_fields;
    n2m_interfaces_pkg::load_begin_t begin_fields;
    n2m_interfaces_pkg::read_range_t range_fields;
    assign write_fields = arguments[n2m_interfaces_pkg::WRITE_HOST_BYTES*8-1:0];
    assign begin_fields = arguments;
    assign range_fields = arguments[n2m_interfaces_pkg::READ_RANGE_BYTES*8-1:0];
    always_comb begin
        command_known = 1;
        length_valid = header.length == 0;
        value_valid = 1;
        state_valid = 1;
        no_frame = 0;
        response_length = 0;
        range_end = {1'b0, range_fields.offset} + {17'b0, range_fields.count};
        case (header.command)
            n2m_interfaces_pkg::COMMAND_PING: response_length = 16'(n2m_interfaces_pkg::WORD_BYTES);
            n2m_interfaces_pkg::COMMAND_READ_HOST: begin
                length_valid = header.length == n2m_interfaces_pkg::READ_HOST_BYTES;
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
                length_valid = header.length == n2m_interfaces_pkg::WORD_BYTES;
                value_valid = arguments[31:0] != 0 && arguments[31:0] <= n2m_interfaces_pkg::WIRE_STEP_MAX_DOTS;
                state_valid = endpoint_state == n2m_interfaces_pkg::STATE_PAUSED && image_valid;
                response_length = 16'(n2m_interfaces_pkg::DOT_BYTES);
            end
            n2m_interfaces_pkg::COMMAND_LOAD_BEGIN: begin
                length_valid = header.length == n2m_interfaces_pkg::LOAD_BEGIN_BYTES;
                value_valid = begin_fields.profile == n2m_interfaces_pkg::PROFILE_DIRECT_ID && begin_fields.size == n2m_interfaces_pkg::PROFILE_ROM_BYTES;
            end
            n2m_interfaces_pkg::COMMAND_LOAD_WRITE: begin
                length_valid = header.length > n2m_interfaces_pkg::OFFSET_BYTES;
                range_end = {1'b0, arguments[31:0]} + (33'(header.length) - 33'(n2m_interfaces_pkg::OFFSET_BYTES));
                value_valid = range_end <= n2m_interfaces_pkg::PROFILE_ROM_BYTES;
                state_valid = endpoint_state == n2m_interfaces_pkg::STATE_LOADING;
            end
            n2m_interfaces_pkg::COMMAND_LOAD_END: state_valid = endpoint_state == n2m_interfaces_pkg::STATE_LOADING;
            n2m_interfaces_pkg::COMMAND_READ_ROM, n2m_interfaces_pkg::COMMAND_READ_FRAME: begin
                length_valid = header.length == n2m_interfaces_pkg::READ_RANGE_BYTES;
                value_valid = range_fields.count != 0 && range_fields.count <= n2m_interfaces_pkg::WIRE_MAX_PAYLOAD &&
                    range_end <= (header.command == n2m_interfaces_pkg::COMMAND_READ_ROM ? n2m_interfaces_pkg::PROFILE_ROM_BYTES : 32'(n2m_interfaces_pkg::FRAME_BYTES));
                response_length = range_fields.count;
                if (header.command == n2m_interfaces_pkg::COMMAND_READ_ROM)
                    state_valid = endpoint_state == n2m_interfaces_pkg::STATE_PAUSED || endpoint_state == n2m_interfaces_pkg::STATE_LOADING;
                else no_frame = !snapshot_valid;
            end
            n2m_interfaces_pkg::COMMAND_WRITE_HOST: begin
                length_valid = header.length == n2m_interfaces_pkg::WRITE_HOST_BYTES;
                value_valid = (write_fields.address == n2m_interfaces_pkg::HOST_REG_INPUT &&
                    (write_fields.value & ~n2m_interfaces_pkg::HOST_WRITE_MASK_INPUT) == 0) ||
                    (write_fields.address == n2m_interfaces_pkg::HOST_REG_INPUT_SOURCE &&
                    (write_fields.value & ~n2m_interfaces_pkg::HOST_WRITE_MASK_INPUT_SOURCE) == 0);
                state_valid = endpoint_state != n2m_interfaces_pkg::STATE_LOADING;
                response_length = 16'(n2m_interfaces_pkg::DOT_BYTES);
            end
            n2m_interfaces_pkg::COMMAND_INPUT: begin
                length_valid = header.length == n2m_interfaces_pkg::INPUT_BYTES;
                state_valid = endpoint_state != n2m_interfaces_pkg::STATE_LOADING;
                response_length = 16'(n2m_interfaces_pkg::DOT_BYTES);
            end
            n2m_interfaces_pkg::COMMAND_SNAPSHOT: begin
                state_valid = endpoint_state != n2m_interfaces_pkg::STATE_LOADING;
                response_length = 16'(n2m_interfaces_pkg::SNAPSHOT_BYTES);
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
