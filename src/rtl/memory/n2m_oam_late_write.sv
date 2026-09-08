`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Direct-path late-write owner. Operands share the authoritative OAM A port.
module n2m_oam_late_write (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic prepare,
    input var logic commit,
    input var logic late_window,
    input var logic [15:0] address,
    input var logic [7:0] data,
    input var logic ppu_read,
    input var logic [6:0] ppu_pair,
    input var n2m_memory_pkg::memory_oam_response_t response,
    output n2m_memory_pkg::memory_oam_request_t request,
    output logic raw_oam_busy, late_commit, ppu_read_allowed,
    output logic fault
);
    // 1..5 issue operands, 6 captures the final operand, 7 waits for T4.
    // 8..10 drain the remaining three words after the selected word at T4.
    logic [3:0] phase, phase_next;
    logic reset, identity, start, late_attempt, fault_now;
    logic [15:0] saved_address;
    logic [7:0] saved_data;
    logic [3:0][15:0] last_row, last_row_next, transformed, result;
    logic [15:0] target_word, target_word_next;
    logic [1:0] preferred, saved_preferred, drain_word;

    function automatic logic [1:0] remaining_word(
        input logic [1:0] selected, first,
        input logic [1:0] ordinal
    );
        integer count, rank;
        count = 0;
        remaining_word = 0;
        for (rank = 0; rank < 4; rank = rank + 1) begin
            if (2'(int'(first) + rank) != selected) begin
                if (count == int'(ordinal)) remaining_word = 2'(int'(first) + rank);
                count = count + 1;
            end
        end
    endfunction

    assign reset = reset_sys || core_reset;
    assign identity = prepare && address == saved_address && data == saved_data;
    assign start = !reset && !fault && phase == 0 && prepare;
    assign late_attempt = !reset && commit && late_window;
    assign late_commit = late_attempt && !fault && phase == 7 && identity;
    assign preferred = ppu_pair[6:2] == saved_address[7:3] ? ppu_pair[1:0] : 2'd2;
    assign drain_word = remaining_word(saved_address[2:1], saved_preferred, 2'(phase - 4'd8));

    assign transformed = n2m_memory_pkg::oam_late_result(last_row, target_word, saved_address[2:0], saved_data);

    always_comb begin
        request = '0;
        if (!reset && !fault) begin
            if (phase >= 1 && phase <= 5 && identity && !commit) begin
                request.read = 1;
                request.pair = phase == 5 ? saved_address[7:1] : 7'd75 + 7'(phase);
            end else if (late_commit) begin
                request.write_enable = 2'b11;
                request.pair = saved_address[7:1];
                request.data = transformed[saved_address[2:1]];
            end else if (phase >= 8 && phase <= 10) begin
                request.write_enable = 2'b11;
                request.pair = {saved_address[7:3], drain_word};
                request.data = result[drain_word];
            end
        end
    end
    assign raw_oam_busy = request.read || |request.write_enable;
    assign ppu_read_allowed = ppu_read && !(|request.write_enable && request.pair == ppu_pair);

    always_comb begin
        phase_next = phase;
        last_row_next = last_row;
        target_word_next = target_word;
        if (phase >= 2 && phase <= 5 && response.valid)
            last_row_next[2'(phase - 4'd2)] = response.data;
        if (phase == 6 && response.valid) target_word_next = response.data;
        if (phase == 0) begin
            if (start) phase_next = 1;
        end else if (phase >= 8) begin
            phase_next = phase == 10 ? 4'd0 : phase + 4'd1;
        end else if (commit) begin
            // Invalidate even repeated identical writes; no operand cache reuse.
            phase_next = late_commit ? 4'd8 : 4'd0;
        end else if (!identity) phase_next = 0;
        else if (phase < 7) phase_next = phase + 4'd1;
    end
    assign fault_now = (late_attempt && !late_commit)
        || (phase >= 2 && phase <= 6 && identity && !response.valid)
        || (phase >= 8 && commit);
    `DFF_ARST_VAL(phase, phase_next, clk_sys, reset, 4'd0)
    `DFF_EN(saved_address, address, clk_sys, start)
    `DFF_EN(saved_data, data, clk_sys, start)
    `DFF(last_row, last_row_next, clk_sys)
    `DFF(target_word, target_word_next, clk_sys)
    `DFF_EN(result, transformed, clk_sys, late_commit)
    `DFF_EN(saved_preferred, preferred, clk_sys, late_commit)
    `DFF_ARST_VAL(fault, fault || fault_now, clk_sys, reset, 1'b0)
    `N2M_ASSERT(OAM_LATE_READY, clk_sys, reset, !late_attempt || late_commit)
    `N2M_ASSERT(OAM_LATE_OPERAND, clk_sys, reset,
        !(phase >= 2 && phase <= 6 && identity) || response.valid)
    `N2M_ASSERT(OAM_LATE_DRAIN, clk_sys, reset, !(phase >= 8 && commit))
    `N2M_ASSERT(OAM_LATE_RANGE, clk_sys, reset, !prepare || address[15:8] == 8'hfe && address[7:0] < 8'ha0)
endmodule
