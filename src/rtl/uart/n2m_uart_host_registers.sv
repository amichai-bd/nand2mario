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
    input var logic snapshot_valid,
    input var n2m_interfaces_pkg::snapshot_t snapshot_metadata,
    input var logic [127:0] build_id,
    output logic address_valid,
    output logic [31:0] data
);
    import n2m_interfaces_pkg::*;
    always_comb begin
        address_valid = 1;
        data = 0;
        case (address)
            HOST_REG_ABI: data = WIRE_ABI;
            HOST_REG_STATE: data = {24'b0, endpoint_state};
            HOST_REG_IMAGE_VALID: data = {31'b0, image_valid};
            HOST_REG_PROFILE: data = {24'b0, profile};
            HOST_REG_DOT_LO: data = dot_count[31:0];
            HOST_REG_DOT_HI: data = dot_count[63:32];
            HOST_REG_RETIRE_LO: data = retirement_count[31:0];
            HOST_REG_RETIRE_HI: data = retirement_count[63:32];
            HOST_REG_INPUT: data = {24'b0, buttons};
            HOST_REG_SNAPSHOT_VALID: data = {31'b0, snapshot_valid};
            HOST_REG_SNAPSHOT_SEQ_LO: data = snapshot_metadata.seq[31:0];
            HOST_REG_SNAPSHOT_SEQ_HI: data = snapshot_metadata.seq[63:32];
            HOST_REG_BUILD_ID_0: data = build_id[31:0];
            HOST_REG_BUILD_ID_1: data = build_id[63:32];
            HOST_REG_BUILD_ID_2: data = build_id[95:64];
            HOST_REG_BUILD_ID_3: data = build_id[127:96];
            HOST_REG_SNAPSHOT_EPOCH: data = snapshot_metadata.epoch;
            default: address_valid = 0;
        endcase
    end
endmodule
`default_nettype wire
