`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Original DMG-B word transformation. Arbitration owns when to accept it.
module n2m_oam_corrupt (
    input var logic clk_sys,
    input var logic reset,
    input var logic [4:0] row_index,
    input var n2m_oam_pkg::oam_effect_t kind,
    input var logic [63:0] current_row,
    input var logic [63:0] previous_row,
    input var logic [63:0] older_row,
    output logic [63:0] current_result,
    output logic [63:0] previous_result,
    output logic [63:0] older_result,
    output logic [2:0] write_mask,
    output logic invalid_row
);
    logic [15:0] a, b, c, d, transformed;
    // clk_sys/reset sample invariants only. The transformation has no flops.
    always_comb begin
        current_result = current_row;
        previous_result = previous_row;
        older_result = older_row;
        write_mask = 0;
        invalid_row = row_index > 19;
        a = 0;
        b = 0;
        c = 0;
        d = 0;
        transformed = 0;
        if (!invalid_row && row_index != 0 && kind != n2m_oam_pkg::OAM_NONE) begin
            if (kind == n2m_oam_pkg::OAM_READ_WRITE && row_index >= 4 && row_index < 19) begin
                a = older_row[15:0];
                b = previous_row[15:0];
                c = current_row[15:0];
                d = previous_row[47:32];
                transformed = (b & (a | c | d)) | (a & c & d);
                previous_result[15:0] = transformed;
                current_result = previous_result;
                older_result = previous_result;
                write_mask = 3'b111;
            end else write_mask = 3'b001;
            // The normal read step consumes the already transformed rows.
            a = current_result[15:0];
            b = previous_result[15:0];
            c = previous_result[47:32];
            transformed = kind == n2m_oam_pkg::OAM_WRITE ? ((a ^ c) & (b ^ c)) ^ c : b | (a & c);
            current_result = {previous_result[63:16], transformed};
        end
    end
    `N2M_ASSERT(CORRUPTION_MASK_RANGE, clk_sys, reset,
        !invalid_row || write_mask == 0)
    `N2M_ASSERT(CORRUPTION_FIRST_ROW, clk_sys, reset,
        row_index != 0 || write_mask == 0)
endmodule
