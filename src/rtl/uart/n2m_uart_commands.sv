`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// One validated command at a time. Helpers own storage, core transitions and
// reply bytes; this owner orders them before exchange-cache publication.
module n2m_uart_commands (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic command_valid,
    input var logic [7:0] command_forced_status,
    input var n2m_interfaces_pkg::packet_header_t request_header,
    input var logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] request_bytes,
    output logic packet_read,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] packet_address,
    input var logic [7:0] packet_data,
    input var logic packet_data_valid,
    output logic response_write,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] response_address,
    output logic [7:0] response_data,
    output logic command_done,
    output logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] response_bytes,
    input var logic [127:0] build_id,
    input var logic gb_tick,
    input var logic paused,
    input var logic core_initialized,
    input var logic instruction_complete,
    input var logic retirement_valid,
    input var logic cpu_stopped,
    output logic pause_request,
    output logic core_reset,
    input var logic [7:0] buttons,
    input var logic [7:0] input_source,
    input var logic [7:0] physical_buttons,
    input var logic [7:0] effective_buttons,
    output n2m_input_pkg::input_write_t accepted_input,
    output logic [31:0] epoch,
    output logic [63:0] dot_count,
    output logic [63:0] retirement_count,
    output logic [7:0] profile,
    output logic image_valid,
    output logic [7:0] endpoint_state,
    output logic rom_write,
    output logic rom_read,
    output logic [14:0] rom_address,
    output logic [7:0] rom_write_data,
    input var logic [7:0] rom_read_data,
    input var logic rom_read_valid,
    output logic snapshot_request,
    input var logic snapshot_ready,
    input var logic snapshot_done,
    input var logic snapshot_ok,
    input var logic snapshot_valid,
    input var n2m_interfaces_pkg::snapshot_t snapshot_metadata,
    output logic frame_read,
    output logic [12:0] frame_address,
    input var logic [7:0] frame_data,
    input var logic frame_valid
);
    typedef enum logic [4:0] {
        IDLE, ARG_FETCH, ARG_USE, VALIDATE, CORE_START, CORE_WAIT,
        LOAD_START, LOAD_WAIT, WRITE_FETCH, WRITE_USE,
        SNAPSHOT_START, SNAPSHOT_WAIT, REPLY_START, REPLY_SMALL,
        REPLY_ROM, FRAME_FETCH, FRAME_USE, REPLY_WAIT
    } state_t;
    state_t state, state_next;
    logic [n2m_interfaces_pkg::LOAD_BEGIN_BYTES*8-1:0] arguments, arguments_next;
    logic [3:0] arg_index, arg_index_next, arg_limit, arg_limit_next;
    logic [n2m_uart_pkg::UART_ADDRESS_BITS-1:0] index, index_next;
    logic loading, loading_next, image_valid_next;
    logic [7:0] profile_next, reply_status, reply_status_next;
    logic [15:0] reply_length, reply_length_next;
    logic [n2m_interfaces_pkg::SNAPSHOT_BYTES*8-1:0] reply_value, reply_value_next;
    logic [7:0] validation_status;
    logic [15:0] validation_length;
    logic host_address_valid;
    logic [31:0] host_data;
    logic core_start, core_busy, core_done;
    logic [7:0] core_command, core_status;
    logic [63:0] core_completed_dot;
    n2m_interfaces_pkg::run_dots_t run_dots_result;
    logic load_start, load_busy, load_done;
    n2m_uart_pkg::uart_load_operation_t load_operation;
    logic [7:0] load_status, load_output_data;
    logic [15:0] load_count;
    logic load_input_valid, load_input_ready, load_output_valid, load_output_ready;
    logic reply_start, reply_busy, reply_done, payload_valid, payload_ready;
    logic [7:0] payload_data;
    n2m_input_pkg::input_write_t core_input;
    n2m_interfaces_pkg::write_host_t write_fields;
    n2m_interfaces_pkg::load_begin_t begin_fields;
    n2m_interfaces_pkg::read_range_t range_fields;
    assign write_fields = arguments[n2m_interfaces_pkg::WRITE_HOST_BYTES*8-1:0];
    assign core_input.valid = 1'b1;
    assign core_input.source_write = request_header.command == n2m_interfaces_pkg::COMMAND_WRITE_HOST && write_fields.address == n2m_interfaces_pkg::HOST_REG_INPUT_SOURCE;
    assign core_input.value = request_header.command == n2m_interfaces_pkg::COMMAND_WRITE_HOST ? write_fields.value[7:0] : arguments[7:0];
    assign begin_fields = arguments;
    assign range_fields = arguments[n2m_interfaces_pkg::READ_RANGE_BYTES*8-1:0];
    assign endpoint_state = loading ? n2m_interfaces_pkg::STATE_LOADING : (paused ? n2m_interfaces_pkg::STATE_PAUSED : n2m_interfaces_pkg::STATE_RUNNING);
    assign packet_read = (state == ARG_FETCH || state == WRITE_FETCH) && !reset_sys;
    assign packet_address = state == ARG_FETCH ? n2m_uart_pkg::UART_ADDRESS_BITS'(n2m_interfaces_pkg::PACKET_HEADER_BYTES + arg_index)
        : n2m_uart_pkg::UART_ADDRESS_BITS'(n2m_interfaces_pkg::PACKET_HEADER_BYTES + n2m_interfaces_pkg::OFFSET_BYTES) + index;
    assign core_start = state == CORE_START;
    assign core_command = request_header.command == n2m_interfaces_pkg::COMMAND_LOAD_BEGIN || request_header.command == n2m_interfaces_pkg::COMMAND_LOAD_END
        ? n2m_interfaces_pkg::COMMAND_RESET : (request_header.command == n2m_interfaces_pkg::COMMAND_WRITE_HOST ? n2m_interfaces_pkg::COMMAND_INPUT : request_header.command);
    assign load_start = state == LOAD_START;
    always_comb begin
        case (request_header.command)
            n2m_interfaces_pkg::COMMAND_LOAD_BEGIN: load_operation = n2m_uart_pkg::UART_LOAD_BEGIN;
            n2m_interfaces_pkg::COMMAND_LOAD_WRITE: load_operation = n2m_uart_pkg::UART_LOAD_WRITE;
            n2m_interfaces_pkg::COMMAND_LOAD_END: load_operation = n2m_uart_pkg::UART_LOAD_END;
            default: load_operation = n2m_uart_pkg::UART_LOAD_READ;
        endcase
    end
    assign load_count = request_header.command == n2m_interfaces_pkg::COMMAND_LOAD_WRITE
        ? request_header.length - 16'(n2m_interfaces_pkg::OFFSET_BYTES) : range_fields.count;
    assign load_input_valid = state == WRITE_USE && packet_data_valid;
    assign load_output_ready = state == REPLY_ROM && payload_ready;
    assign reply_start = state == REPLY_START;
    assign command_done = reply_done && (state == REPLY_WAIT || state == REPLY_ROM);
    assign snapshot_request = state == SNAPSHOT_START && !reset_sys;
    assign frame_read = state == FRAME_FETCH && payload_ready && !reset_sys;
    assign frame_address = range_fields.offset[12:0] + 13'(index);
    always_comb begin
        payload_valid = 0;
        payload_data = 0;
        case (state)
            REPLY_SMALL: begin
                payload_valid = 1;
                payload_data = 8'(reply_value >> (index*8));
            end
            REPLY_ROM: begin payload_valid = load_output_valid; payload_data = load_output_data; end
            FRAME_USE: begin payload_valid = frame_valid; payload_data = frame_data; end
            default: begin end
        endcase
    end
    n2m_uart_host_registers u_host_registers (
        .address(arguments[31:0]), .endpoint_state(endpoint_state), .image_valid(image_valid),
        .profile(profile), .dot_count(dot_count), .retirement_count(retirement_count),
        .buttons(buttons), .input_source(input_source), .physical_buttons(physical_buttons),
        .effective_buttons(effective_buttons), .snapshot_valid(snapshot_valid), .snapshot_metadata(snapshot_metadata),
        .build_id(build_id), .address_valid(host_address_valid), .data(host_data)
    );
    n2m_uart_validate u_validate (
        .header(request_header), .packet_bytes(request_bytes), .arguments(arguments),
        .forced_status(command_forced_status), .endpoint_state(endpoint_state),
        .image_valid(image_valid), .snapshot_valid(snapshot_valid), .host_address_valid(host_address_valid),
        .status(validation_status), .response_length(validation_length)
    );
    n2m_uart_core_control u_core_control (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .start(core_start), .command(core_command),
        .step_budget(arguments[31:0]), .input_write(core_input), .gb_tick(gb_tick),
        .paused(paused), .core_initialized(core_initialized), .instruction_complete(instruction_complete),
        .retirement_valid(retirement_valid), .cpu_stopped(cpu_stopped), .pause_request(pause_request),
        .core_reset(core_reset), .accepted_input(accepted_input), .epoch(epoch), .dot_count(dot_count),
        .retirement_count(retirement_count), .busy(core_busy), .done(core_done), .status(core_status),
        .completed_dot(core_completed_dot), .run_dots_result(run_dots_result)
    );
    n2m_uart_load u_load (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .start(load_start), .operation(load_operation),
        .offset(arguments[31:0]), .count(load_count), .expected_crc(begin_fields.crc32),
        .busy(load_busy), .done(load_done), .status(load_status), .input_valid(load_input_valid),
        .input_data(packet_data), .input_ready(load_input_ready), .output_valid(load_output_valid),
        .output_data(load_output_data), .output_ready(load_output_ready), .rom_write(rom_write),
        .rom_read(rom_read), .rom_address(rom_address), .rom_write_data(rom_write_data),
        .rom_read_data(rom_read_data), .rom_read_valid(rom_read_valid)
    );
    n2m_uart_response u_response (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .start(reply_start), .sequence_token(request_header.seq),
        .command(request_header.command), .status(reply_status), .payload_bytes(reply_length),
        .busy(reply_busy), .payload_valid(payload_valid), .payload_data(payload_data), .payload_ready(payload_ready),
        .response_write(response_write), .response_address(response_address), .response_data(response_data),
        .done(reply_done), .response_bytes(response_bytes)
    );
    always_comb begin
        state_next = state;
        arguments_next = arguments;
        arg_index_next = arg_index;
        arg_limit_next = arg_limit;
        index_next = index;
        loading_next = loading;
        image_valid_next = image_valid;
        profile_next = profile;
        reply_status_next = reply_status;
        reply_length_next = reply_length;
        reply_value_next = reply_value;
        case (state)
            IDLE: if (command_valid) begin
                arguments_next = 0;
                arg_index_next = 0;
                arg_limit_next = request_header.length < n2m_interfaces_pkg::LOAD_BEGIN_BYTES ? 4'(request_header.length) : 4'(n2m_interfaces_pkg::LOAD_BEGIN_BYTES);
                index_next = 0;
                if (command_forced_status != n2m_interfaces_pkg::STATUS_OK || request_header.version != n2m_interfaces_pkg::WIRE_VERSION ||
                    request_header.length > n2m_interfaces_pkg::WIRE_MAX_PAYLOAD ||
                    32'(request_bytes) != n2m_interfaces_pkg::PACKET_HEADER_BYTES + 32'(request_header.length) + 2 || request_header.length == 0)
                    state_next = VALIDATE;
                else state_next = ARG_FETCH;
            end
            ARG_FETCH: state_next = ARG_USE;
            ARG_USE: if (packet_data_valid) begin
                arguments_next[arg_index*8 +: 8] = packet_data;
                arg_index_next = arg_index + 1'b1;
                state_next = arg_index + 1'b1 == arg_limit ? VALIDATE : ARG_FETCH;
            end
            VALIDATE: begin
                reply_status_next = validation_status;
                reply_length_next = validation_length;
                reply_value_next = 0;
                if (validation_status != n2m_interfaces_pkg::STATUS_OK) state_next = REPLY_START;
                else case (request_header.command)
                    n2m_interfaces_pkg::COMMAND_PING: begin reply_value_next[31:0] = n2m_interfaces_pkg::WIRE_ABI; state_next = REPLY_START; end
                    n2m_interfaces_pkg::COMMAND_READ_HOST: begin reply_value_next[31:0] = host_data; state_next = REPLY_START; end
                    n2m_interfaces_pkg::COMMAND_RESET, n2m_interfaces_pkg::COMMAND_RUN, n2m_interfaces_pkg::COMMAND_HALT, n2m_interfaces_pkg::COMMAND_STEP, n2m_interfaces_pkg::COMMAND_RUN_DOTS, n2m_interfaces_pkg::COMMAND_INPUT, n2m_interfaces_pkg::COMMAND_WRITE_HOST: state_next = CORE_START;
                    n2m_interfaces_pkg::COMMAND_LOAD_BEGIN: begin
                        loading_next = 1;
                        image_valid_next = 0;
                        profile_next = begin_fields.profile;
                        state_next = CORE_START;
                    end
                    n2m_interfaces_pkg::COMMAND_LOAD_WRITE, n2m_interfaces_pkg::COMMAND_LOAD_END, n2m_interfaces_pkg::COMMAND_READ_ROM: state_next = LOAD_START;
                    n2m_interfaces_pkg::COMMAND_SNAPSHOT: state_next = SNAPSHOT_START;
                    n2m_interfaces_pkg::COMMAND_READ_FRAME: state_next = REPLY_START;
                    default: state_next = REPLY_START;
                endcase
            end
            CORE_START: state_next = CORE_WAIT;
            CORE_WAIT: if (core_done) begin
                if (request_header.command == n2m_interfaces_pkg::COMMAND_LOAD_BEGIN) state_next = LOAD_START;
                else begin
                    if (request_header.command == n2m_interfaces_pkg::COMMAND_LOAD_END) begin loading_next = 0; image_valid_next = 1; end
                    reply_status_next = core_status;
                    if (core_status != n2m_interfaces_pkg::STATUS_OK) reply_length_next = 0;
                    reply_value_next[63:0] = core_completed_dot;
                    if (request_header.command == n2m_interfaces_pkg::COMMAND_RUN_DOTS)
                        reply_value_next[n2m_interfaces_pkg::RUN_DOTS_BYTES*8-1:0] = run_dots_result;
                    state_next = REPLY_START;
                end
            end
            LOAD_START: begin
                index_next = 0;
                if (request_header.command == n2m_interfaces_pkg::COMMAND_LOAD_WRITE) state_next = WRITE_FETCH;
                else if (request_header.command == n2m_interfaces_pkg::COMMAND_READ_ROM) state_next = REPLY_START;
                else state_next = LOAD_WAIT;
            end
            WRITE_FETCH: state_next = WRITE_USE;
            WRITE_USE: if (packet_data_valid && load_input_ready) begin
                index_next = index + 1'b1;
                state_next = 16'(index) + 1'b1 == load_count ? LOAD_WAIT : WRITE_FETCH;
            end
            LOAD_WAIT: if (load_done) begin
                reply_status_next = load_status;
                if (load_status != n2m_interfaces_pkg::STATUS_OK) begin reply_length_next = 0; state_next = REPLY_START; end
                else state_next = request_header.command == n2m_interfaces_pkg::COMMAND_LOAD_END ? CORE_START : REPLY_START;
            end
            SNAPSHOT_START: if (snapshot_ready) state_next = SNAPSHOT_WAIT;
            SNAPSHOT_WAIT: if (snapshot_done) begin
                reply_status_next = snapshot_ok ? n2m_interfaces_pkg::STATUS_OK : n2m_interfaces_pkg::STATUS_NO_FRAME;
                reply_length_next = snapshot_ok ? 16'(n2m_interfaces_pkg::SNAPSHOT_BYTES) : 16'd0;
                reply_value_next = snapshot_metadata;
                state_next = REPLY_START;
            end
            REPLY_START: begin
                index_next = 0;
                if (reply_length == 0) state_next = REPLY_WAIT;
                else if (request_header.command == n2m_interfaces_pkg::COMMAND_READ_ROM) state_next = REPLY_ROM;
                else if (request_header.command == n2m_interfaces_pkg::COMMAND_READ_FRAME) state_next = FRAME_FETCH;
                else state_next = REPLY_SMALL;
            end
            REPLY_SMALL: if (payload_ready) begin
                index_next = index + 1'b1;
                if (16'(index) + 1'b1 == reply_length) state_next = REPLY_WAIT;
            end
            FRAME_FETCH: if (payload_ready) state_next = FRAME_USE;
            FRAME_USE: if (frame_valid && payload_ready) begin
                index_next = index + 1'b1;
                state_next = 16'(index) + 1'b1 == reply_length ? REPLY_WAIT : FRAME_FETCH;
            end
            REPLY_ROM, REPLY_WAIT: if (reply_done) state_next = IDLE;
            default: state_next = IDLE;
        endcase
    end
    `DFF_ARST_VAL(state, state_next, clk_sys, reset_sys, IDLE)
    `DFF_ARST_VAL(arguments, arguments_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(arg_index, arg_index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(arg_limit, arg_limit_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(index, index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(loading, loading_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(image_valid, image_valid_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(profile, profile_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(reply_status, reply_status_next, clk_sys, reset_sys, n2m_interfaces_pkg::STATUS_OK)
    `DFF_ARST_VAL(reply_length, reply_length_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(reply_value, reply_value_next, clk_sys, reset_sys, '0)
    `N2M_ASSERT(UART_COMMAND_ACTIVE, clk_sys, reset_sys, state != IDLE |-> command_valid)
    `N2M_ASSERT(UART_COMMAND_PACKET_SERVICE, clk_sys, reset_sys,
        state == ARG_USE || state == WRITE_USE |-> packet_data_valid)
    `N2M_ASSERT(UART_COMMAND_FRAME_SERVICE, clk_sys, reset_sys, state == FRAME_USE |-> frame_valid)
    `N2M_ASSERT(UART_COMMAND_WRITE_READY, clk_sys, reset_sys, state == WRITE_USE |-> load_input_ready)
    `N2M_ASSERT(UART_COMMAND_LOAD_PAUSED, clk_sys, reset_sys, rom_write |-> loading && paused)
    `N2M_ASSERT(UART_COMMAND_PACKET_RANGE, clk_sys, reset_sys,
        packet_read |-> packet_address < request_bytes - 2)
    `N2M_ASSERT_KNOWN(UART_COMMAND_STATE, clk_sys, reset_sys, ({state, command_valid, image_valid, loading}))
endmodule
`default_nettype wire
