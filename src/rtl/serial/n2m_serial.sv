`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Present-but-unimplemented DMG serial port. SB is plain byte storage and SC
// keeps only its two DMG control bits; unused SC bits read as one. No shift
// clock, no transfer completion and no serial interrupt exist here.
module n2m_serial (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic io_commit,
    input var logic io_write,
    input var logic [15:0] io_address,
    input var logic [7:0] io_wdata,
    output logic io_selected,
    output logic [7:0] io_rdata
);
    // SC bits 6:1 are unused on DMG and read back as one. Pinned SameBoy
    // Core/memory.c stores `value | (~0x83)` and additionally forces bit 1 on
    // non-CGB models, so a DMG SC read is the written value OR 8'h7E.
    localparam logic [7:0] SC_READ_MASK = 8'h7E;
    logic reset, write_sb, write_sc;
    logic [7:0] sb_q, sb_next;
    logic transfer_q, clock_q, transfer_next, clock_next;

    assign reset = reset_sys || core_reset;
    assign io_selected = io_address == n2m_interfaces_pkg::GB_REG_SB
        || io_address == n2m_interfaces_pkg::GB_REG_SC;
    assign write_sb = io_commit && io_write && io_address == n2m_interfaces_pkg::GB_REG_SB;
    assign write_sc = io_commit && io_write && io_address == n2m_interfaces_pkg::GB_REG_SC;
    assign sb_next = write_sb ? io_wdata : sb_q;
    // Transfer enable is retained, never cleared: without a link partner an
    // accepted transfer never completes and raises no interrupt.
    assign transfer_next = write_sc ? io_wdata[7] : transfer_q;
    assign clock_next = write_sc ? io_wdata[0] : clock_q;
    `DFF_ARST_VAL(sb_q, sb_next, clk_sys, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL)
    `DFF_ARST_VAL(transfer_q, transfer_next, clk_sys, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[7])
    `DFF_ARST_VAL(clock_q, clock_next, clk_sys, reset, n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[0])
    always_comb begin
        io_rdata = 0;
        case (io_address)
            n2m_interfaces_pkg::GB_REG_SB:
                io_rdata = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : sb_q;
            n2m_interfaces_pkg::GB_REG_SC:
                io_rdata = reset ? SC_READ_MASK
                    : ({transfer_q, 6'b000000, clock_q} | SC_READ_MASK);
            default: begin end
        endcase
    end
    `N2M_ASSERT(SERIAL_COMMIT_BOUNDARY, clk_sys, reset, !io_commit || (gb_tick && io_selected))
    `N2M_ASSERT_KNOWN(SERIAL_CONTROLS, clk_sys, reset, {gb_tick, io_commit, io_write})
    `N2M_ASSERT(SERIAL_WRITE_KNOWN, clk_sys, reset,
        !(io_commit && io_write) || !$isunknown({io_address, io_wdata}))
    `N2M_ASSERT_STABLE_WHEN(SERIAL_STATE_STABLE, clk_sys, reset,
        !write_sb && !write_sc, {sb_q, transfer_q, clock_q})
endmodule
