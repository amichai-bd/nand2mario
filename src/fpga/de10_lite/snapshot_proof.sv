`timescale 1ns/1ps
`default_nettype none
// Virtual-port resource/timing proof of the actual four-store service.
module snapshot_proof (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic observe_valid,
    input var logic observe_complete,
    input var logic observe_abort,
    input var logic [14:0] observe_index,
    input var logic [1:0] observe_shade,
    input var logic [31:0] observe_epoch,
    input var logic [63:0] observe_sequence,
    input var logic [63:0] observe_dot,
    input var logic snapshot_request,
    output logic snapshot_ready, snapshot_done, snapshot_ok, snapshot_valid,
    output logic [31:0] snapshot_epoch,
    output logic [63:0] snapshot_sequence, snapshot_dot,
    output logic snapshot_size_valid,
    input var logic frame_read,
    input var logic [12:0] frame_address,
    output logic [7:0] frame_data,
    output logic frame_valid
);
    n2m_interfaces_pkg::snapshot_t snapshot_metadata;
    n2m_frame_snapshot u_snapshot (.*);
    assign snapshot_epoch = snapshot_metadata.epoch;
    assign snapshot_sequence = snapshot_metadata.seq;
    assign snapshot_dot = snapshot_metadata.dot;
    // Size is a fixed ABI value after publication, zero before first success.
    // Expose its state-dependent comparison instead of constant physical pins.
    assign snapshot_size_valid = snapshot_metadata.size == 32'd5760;
endmodule
