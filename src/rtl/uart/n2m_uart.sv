`timescale 1ns/1ps
`default_nettype none
module n2m_uart #(
    parameter integer CLOCK_HZ = 50000000,
    parameter integer BAUD = n2m_interfaces_pkg::WIRE_BAUD
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic uart_rx,
    output logic uart_tx,
    input var logic [127:0] build_id,
    input var logic gb_tick,
    input var logic paused,
    input var logic core_initialized,
    input var logic instruction_complete,
    input var logic retirement_valid,
    input var logic cpu_stopped,
    output logic pause_request,
    output logic core_reset,
    output logic [7:0] buttons,
    input var logic physical_commit,
    input var logic [7:0] physical_buttons,
    output logic [7:0] effective_buttons,
    output n2m_input_pkg::input_update_t effective_update,
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
    import n2m_uart_pkg::*;
    n2m_input_pkg::input_write_t accepted_input;
    logic [7:0] input_source, physical_observe;
    logic rx_valid, rx_error, byte_valid, byte_ready;
    logic [7:0] rx_data, byte_data;
    logic request_valid, request_done;
    n2m_interfaces_pkg::packet_header_t request_header;
    logic [UART_ADDRESS_BITS-1:0] request_bytes;
    logic packet_read, packet_data_valid;
    logic [UART_ADDRESS_BITS-1:0] packet_address;
    logic [7:0] packet_data;
    logic command_valid, command_done, command_packet_read;
    logic [7:0] command_forced_status;
    logic [UART_ADDRESS_BITS-1:0] command_packet_address;
    logic response_write;
    logic [UART_ADDRESS_BITS-1:0] response_address, response_bytes;
    logic [7:0] response_data;
    logic transmit_valid, transmit_read, transmit_data_valid, transmit_done;
    logic [UART_ADDRESS_BITS-1:0] transmit_bytes, transmit_address;
    logic [7:0] transmit_data;
    n2m_input u_input (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .host_write(accepted_input), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .host_buttons(buttons), .physical_observe(physical_observe), .source_observe(input_source),
        .effective_buttons(effective_buttons), .effective_update(effective_update)
    );
    n2m_uart_rx #(.CLOCK_HZ(CLOCK_HZ), .BAUD(BAUD)) u_serial_rx (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .uart_rx(uart_rx),
        .byte_valid(rx_valid), .byte_data(rx_data), .frame_error(rx_error)
    );
    n2m_uart_tx #(.CLOCK_HZ(CLOCK_HZ), .BAUD(BAUD)) u_serial_tx (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .uart_tx(uart_tx),
        .byte_valid(byte_valid), .byte_data(byte_data), .byte_ready(byte_ready)
    );
    n2m_uart_packet_rx #(.CLOCK_HZ(CLOCK_HZ)) u_packet_rx (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .rx_valid(rx_valid), .rx_data(rx_data), .rx_error(rx_error),
        .request_valid(request_valid), .request_header(request_header), .request_bytes(request_bytes),
        .request_done(request_done), .packet_read(packet_read), .packet_address(packet_address),
        .packet_data(packet_data), .packet_data_valid(packet_data_valid)
    );
    n2m_uart_exchange u_exchange (
        .clk_sys(clk_sys),
        .reset_sys(reset_sys),
        .request_valid(request_valid),
        .request_header(request_header),
        .request_bytes(request_bytes),
        .request_done(request_done),
        .packet_read(packet_read),
        .packet_address(packet_address),
        .packet_data(packet_data),
        .packet_data_valid(packet_data_valid),
        .command_valid(command_valid),
        .command_forced_status(command_forced_status),
        .command_packet_read(command_packet_read),
        .command_packet_address(command_packet_address),
        .response_write(response_write),
        .response_address(response_address),
        .response_data(response_data),
        .command_done(command_done),
        .response_bytes(response_bytes),
        .transmit_valid(transmit_valid),
        .transmit_bytes(transmit_bytes),
        .transmit_read(transmit_read),
        .transmit_address(transmit_address),
        .transmit_data(transmit_data),
        .transmit_data_valid(transmit_data_valid),
        .transmit_done(transmit_done)
    );
    n2m_uart_packet_tx u_packet_tx (
        .clk_sys(clk_sys),
        .reset_sys(reset_sys),
        .transmit_valid(transmit_valid),
        .transmit_bytes(transmit_bytes),
        .transmit_done(transmit_done),
        .transmit_read(transmit_read),
        .transmit_address(transmit_address),
        .transmit_data(transmit_data),
        .transmit_data_valid(transmit_data_valid),
        .byte_valid(byte_valid),
        .byte_data(byte_data),
        .byte_ready(byte_ready)
    );
    n2m_uart_commands u_commands (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .command_valid(command_valid),
        .command_forced_status(command_forced_status), .request_header(request_header), .request_bytes(request_bytes),
        .packet_read(command_packet_read), .packet_address(command_packet_address),
        .packet_data(packet_data), .packet_data_valid(packet_data_valid),
        .response_write(response_write), .response_address(response_address), .response_data(response_data),
        .command_done(command_done), .response_bytes(response_bytes), .build_id(build_id),
        .gb_tick(gb_tick), .paused(paused), .core_initialized(core_initialized),
        .instruction_complete(instruction_complete), .retirement_valid(retirement_valid), .cpu_stopped(cpu_stopped),
        .pause_request(pause_request), .core_reset(core_reset), .buttons(buttons), .input_source(input_source),
        .physical_buttons(physical_observe), .effective_buttons(effective_buttons),
        .accepted_input(accepted_input), .epoch(epoch),
        .dot_count(dot_count), .retirement_count(retirement_count), .profile(profile), .image_valid(image_valid),
        .endpoint_state(endpoint_state), .rom_write(rom_write), .rom_read(rom_read), .rom_address(rom_address),
        .rom_write_data(rom_write_data), .rom_read_data(rom_read_data), .rom_read_valid(rom_read_valid),
        .snapshot_request(snapshot_request), .snapshot_ready(snapshot_ready), .snapshot_done(snapshot_done),
        .snapshot_ok(snapshot_ok), .snapshot_valid(snapshot_valid), .snapshot_metadata(snapshot_metadata),
        .frame_read(frame_read), .frame_address(frame_address), .frame_data(frame_data), .frame_valid(frame_valid)
    );
endmodule
`default_nettype wire
