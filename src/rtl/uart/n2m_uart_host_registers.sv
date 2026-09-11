`timescale 1ns/1ps
`default_nettype none
// Host address space only. An unknown or unaligned address has no value.
module n2m_uart_host_registers (
    input var logic [31:0] address,
    input var logic [7:0] endpoint_state,
    input var logic image_valid,
    input var logic [7:0] profile,
    input var logic [63:0] dot_count,
    input var logic [63:0] retirement_count,
    input var logic [7:0] buttons,
    input var logic [7:0] input_source,
    input var logic [7:0] physical_buttons,
    input var logic [7:0] effective_buttons,
    input var logic snapshot_valid,
    input var n2m_interfaces_pkg::snapshot_t snapshot_metadata,
    input var logic [127:0] build_id,
    // Live DMG I/O observations. Each is a committed flop of its owning
    // module; this decode only selects among them and never drives them.
    input var logic [7:0] io_lcdc,
    input var logic [7:0] io_stat,
    input var logic [7:0] io_ly,
    input var logic [7:0] io_lyc,
    input var logic [7:0] io_scy,
    input var logic [7:0] io_scx,
    input var logic [7:0] io_wy,
    input var logic [7:0] io_wx,
    input var logic [7:0] io_bgp,
    input var logic [7:0] io_obp0,
    input var logic [7:0] io_obp1,
    input var logic [7:0] io_div,
    input var logic [7:0] io_tima,
    input var logic [7:0] io_tma,
    input var logic [7:0] io_tac,
    input var logic [7:0] io_if,
    input var logic [7:0] io_ie,
    output logic address_valid,
    output logic [31:0] data
);
    always_comb begin
        address_valid = 1;
        data = 0;
        if (address == n2m_interfaces_pkg::HOST_REG_ABI) data = n2m_interfaces_pkg::WIRE_ABI;
        else if (address == n2m_interfaces_pkg::HOST_REG_STATE) data = {24'b0, endpoint_state};
        else if (address == n2m_interfaces_pkg::HOST_REG_IMAGE_VALID) data = {31'b0, image_valid};
        else if (address == n2m_interfaces_pkg::HOST_REG_PROFILE) data = {24'b0, profile};
        else if (address == n2m_interfaces_pkg::HOST_REG_DOT_LO) data = dot_count[31:0];
        else if (address == n2m_interfaces_pkg::HOST_REG_DOT_HI) data = dot_count[63:32];
        else if (address == n2m_interfaces_pkg::HOST_REG_RETIRE_LO) data = retirement_count[31:0];
        else if (address == n2m_interfaces_pkg::HOST_REG_RETIRE_HI) data = retirement_count[63:32];
        else if (address == n2m_interfaces_pkg::HOST_REG_INPUT) data = {24'b0, buttons};
        else if (address == n2m_interfaces_pkg::HOST_REG_INPUT_SOURCE) data = {24'b0, input_source};
        else if (address == n2m_interfaces_pkg::HOST_REG_INPUT_PHYSICAL) data = {24'b0, physical_buttons};
        else if (address == n2m_interfaces_pkg::HOST_REG_INPUT_EFFECTIVE) data = {24'b0, effective_buttons};
        else if (address == n2m_interfaces_pkg::HOST_REG_SNAPSHOT_VALID) data = {31'b0, snapshot_valid};
        else if (address == n2m_interfaces_pkg::HOST_REG_SNAPSHOT_SEQ_LO) data = snapshot_metadata.seq[31:0];
        else if (address == n2m_interfaces_pkg::HOST_REG_SNAPSHOT_SEQ_HI) data = snapshot_metadata.seq[63:32];
        else if (address == n2m_interfaces_pkg::HOST_REG_BUILD_ID_0) data = build_id[31:0];
        else if (address == n2m_interfaces_pkg::HOST_REG_BUILD_ID_1) data = build_id[63:32];
        else if (address == n2m_interfaces_pkg::HOST_REG_BUILD_ID_2) data = build_id[95:64];
        else if (address == n2m_interfaces_pkg::HOST_REG_BUILD_ID_3) data = build_id[127:96];
        else if (address == n2m_interfaces_pkg::HOST_REG_SNAPSHOT_EPOCH) data = snapshot_metadata.epoch;
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_LCDC) data = {24'b0, io_lcdc};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_STAT) data = {24'b0, io_stat};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_LY) data = {24'b0, io_ly};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_LYC) data = {24'b0, io_lyc};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_SCY) data = {24'b0, io_scy};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_SCX) data = {24'b0, io_scx};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_WY) data = {24'b0, io_wy};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_WX) data = {24'b0, io_wx};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_BGP) data = {24'b0, io_bgp};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_OBP0) data = {24'b0, io_obp0};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_OBP1) data = {24'b0, io_obp1};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_DIV) data = {24'b0, io_div};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_TIMA) data = {24'b0, io_tima};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_TMA) data = {24'b0, io_tma};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_TAC) data = {24'b0, io_tac};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_IF) data = {24'b0, io_if};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_IE) data = {24'b0, io_ie};
        else if (address == n2m_interfaces_pkg::HOST_REG_IO_LCD_STATUS)
            data = {8'b0, io_lcdc, io_stat, io_ly};
        else address_valid = 0;
    end
endmodule
`default_nettype wire
