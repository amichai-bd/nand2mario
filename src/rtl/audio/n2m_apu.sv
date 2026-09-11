`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Present-but-unimplemented DMG APU gateway. It owns the FF10-FF26 register
// reads and the FF30-FF3F wave-RAM access path. There is no channel, frame
// sequencer, DAC or mixer here; the APU is permanently powered off, so every
// register write is ignored and every register read is its documented
// read-back mask. Wave RAM stays plain storage in the memory owner.
module n2m_apu (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic io_prepare,
    input var logic io_commit,
    input var logic io_write,
    input var logic [15:0] io_address,
    input var logic [7:0] io_wdata,
    output logic io_selected,
    output logic [7:0] io_rdata,
    output logic io_valid,
    output logic wave_read,
    output logic wave_write,
    output logic [3:0] wave_address,
    output logic [7:0] wave_wdata,
    input var logic [7:0] wave_rdata,
    input var logic wave_valid
);
    logic reset, register_selected, wave_selected, wave_request, wave_response;
    logic prepared_read;
    logic [3:0] prepared_address;

    // Unimplemented and unused audio-register bits read back as one. The
    // per-register OR masks are the pinned SameBoy Core/apu.c `read_mask`
    // table in `GB_apu_read`, model 213a12ce93d66b105a113debd9396306066a7cfc.
    // With the APU off every stored bit is zero, so the mask is the read value.
    function automatic logic [7:0] register_read(input logic [15:0] address);
        register_read = 8'hFF;
        case (address)
            n2m_interfaces_pkg::GB_REG_NR10: register_read = 8'h80;
            n2m_interfaces_pkg::GB_REG_NR11: register_read = 8'h3F;
            n2m_interfaces_pkg::GB_REG_NR12: register_read = 8'h00;
            n2m_interfaces_pkg::GB_REG_NR13: register_read = 8'hFF;
            n2m_interfaces_pkg::GB_REG_NR14: register_read = 8'hBF;
            n2m_interfaces_pkg::GB_REG_NR21: register_read = 8'h3F;
            n2m_interfaces_pkg::GB_REG_NR22: register_read = 8'h00;
            n2m_interfaces_pkg::GB_REG_NR23: register_read = 8'hFF;
            n2m_interfaces_pkg::GB_REG_NR24: register_read = 8'hBF;
            n2m_interfaces_pkg::GB_REG_NR30: register_read = 8'h7F;
            n2m_interfaces_pkg::GB_REG_NR31: register_read = 8'hFF;
            n2m_interfaces_pkg::GB_REG_NR32: register_read = 8'h9F;
            n2m_interfaces_pkg::GB_REG_NR33: register_read = 8'hFF;
            n2m_interfaces_pkg::GB_REG_NR34: register_read = 8'hBF;
            n2m_interfaces_pkg::GB_REG_NR41: register_read = 8'hFF;
            n2m_interfaces_pkg::GB_REG_NR42: register_read = 8'h00;
            n2m_interfaces_pkg::GB_REG_NR43: register_read = 8'h00;
            n2m_interfaces_pkg::GB_REG_NR44: register_read = 8'hBF;
            n2m_interfaces_pkg::GB_REG_NR50: register_read = 8'h00;
            n2m_interfaces_pkg::GB_REG_NR51: register_read = 8'h00;
            // NR52: power in bit 7, channel status in bits 3:0, bits 6:4 set.
            // Power stays off and no channel exists, so the read is 8'h70.
            n2m_interfaces_pkg::GB_REG_NR52: register_read = 8'h70;
            default: begin end
        endcase
    endfunction

    assign reset = reset_sys || core_reset;
    assign register_selected = io_address >= n2m_interfaces_pkg::GB_REG_NR10
        && io_address <= n2m_interfaces_pkg::GB_REG_NR52;
    assign wave_selected = io_address >= n2m_interfaces_pkg::GB_VIEW_WAVE_START
        && io_address <= n2m_interfaces_pkg::GB_VIEW_WAVE_END;
    assign io_selected = register_selected || wave_selected;
    assign wave_address = io_address[3:0];
    assign wave_wdata = io_wdata;
    assign wave_request = io_prepare && wave_selected && !io_write && !reset;
    assign wave_read = wave_request;
    assign wave_write = io_commit && io_write && wave_selected && !reset;

    // Store validity belongs to the previous enabled read. Compare the
    // prepared offset before exposing it to a newly prepared request.
    `DFF_ARST_VAL(prepared_read, wave_request, clk_sys, reset, 1'b0)
    `DFF_EN(prepared_address, wave_address, clk_sys, wave_request)
    assign wave_response = prepared_read && prepared_address == wave_address && wave_valid;
    assign io_rdata = wave_selected ? wave_rdata : register_read(io_address);
    assign io_valid = !reset && (wave_selected ? wave_response : register_selected);

    `N2M_ASSERT(APU_COMMIT_BOUNDARY, clk_sys, reset, !io_commit || (gb_tick && io_selected))
    `N2M_ASSERT(APU_PREPARE_SELECTED, clk_sys, reset, !io_prepare || io_selected)
    `N2M_ASSERT(APU_WAVE_EXCLUSIVE, clk_sys, reset, !(wave_read && wave_write))
    `N2M_ASSERT_KNOWN(APU_CONTROLS, clk_sys, reset, {gb_tick, io_prepare, io_commit, io_write})
    `N2M_ASSERT(APU_WRITE_KNOWN, clk_sys, reset,
        !(io_commit && io_write) || !$isunknown({io_address, io_wdata}))
endmodule
