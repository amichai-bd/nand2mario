`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Source, observer and ownership contract: wiki/src/rtl/vga/MAS_vga.md.
module n2m_frame_bridge (
    input logic clk_sys, reset_sys, core_reset,
    input logic clk_pix, reset_pix,
    input logic source_valid, source_start,
    input logic [1:0] source_shade,
    input logic [31:0] source_epoch,
    input logic [63:0] source_dot,
    output logic observe_valid, observe_complete,
    output logic [14:0] observe_index,
    output logic [1:0] observe_shade,
    output logic [31:0] observe_epoch,
    output logic [63:0] observe_sequence, observe_dot,
    output logic [63:0] discard_count, repeat_count,
    output logic display_valid,
    output logic [63:0] display_sequence,
    output logic [31:0] display_epoch,
    output logic [9:0] video_x, video_y,
    output logic video_valid, video_active, video_image,
    output logic [3:0] red, green, blue,
    output logic hsync_n, vsync_n
);
    logic [14:0] write_index;
    logic [63:0] source_sequence;
    wire accept_pixel = source_valid && !reset_sys && !core_reset;
    wire complete = accept_pixel && write_index == 15'd23039;
    `DFF_RST_EN(write_index, complete ? 15'd0 : write_index + 15'd1,
                clk_sys, accept_pixel, reset_sys || core_reset, 15'd0)
    `DFF_RST_EN(source_sequence, source_sequence + 64'd1, clk_sys, complete,
                reset_sys || core_reset, 64'd0)
    assign observe_valid = accept_pixel;
    assign observe_complete = complete;
    assign observe_index = write_index;
    assign observe_shade = source_shade;
    assign observe_epoch = source_epoch;
    assign observe_sequence = source_sequence;
    assign observe_dot = source_dot;

    logic request, acknowledge;
    // Specialized attributed synchronizers; no functional use of first stages.
    (* preserve, altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED" *)
    logic [1:0] pix_ready_sys, sys_ready_pix, ack_sys, req_pix;
    `DFF_ARST_VAL(pix_ready_sys, {pix_ready_sys[0], !reset_pix}, clk_sys, reset_sys, 2'b00)
    `DFF_ARST_VAL(ack_sys, {ack_sys[0], acknowledge}, clk_sys, reset_sys, 2'b00)
    `DFF_ARST_VAL(sys_ready_pix, {sys_ready_pix[0], !reset_sys}, clk_pix, reset_pix, 2'b00)
    `DFF_ARST_VAL(req_pix, {req_pix[0], request}, clk_pix, reset_pix, 2'b00)
    logic [1:0] writer_bank, system_display_bank, free_bank, offer_bank;
    logic [1:0] writer_next, system_display_next, free_next, offer_next;
    logic pending, pending_next, request_next;
    logic [63:0] offer_sequence, offer_sequence_next, discard_next;
    logic [31:0] offer_epoch, offer_epoch_next;
    always_comb begin
        writer_next = writer_bank;
        system_display_next = system_display_bank;
        free_next = free_bank;
        offer_next = offer_bank;
        pending_next = pending;
        request_next = request;
        offer_sequence_next = offer_sequence;
        offer_epoch_next = offer_epoch;
        discard_next = discard_count;
        // Returning ownership is applied before a simultaneous completion.
        if (pending && ack_sys[1] == request && pix_ready_sys[1]) begin
            free_next = system_display_bank;
            system_display_next = offer_bank;
            pending_next = 1'b0;
        end
        if (complete) begin
            if (!pending_next && pix_ready_sys[1]) begin
                offer_next = writer_bank;
                offer_sequence_next = source_sequence;
                offer_epoch_next = source_epoch;
                request_next = !request;
                pending_next = 1'b1;
                writer_next = free_next;
            end else discard_next = discard_count + 64'd1;
        end
    end
    `DFF_RST_VAL(writer_bank, writer_next, clk_sys, reset_sys, 2'd0)
    `DFF_RST_VAL(system_display_bank, system_display_next, clk_sys, reset_sys, 2'd1)
    `DFF_RST_VAL(free_bank, free_next, clk_sys, reset_sys, 2'd2)
    `DFF_RST_VAL(offer_bank, offer_next, clk_sys, reset_sys, 2'd0)
    `DFF_RST(pending, pending_next, clk_sys, reset_sys)
    `DFF_RST(request, request_next, clk_sys, reset_sys)
    `DFF_RST(offer_sequence, offer_sequence_next, clk_sys, reset_sys)
    `DFF_RST(offer_epoch, offer_epoch_next, clk_sys, reset_sys)
    `DFF_RST(discard_count, discard_next, clk_sys, reset_sys)

    logic capture_wait, captured;
    logic [1:0] captured_bank, display_bank;
    logic [63:0] captured_sequence;
    logic [31:0] captured_epoch;
    logic captured_phase;
    logic swap_boundary;
    wire new_request = sys_ready_pix[1] && req_pix[1] != acknowledge;
    wire capture_now = capture_wait && !captured;
    wire swap = swap_boundary && captured && sys_ready_pix[1];
    `DFF_RST(capture_wait, new_request && !captured && !capture_wait,
             clk_pix, reset_pix)
    `DFF_RST(captured, swap ? 1'b0 : (capture_now ? 1'b1 : captured), clk_pix, reset_pix)
    `DFF_RST_EN(captured_bank, offer_bank, clk_pix, capture_now, reset_pix, 2'd0)
    `DFF_RST_EN(captured_sequence, offer_sequence, clk_pix, capture_now, reset_pix, 64'd0)
    `DFF_RST_EN(captured_epoch, offer_epoch, clk_pix, capture_now, reset_pix, 32'd0)
    `DFF_RST_EN(captured_phase, req_pix[1], clk_pix, capture_now, reset_pix, 1'b0)
    `DFF_RST_EN(display_bank, captured_bank, clk_pix, swap, reset_pix, 2'd1)
    `DFF_RST_EN(display_sequence, captured_sequence, clk_pix, swap, reset_pix, 64'd0)
    `DFF_RST_EN(display_epoch, captured_epoch, clk_pix, swap, reset_pix, 32'd0)
    `DFF_RST_EN(display_valid, 1'b1, clk_pix, swap, reset_pix, 1'b0)
    `DFF_RST_EN(acknowledge, captured_phase, clk_pix, swap, reset_pix, 1'b0)
    `DFF_RST_EN(repeat_count, repeat_count + 64'd1, clk_pix,
                swap_boundary && !swap && display_valid, reset_pix, 64'd0)

    logic read_enable;
    logic [14:0] read_address;
    wire [1:0] bank_shade [0:2];
    wire [1:0] read_shade = bank_shade[display_bank];
    genvar bank;
    generate for (bank = 0; bank < 3; bank = bank + 1) begin : banks
        n2m_frame_ram u_ram (
            .clk_sys, .write_enable(accept_pixel && writer_bank == 2'(bank)),
            .write_address(write_index), .write_shade(source_shade),
            .clk_pix, .read_enable(read_enable && display_bank == 2'(bank)),
            .read_address, .read_shade(bank_shade[bank])
        );
    end endgenerate
    n2m_vga_scan u_scan (
        .clk_pix, .reset_pix, .display_valid, .read_shade,
        .read_enable, .read_address, .swap_boundary,
        .video_x, .video_y, .video_valid, .video_active, .video_image,
        .red, .green, .blue, .hsync_n, .vsync_n
    );
`ifndef SYNTHESIS
    logic in_frame;
    logic [31:0] frame_epoch;
    `DFF_RST_EN(in_frame, !complete, clk_sys, accept_pixel,
                reset_sys || core_reset, 1'b0)
    `DFF_RST_EN(frame_epoch, source_epoch, clk_sys, accept_pixel && source_start,
                reset_sys || core_reset, 32'd0)
    `N2M_ASSERT(frame_source_order, clk_sys, reset_sys || core_reset,
                source_valid |-> (source_start === !in_frame))
    `N2M_ASSERT(frame_source_epoch, clk_sys, reset_sys || core_reset,
                (source_valid && in_frame) |-> (source_epoch === frame_epoch))
    `N2M_ASSERT(frame_source_known, clk_sys, reset_sys || core_reset,
                source_valid |-> !$isunknown({source_shade, source_start, source_epoch, source_dot}))
`endif
endmodule
