`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"
// Contract: wiki/src/rtl/snapshot/MAS_snapshot.md.
module n2m_frame_snapshot (
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
    output n2m_interfaces_pkg::snapshot_t snapshot_metadata,
    input var logic frame_read,
    input var logic [12:0] frame_address,
    output logic frame_valid,
    output logic [7:0] frame_data
);
    import n2m_snapshot_pkg::*;
    snapshot_state_t state_q, state_next, reset_value;
    logic done_next, ok_next;
    logic accept_pixel, write_byte, acquire, pin_latest;
    logic copy_read, copy_write, read_bank;
    logic [7:0] packed_byte, copy_data;
    logic [1:0] source_read_valid, host_read_valid;
    logic [7:0] source_read_data [0:1];
    logic [7:0] host_read_data [0:1];
    logic [7:0] unused_source_data [0:1];
    logic [7:0] unused_host_data [0:1];
    logic [1:0] unused_source_valid, unused_host_valid;

    always_comb begin
        reset_value = '0;
        reset_value.assembly_bank = 1'b1;
    end
    assign snapshot_ready = !state_q.busy && !reset_sys && !core_reset;
    assign acquire = snapshot_request && snapshot_ready;
    assign pin_latest = acquire && state_q.latest_valid;
    assign accept_pixel = observe_valid && !observe_abort && !core_reset && !reset_sys;
    assign write_byte = accept_pixel && observe_index[1:0] == 2'd3;
    assign packed_byte = {observe_shade, state_q.packed_shades};
    assign copy_read = state_q.busy && !state_q.copy_pending && !core_reset && !reset_sys;
    assign copy_write = state_q.busy && state_q.copy_pending && !core_reset && !reset_sys;
    assign copy_data = source_read_data[state_q.copy_bank];
    assign snapshot_valid = state_q.host_valid && !reset_sys;
    assign snapshot_metadata = state_q.host_metadata;
    assign frame_valid = host_read_valid[read_bank] && snapshot_valid;
    assign frame_data = host_read_data[read_bank];
    `DFF_ARST_VAL(read_bank, state_q.host_bank, clk_sys, reset_sys, 1'b0)

    always_comb begin
        state_next = state_q;
        done_next = 1'b0;
        ok_next = 1'b0;
        if (accept_pixel) begin
            case (observe_index[1:0])
                2'd0: state_next.packed_shades[1:0] = observe_shade;
                2'd1: state_next.packed_shades[3:2] = observe_shade;
                2'd2: state_next.packed_shades[5:4] = observe_shade;
                default: state_next.packed_shades = 6'd0;
            endcase
            if (observe_complete && !state_q.busy && !pin_latest) begin
                state_next.latest_bank = state_q.assembly_bank;
                state_next.assembly_bank = state_q.latest_bank;
                state_next.latest_valid = 1'b1;
                state_next.latest_metadata.epoch = observe_epoch;
                state_next.latest_metadata.seq = observe_sequence;
                state_next.latest_metadata.dot = observe_dot;
                state_next.latest_metadata.size = 32'd5760;
            end
        end
        if (observe_abort) state_next.packed_shades = 6'd0;
        if (acquire) begin
            if (state_q.latest_valid) begin
                state_next.busy = 1'b1;
                state_next.copy_bank = state_q.latest_bank;
                state_next.copy_metadata = state_q.latest_metadata;
                state_next.copy_address = 13'd0;
                state_next.copy_pending = 1'b0;
            end else done_next = 1'b1;
        end
        if (copy_read) state_next.copy_pending = 1'b1;
        if (copy_write) begin
            state_next.copy_pending = 1'b0;
            if (state_q.copy_address == 13'd5759) begin
                state_next.busy = 1'b0;
                state_next.host_bank = !state_q.host_bank;
                state_next.host_valid = 1'b1;
                state_next.host_metadata = state_q.copy_metadata;
                done_next = 1'b1;
                ok_next = 1'b1;
            end else state_next.copy_address = state_q.copy_address + 13'd1;
        end
        if (core_reset) begin
            state_next.latest_valid = 1'b0;
            state_next.packed_shades = 6'd0;
            state_next.busy = 1'b0;
            state_next.copy_pending = 1'b0;
            done_next = state_q.busy;
            ok_next = 1'b0;
        end
    end
    `DFF_ARST_VAL(state_q, state_next, clk_sys, reset_sys, reset_value)
    `DFF_ARST_VAL(snapshot_done, done_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(snapshot_ok, ok_next, clk_sys, reset_sys, 1'b0)

    genvar bank;
    generate for (bank = 0; bank < 2; bank = bank + 1) begin : banks
        n2m_intel_ram #(.DEPTH(5760), .DATA_BITS(8), .ADDRESS_BITS(13)) u_source (
            .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset_sys), .reset_b(reset_sys),
            .a_read(1'b0), .a_write(write_byte && state_q.assembly_bank == bank),
            .a_address(write_byte ? observe_index[14:2] : 13'd0),
            .a_wdata(packed_byte), .a_byte_enable(1'b1),
            .a_rdata(unused_source_data[bank]), .a_valid(unused_source_valid[bank]),
            .b_read(copy_read && state_q.copy_bank == bank),
            .b_address(copy_read ? state_q.copy_address : 13'd0),
            .b_rdata(source_read_data[bank]), .b_valid(source_read_valid[bank])
        );
        n2m_intel_ram #(.DEPTH(5760), .DATA_BITS(8), .ADDRESS_BITS(13)) u_host (
            .clk_a(clk_sys), .clk_b(clk_sys), .reset_a(reset_sys), .reset_b(reset_sys),
            .a_read(1'b0), .a_write(copy_write && state_q.host_bank != bank),
            .a_address(copy_write ? state_q.copy_address : 13'd0),
            .a_wdata(copy_data), .a_byte_enable(1'b1),
            .a_rdata(unused_host_data[bank]), .a_valid(unused_host_valid[bank]),
            .b_read(frame_read && snapshot_valid && state_q.host_bank == bank),
            .b_address(frame_read ? frame_address : 13'd0),
            .b_rdata(host_read_data[bank]), .b_valid(host_read_valid[bank])
        );
    end endgenerate

    `N2M_ASSERT(SNAPSHOT_SOURCE_RANGE, clk_sys, reset_sys || core_reset,
        !observe_valid || observe_index < 15'd23040)
    `N2M_ASSERT(SNAPSHOT_COMPLETE_INDEX, clk_sys, reset_sys || core_reset,
        !observe_complete || (observe_valid && observe_index == 15'd23039))
    `N2M_ASSERT(SNAPSHOT_BANK_OWNERSHIP, clk_sys, reset_sys,
        state_q.assembly_bank != state_q.latest_bank &&
        (!state_q.busy || state_q.copy_bank != state_q.assembly_bank))
    `N2M_ASSERT(SNAPSHOT_COPY_RESPONSE, clk_sys, reset_sys || core_reset,
        !copy_write || source_read_valid[state_q.copy_bank])
    `N2M_ASSERT(SNAPSHOT_READ_RANGE, clk_sys, reset_sys,
        !frame_read || (snapshot_valid && frame_address < 13'd5760))
endmodule
